import json
import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.annotation import Annotation
from app.models.image import Image
from app.models.category import Category
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.schemas.schemas import (
    AnnotationCreate, AnnotationUpdate, AnnotationResponse, MessageResponse,
)

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "annotation"}


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_annotation(
    body: AnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verify image exists
    image = db.query(Image).filter(Image.image_id == body.image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    # Verify category exists
    category = db.query(Category).filter(Category.category_id == body.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Save label_data as JSON file if provided
    label_json_path = None
    if body.label_data is not None:
        from app.config import settings
        labels_dir = os.path.join(settings.UPLOAD_FOLDER, "labels")
        os.makedirs(labels_dir, exist_ok=True)

        import uuid
        label_filename = f"{uuid.uuid4()}.json"
        label_json_path = os.path.join(labels_dir, label_filename)
        with open(label_json_path, "w") as f:
            json.dump(body.label_data, f)

    new_annotation = Annotation(
        image_id=body.image_id,
        category_id=body.category_id,
        annotated_by=current_user.user_id,
        label_json_path=label_json_path,
    )
    db.add(new_annotation)
    db.commit()
    db.refresh(new_annotation)

    return {
        "annotation_id": new_annotation.annotation_id,
        "image_id": new_annotation.image_id,
        "category_id": new_annotation.category_id,
        "annotated_by": new_annotation.annotated_by,
        "label_json_path": new_annotation.label_json_path,
        "yolo_label_path": new_annotation.yolo_label_path,
        "annotated_at": str(new_annotation.annotated_at) if new_annotation.annotated_at else None,
    }


@router.get("/{annotation_id}")
def get_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    return {
        "annotation_id": annotation.annotation_id,
        "image_id": annotation.image_id,
        "category_id": annotation.category_id,
        "annotated_by": annotation.annotated_by,
        "label_json_path": annotation.label_json_path,
        "yolo_label_path": annotation.yolo_label_path,
        "annotated_at": str(annotation.annotated_at) if annotation.annotated_at else None,
    }


@router.get("/image/{image_id}")
def get_annotations_for_image(
    image_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    image = db.query(Image).filter(Image.image_id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    annotations = db.query(Annotation).filter(Annotation.image_id == image_id).all()
    results = [
        {
            "annotation_id": a.annotation_id,
            "image_id": a.image_id,
            "category_id": a.category_id,
            "annotated_by": a.annotated_by,
            "label_json_path": a.label_json_path,
            "yolo_label_path": a.yolo_label_path,
            "annotated_at": str(a.annotated_at) if a.annotated_at else None,
        }
        for a in annotations
    ]
    return {"annotations": results}


@router.put("/{annotation_id}")
def update_annotation(
    annotation_id: str,
    body: AnnotationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Only owner or admin can update
    if annotation.annotated_by != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to update this annotation")

    if body.category_id is not None:
        cat = db.query(Category).filter(Category.category_id == body.category_id).first()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        annotation.category_id = body.category_id

    if body.label_data is not None:
        from app.config import settings
        labels_dir = os.path.join(settings.UPLOAD_FOLDER, "labels")
        os.makedirs(labels_dir, exist_ok=True)

        import uuid
        label_filename = f"{uuid.uuid4()}.json"
        new_path = os.path.join(labels_dir, label_filename)
        with open(new_path, "w") as f:
            json.dump(body.label_data, f)

        # Remove old label file
        if annotation.label_json_path and os.path.exists(annotation.label_json_path):
            os.remove(annotation.label_json_path)
        annotation.label_json_path = new_path

    db.commit()
    db.refresh(annotation)

    return {
        "annotation_id": annotation.annotation_id,
        "image_id": annotation.image_id,
        "category_id": annotation.category_id,
        "annotated_by": annotation.annotated_by,
        "label_json_path": annotation.label_json_path,
        "yolo_label_path": annotation.yolo_label_path,
        "annotated_at": str(annotation.annotated_at) if annotation.annotated_at else None,
    }


@router.delete("/{annotation_id}")
def delete_annotation(
    annotation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    annotation = db.query(Annotation).filter(Annotation.annotation_id == annotation_id).first()
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")

    # Only owner or admin can delete
    if annotation.annotated_by != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this annotation")

    # Clean up label files
    if annotation.label_json_path and os.path.exists(annotation.label_json_path):
        os.remove(annotation.label_json_path)
    if annotation.yolo_label_path and os.path.exists(annotation.yolo_label_path):
        os.remove(annotation.yolo_label_path)

    db.delete(annotation)
    db.commit()
    return {"message": "Annotation deleted successfully"}
