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


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "annotation"}


# ---------------------------------------------------------------------------
# POST / — Create annotation
# ---------------------------------------------------------------------------

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

    # 4. Save label_data as JSON file if provided (legacy backward compatibility)
    label_json_path = None
    if body.label_data is not None:
        labels_dir = os.path.join(settings.UPLOAD_FOLDER, "labels")
        os.makedirs(labels_dir, exist_ok=True)
        import uuid
        label_filename = f"{uuid.uuid4()}.json"
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
    db.commit()
    db.refresh(new_annotation)

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
