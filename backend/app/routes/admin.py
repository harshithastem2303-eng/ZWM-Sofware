from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User
from app.models.category import Category
from app.models.image import Image
from app.dependencies.auth import require_admin
from app.schemas.schemas import CategoryCreate, MessageResponse

router = APIRouter()

class ImageApproveRequest(BaseModel):
    action: str

@router.get("/categories", response_model=dict)
def get_categories(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    categories = db.query(Category).all()
    results = [{"id": c.category_id, "name": c.class_name, "code": c.class_code, "validated_count": c.validated_count} for c in categories]
    return {"categories": results}

@router.post("/categories", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_category(category_in: CategoryCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    existing = db.query(Category).filter(
        (Category.class_name == category_in.class_name) |
        (Category.class_code == category_in.class_code)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Category name or code already exists")

    new_category = Category(
        class_name=category_in.class_name,
        class_code=category_in.class_code
    )
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    
    return {"message": "Category created", "category_id": new_category.category_id}


@router.get("/users", response_model=dict)
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).all()
    results = [{
        "user_id": u.user_id,
        "email": u.email,
        "role": u.role,
        "image_count": u.image_count,
        "reward_points": u.reward_points
    } for u in users]
    return {"users": results}

@router.get("/validation-queue", response_model=dict)
def get_validation_queue(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    images = db.query(Image).filter(Image.status == "uploaded", Image.is_validated == False).all()
    results = [{
        "image_id": img.image_id,
        "original_filename": img.original_filename,
        "uploaded_at": img.uploaded_at
    } for img in images]
    return {"queue": results}

@router.post("/images/{image_id}/approve", response_model=MessageResponse)
def approve_image(image_id: str, request_in: ImageApproveRequest, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    action = request_in.action
    
    img = db.query(Image).filter(Image.image_id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
        
    if action == "approve":
        img.status = "approved"
        img.is_validated = True
        
        uploader = db.query(User).filter(User.user_id == img.user_id).first()
        if uploader and not img.reward_given:
            uploader.reward_points += 10
            uploader.image_count += 1
            img.reward_given = True
            img.credits_awarded = 10
            
    elif action == "reject":
        img.status = "rejected"
        img.is_validated = True
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'approve' or 'reject'")

    db.commit()
    return {"message": f"Image {action}d successfully"}


# ---- Analytics ----

@router.get("/analytics/overview", response_model=dict)
def analytics_overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from app.models.annotation import Annotation
    from app.models.training import TrainingJob

    total_users = db.query(User).count()
    total_images = db.query(Image).count()
    validated_images = db.query(Image).filter(Image.is_validated == True, Image.status == "approved").count()
    pending_images = db.query(Image).filter(Image.status == "uploaded", Image.is_validated == False).count()
    rejected_images = db.query(Image).filter(Image.status == "rejected").count()
    total_annotations = db.query(Annotation).count()
    total_categories = db.query(Category).count()
    total_training_jobs = db.query(TrainingJob).count()

    return {
        "total_users": total_users,
        "total_images": total_images,
        "validated_images": validated_images,
        "pending_images": pending_images,
        "rejected_images": rejected_images,
        "total_annotations": total_annotations,
        "total_categories": total_categories,
        "total_training_jobs": total_training_jobs,
    }


@router.get("/analytics/leaderboard", response_model=dict)
def analytics_leaderboard(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.reward_points.desc()).limit(10).all()
    results = [
        {
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name,
            "reward_points": u.reward_points or 0,
            "image_count": u.image_count or 0,
        }
        for u in users
    ]
    return {"leaderboard": results}
