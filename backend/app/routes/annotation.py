"""
Annotation routes  —  /api/annotations

Endpoints
---------
POST   /                            Create a new annotation
GET    /{annotation_id}             Get a single annotation
GET    /image/{image_id}            List all annotations for an image
PUT    /{annotation_id}             Update an annotation (owner or admin)
DELETE /{annotation_id}             Delete an annotation (owner or admin)
GET    /{annotation_id}/yolo-bbox   Return the YOLO bounding box for one annotation

Annotation types supported: rectangle | polygon | circle | freehand
Authentication: existing JWT / get_current_user dependency (unchanged).

NOTE: Annotation logic is fully self-contained here.
      The lifecycle service is NOT modified.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.annotation import Annotation
from app.models.image import Image
from app.models.category import Category
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.schemas.schemas import AnnotationCreate, AnnotationUpdate, AnnotationResponse, MessageResponse
from app.services.annotation_service import validate_annotation_type, validate_label_data
from app.services.annotation_converter import shape_to_bbox_dict, annotation_to_yolo_line
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _annotation_to_dict(a: Annotation) -> dict:
    """Serialise an Annotation ORM object to a clean response dict."""
    return {
        "annotation_id": a.annotation_id,
        "image_id": a.image_id,
        "category_id": a.category_id,
        "annotated_by": a.annotated_by,
        "annotation_type": a.annotation_type,
        "label_data_json": a.label_data_json,
        "ai_generated": a.ai_generated,
        "image_width": a.image_width,
        "image_height": a.image_height,
        "label_json_path": a.label_json_path,
        "yolo_label_path": a.yolo_label_path,
        "annotated_at": str(a.annotated_at) if a.annotated_at else None,
    }


def _verify_image(image_id: str, db: Session) -> Image:
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    return image


def _verify_category(category_id: int, db: Session) -> Category:
    cat = db.query(Category).filter(Category.category_id == category_id).first()
    if not cat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return cat


def _verify_annotation_ownership(annotation: Annotation, current_user: User) -> None:
    if annotation.annotated_by != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this annotation",
        )


def _export_image_annotation_json(image_id: str, db: Session) -> Optional[str]:
    """
    Generate and save a structured, comprehensive JSON document containing
    true image metadata, dimensions, status, and all associated annotations.
    Strictly validates and clamps coordinates within [0, img_width] and [0, img_height].
    """
    image_rec = db.query(Image).filter(Image.image_id == image_id).first()
    if not image_rec:
        return None

    img_path = image_rec.permanent_s3_path or image_rec.temp_s3_path
    img_w, img_h = 0, 0

    # Determine exact physical image dimensions from image file on disk
    if img_path and os.path.exists(img_path):
        import cv2
        img = cv2.imread(img_path)
        if img is not None:
            img_h, img_w = img.shape[:2]

    # Fallback to annotation recorded dimensions if file unreadable
    if img_w == 0 or img_h == 0:
        if image_rec.annotations and len(image_rec.annotations) > 0:
            img_w = image_rec.annotations[0].image_width or 0
            img_h = image_rec.annotations[0].image_height or 0

    all_anns = db.query(Annotation).filter(Annotation.image_id == image_id).all()
    formatted_anns = []

    def clamp_x(v: float) -> float:
        if img_w <= 0: return round(float(v), 2)
        return round(max(0.0, min(float(img_w), float(v))), 2)

    def clamp_y(v: float) -> float:
        if img_h <= 0: return round(float(v), 2)
        return round(max(0.0, min(float(img_h), float(v))), 2)

    for ann in all_anns:
        cat = db.query(Category).filter(Category.category_id == ann.category_id).first() if ann.category_id else None
        data = ann.label_data_json or {}
        raw_type = ann.annotation_type or "polygon"
        is_ai = bool(ann.ai_generated or raw_type == "ai_polygon")
        
        final_type = "polygon" if raw_type in ["polygon", "ai_polygon"] else raw_type
        source_str = "ai" if is_ai else "manual"
        
        bbox_dict = shape_to_bbox_dict(raw_type, data) if data else None

        geometry = {}
        # 1. Rectangle
        if final_type == "rectangle":
            if bbox_dict:
                x_min = clamp_x(bbox_dict["x_min"])
                y_min = clamp_y(bbox_dict["y_min"])
                x_max = clamp_x(bbox_dict["x_max"])
                y_max = clamp_y(bbox_dict["y_max"])
                geometry = {
                    "x": x_min,
                    "y": y_min,
                    "width": round(x_max - x_min, 2),
                    "height": round(y_max - y_min, 2)
                }
            else:
                geometry = data
        # 2. Circle
        elif final_type == "circle":
            if isinstance(data, dict) and "cx" in data:
                geometry = {
                    "center": {"x": clamp_x(data["cx"]), "y": clamp_y(data["cy"])},
                    "radius": round(float(data.get("r", 0)), 2)
                }
            elif isinstance(data, dict) and "center" in data:
                geometry = {
                    "center": {"x": clamp_x(data["center"].get("x", 0)), "y": clamp_y(data["center"].get("y", 0))},
                    "radius": round(float(data.get("radius", 0)), 2)
                }
            else:
                geometry = data
        # 3. Polygon & Freehand
        elif final_type in ["polygon", "freehand"]:
            pts = []
            if isinstance(data, dict) and "points" in data:
                pts = data["points"]
            elif isinstance(data, list):
                pts = data

            clamped_pts = [{"x": clamp_x(p.get("x", 0)), "y": clamp_y(p.get("y", 0))} for p in pts if isinstance(p, dict)]
            geometry = {"points": clamped_pts}
        else:
            geometry = data

        # Standardized Bounding Box
        clamped_bbox = None
        if bbox_dict:
            clamped_bbox = {
                "x_min": clamp_x(bbox_dict["x_min"]),
                "y_min": clamp_y(bbox_dict["y_min"]),
                "x_max": clamp_x(bbox_dict["x_max"]),
                "y_max": clamp_y(bbox_dict["y_max"])
            }

        ann_entry = {
            "annotation_id": ann.annotation_id,
            "annotation_type": final_type,
            "category_id": ann.category_id,
            "class_id": cat.class_code if cat else (ann.category_id or 0),
            "class_name": cat.class_name if cat else "Waste Object",
            "source": source_str,
            "ai_generated": is_ai,
            "geometry": geometry,
            "bounding_box": clamped_bbox,
            "annotated_at": str(ann.annotated_at) if ann.annotated_at else None,
        }
        formatted_anns.append(ann_entry)

    export_data = {
        "image_id": image_rec.image_id,
        "image_name": image_rec.original_filename,
        "image_path": img_path,
        "image_width": img_w,
        "image_height": img_h,
        "status": image_rec.status or "annotated",
        "annotations_count": len(formatted_anns),
        "annotations": formatted_anns,
    }

    try:
        labels_dir = os.path.join(settings.UPLOAD_FOLDER, "labels")
        os.makedirs(labels_dir, exist_ok=True)
        export_path = os.path.join(labels_dir, f"{image_id}_annotation.json")
        with open(export_path, "w") as f:
            json.dump(export_data, f, indent=2)
        return export_path
    except Exception as e:
        logger.error(f"Failed to export structured annotation JSON for image {image_id}: {e}")
        return None


def _generate_yolo_txt_for_image(image_id: str, db: Session) -> Optional[str]:
    """Generate YOLO annotation TXT file for all annotations on an image."""
    image_rec = db.query(Image).filter(Image.image_id == image_id).first()
    if not image_rec:
        return None

    annotations = db.query(Annotation).filter(Annotation.image_id == image_id).all()
    if not annotations:
        return None

    img_path = image_rec.permanent_s3_path or image_rec.temp_s3_path
    img_w, img_h = 0, 0
    if img_path and os.path.exists(img_path):
        import cv2
        img = cv2.imread(img_path)
        if img is not None:
            img_h, img_w = img.shape[:2]

    if img_w == 0 or img_h == 0:
        img_w = annotations[0].image_width or 800
        img_h = annotations[0].image_height or 600

    yolo_lines = []
    for ann in annotations:
        if not ann.annotation_type or not ann.label_data_json:
            continue
        cat = db.query(Category).filter(Category.category_id == ann.category_id).first() if ann.category_id else None
        class_id = cat.class_code if cat else (ann.category_id or 0)
        line = annotation_to_yolo_line(
            ann.annotation_type,
            ann.label_data_json,
            img_w,
            img_h,
            class_id,
        )
        if line:
            yolo_lines.append(line)

    if not yolo_lines:
        return None

    labels_dir = os.path.join(settings.UPLOAD_FOLDER, "labels")
    os.makedirs(labels_dir, exist_ok=True)
    txt_path = os.path.join(labels_dir, f"{image_id}.txt")
    with open(txt_path, "w") as f:
        f.write("\n".join(yolo_lines) + "\n")

    return txt_path


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "annotation"}


# ---------------------------------------------------------------------------
# POST / — Create annotation
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
def create_annotation(
    body: AnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new annotation.

    The annotation_type is validated first, then the label_data is validated
    against the shape-specific rules (point count, coordinate validity, etc.).

    category_id is optional — set when the user selects from the label dropdown.
    ai_generated = True marks annotations produced by the ML predict endpoint.
    """
    # 1. Verify image exists
    _verify_image(body.image_id, db)

    # 2. Verify category if provided (from predefined dropdown)
    if body.category_id is not None:
        _verify_category(body.category_id, db)

    # 3. Handle optional annotation_type and label_data validation
    ann_type = None
    validated_data = None
    if body.annotation_type is not None:
        ann_type = validate_annotation_type(body.annotation_type)
        if body.label_data is not None:
            validated_data = validate_label_data(ann_type, body.label_data)
    else:
        # If annotation_type is not specified but label_data is, save label_data as-is
        validated_data = body.label_data

    # 4. Save label_data as JSON file if provided
    label_json_path = None
    if body.label_data is not None:
        labels_dir = os.path.join(settings.UPLOAD_FOLDER, "labels")
        os.makedirs(labels_dir, exist_ok=True)
        label_filename = f"{body.image_id}_annotation.json"
        label_json_path = os.path.join(labels_dir, label_filename)
        with open(label_json_path, "w") as f:
            json.dump(body.label_data, f)

    # 5. Persist annotation inline in PostgreSQL
    new_annotation = Annotation(
        image_id=body.image_id,
        category_id=body.category_id,
        annotated_by=current_user.user_id,
        annotation_type=ann_type,
        label_data_json=validated_data,
        ai_generated=body.ai_generated,
        image_width=body.image_width,
        image_height=body.image_height,
        label_json_path=label_json_path,
    )
    db.add(new_annotation)

    # 6. Update image category & status
    image_rec = db.query(Image).filter(Image.image_id == body.image_id).first()
    if image_rec:
        if body.category_id is not None:
            image_rec.selected_category_id = body.category_id
        image_rec.status = "annotated"
        image_rec.annotated_at = datetime.now(timezone.utc)
        db.add(image_rec)

    db.commit()
    db.refresh(new_annotation)

    # 7. Generate YOLO TXT & promote image and labels to uploads/dataset/{category_slug}/
    yolo_txt_path = _generate_yolo_txt_for_image(body.image_id, db)
    if yolo_txt_path:
        new_annotation.yolo_label_path = yolo_txt_path
        db.commit()
        try:
            from app.services.lifecycle_service import promote_to_permanent
            promote_to_permanent(db, body.image_id, yolo_txt_path)
        except Exception as exc:
            logger.warning(f"Auto-promotion to dataset folder note: {exc}")

    # 8. Generate full structured annotation JSON export
    _export_image_annotation_json(body.image_id, db)

    logger.info(
        "ANNOTATION_CREATED | annotation_id=%s | image_id=%s | type=%s | user=%s | ai=%s",
        new_annotation.annotation_id, body.image_id, ann_type,
        current_user.user_id, body.ai_generated,
    )

    return _annotation_to_dict(new_annotation)


# ---------------------------------------------------------------------------
# GET /{annotation_id} — Get single annotation
# ---------------------------------------------------------------------------

@router.get("/{annotation_id}")
def get_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single annotation by ID."""
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return _annotation_to_dict(annotation)


# ---------------------------------------------------------------------------
# GET /image/{image_id} — List annotations for an image
# ---------------------------------------------------------------------------

@router.get("/image/{image_id}")
def get_annotations_for_image(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all annotations attached to a specific image."""
    _verify_image(image_id, db)
    annotations = db.query(Annotation).filter(Annotation.image_id == image_id).all()
    return {"annotations": [_annotation_to_dict(a) for a in annotations], "count": len(annotations)}


# ---------------------------------------------------------------------------
# PUT /{annotation_id} — Update annotation (owner or admin)
# ---------------------------------------------------------------------------

@router.put("/{annotation_id}")
def update_annotation(
    annotation_id: str,
    body: AnnotationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update an annotation.

    Partial update — only fields present in the request body are changed.
    Only the annotation owner or an admin may update.
    """
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    _verify_annotation_ownership(annotation, current_user)

    # Apply updates
    if body.annotation_type is not None:
        annotation.annotation_type = validate_annotation_type(body.annotation_type)

    if body.label_data is not None:
        effective_type = annotation.annotation_type or "polygon"
        annotation.label_data_json = validate_label_data(effective_type, body.label_data)

    if body.category_id is not None:
        _verify_category(body.category_id, db)
        annotation.category_id = body.category_id

    if body.image_width is not None:
        annotation.image_width = body.image_width

    if body.image_height is not None:
        annotation.image_height = body.image_height

    if body.ai_generated is not None:
        annotation.ai_generated = body.ai_generated

    db.commit()
    db.refresh(annotation)

    logger.info(
        "ANNOTATION_UPDATED | annotation_id=%s | user=%s",
        annotation_id, current_user.user_id,
    )

    return _annotation_to_dict(annotation)


# ---------------------------------------------------------------------------
# DELETE /{annotation_id} — Delete annotation (owner or admin)
# ---------------------------------------------------------------------------

@router.delete("/{annotation_id}")
def delete_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an annotation and its associated label files."""
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    _verify_annotation_ownership(annotation, current_user)

    # Clean up legacy label files if they exist
    if annotation.label_json_path and os.path.exists(annotation.label_json_path):
        os.remove(annotation.label_json_path)
    if annotation.yolo_label_path and os.path.exists(annotation.yolo_label_path):
        os.remove(annotation.yolo_label_path)

    db.delete(annotation)
    db.commit()

    logger.info(
        "ANNOTATION_DELETED | annotation_id=%s | user=%s",
        annotation_id, current_user.user_id,
    )

    return {"message": "Annotation deleted successfully"}


# ---------------------------------------------------------------------------
# GET /{annotation_id}/yolo-bbox — YOLO bounding-box for one annotation
# ---------------------------------------------------------------------------

@router.get("/{annotation_id}/yolo-bbox")
def get_yolo_bbox(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Return the YOLO-normalised bounding box for an annotation.

    Requires image_width and image_height to have been stored on the annotation
    (or they can be overridden via query parameters).

    Response:
        bbox         : {x_min, y_min, x_max, y_max} in pixels
        yolo_line    : YOLO TXT line string (if class_id available)
        annotation_type
    """
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")

    if not annotation.annotation_type or not annotation.label_data_json:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Annotation has no shape data stored.",
        )

    bbox_dict = shape_to_bbox_dict(annotation.annotation_type, annotation.label_data_json)
    if bbox_dict is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not derive bounding box from annotation data.",
        )

    yolo_line = None
    if annotation.image_width and annotation.image_height and annotation.category_id is not None:
        cat = db.query(Category).filter(Category.category_id == annotation.category_id).first()
        class_id = cat.class_code if cat else annotation.category_id
        yolo_line = annotation_to_yolo_line(
            annotation.annotation_type,
            annotation.label_data_json,
            annotation.image_width,
            annotation.image_height,
            class_id,
        )

    return {
        "annotation_id": annotation_id,
        "annotation_type": annotation.annotation_type,
        "bbox": bbox_dict,
        "yolo_line": yolo_line,
        "image_width": annotation.image_width,
        "image_height": annotation.image_height,
    }
