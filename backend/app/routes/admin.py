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
            
            from app.models.user import RewardTransaction
            tx = RewardTransaction(
                user_id=uploader.user_id,
                image_id=img.image_id,
                points=10,
                description=f"Approved image validation reward: {img.original_filename}"
            )
            db.add(tx)
            
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


from datetime import date
from sqlalchemy import func

@router.get("/analytics/details", response_model=dict)
def analytics_details(
    start_date: date | None = None,
    end_date: date | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.annotation import Annotation
    from app.models.training import TrainingJob
    
    img_query = db.query(Image)
    ann_query = db.query(Annotation)
    
    if start_date:
        img_query = img_query.filter(Image.uploaded_at >= start_date)
        ann_query = ann_query.filter(Annotation.annotated_at >= start_date)
        
    if end_date:
        img_query = img_query.filter(Image.uploaded_at <= end_date)
        ann_query = ann_query.filter(Annotation.annotated_at <= end_date)
        
    total_users = db.query(User).count()
    total_images = img_query.count()
    validated_images = img_query.filter(Image.is_validated == True, Image.status == "approved").count()
    pending_images = img_query.filter(Image.status == "uploaded", Image.is_validated == False).count()
    rejected_images = img_query.filter(Image.status == "rejected").count()
    total_annotations = ann_query.count()
    
    category_counts = (
        db.query(Category.class_name, func.count(func.distinct(Annotation.image_id)))
        .outerjoin(Annotation, Category.category_id == Annotation.category_id)
        .group_by(Category.class_name)
        .all()
    )
    category_stats = [{"category": row[0], "count": row[1]} for row in category_counts]
    
    daily_uploads = (
        img_query.with_entities(func.date_trunc('day', Image.uploaded_at).label('day'), func.count(Image.image_id))
        .group_by('day')
        .order_by('day')
        .all()
    )
    daily_stats = [{"date": str(row[0].date()) if row[0] else None, "count": row[1]} for row in daily_uploads]
    
    monthly_uploads = (
        img_query.with_entities(func.date_trunc('month', Image.uploaded_at).label('month'), func.count(Image.image_id))
        .group_by('month')
        .order_by('month')
        .all()
    )
    monthly_stats = [{"month": str(row[0].date().strftime("%Y-%m")) if row[0] else None, "count": row[1]} for row in monthly_uploads]
    
    type_counts = (
        ann_query.with_entities(Annotation.annotation_type, func.count(Annotation.annotation_id))
        .group_by(Annotation.annotation_type)
        .all()
    )
    annotation_types = [{"type": row[0] or "legacy", "count": row[1]} for row in type_counts]
    
    approved_by_date = (
        img_query.filter(Image.is_validated == True, Image.status == "approved")
        .with_entities(func.date_trunc('day', Image.validated_at).label('day'), func.count(Image.image_id))
        .group_by('day')
        .order_by('day')
        .all()
    )
    growth_stats = []
    running_total = 0
    for row in approved_by_date:
        if row[0]:
            running_total += row[1]
            growth_stats.append({"date": str(row[0].date()), "count": row[1], "cumulative": running_total})
            
    jobs_by_status = (
        db.query(TrainingJob.status, func.count(TrainingJob.job_id))
        .group_by(TrainingJob.status)
        .all()
    )
    status_stats = {row[0]: row[1] for row in jobs_by_status}
    
    completed_jobs = (
        db.query(TrainingJob.started_at, TrainingJob.completed_at)
        .filter(TrainingJob.status == "completed", TrainingJob.started_at != None, TrainingJob.completed_at != None)
        .all()
    )
    durations = []
    for started, completed in completed_jobs:
        diff = (completed - started).total_seconds() / 60.0
        durations.append(diff)
    avg_duration = sum(durations) / len(durations) if durations else 0.0
    
    top_contributors = (
        db.query(User.user_id, User.email, User.full_name, User.image_count)
        .order_by(User.image_count.desc())
        .limit(10)
        .all()
    )
    contributor_stats = [
        {"user_id": row[0], "email": row[1], "full_name": row[2], "uploads": row[3] or 0}
        for row in top_contributors
    ]
    
    return {
        "summary": {
            "total_users": total_users,
            "total_images": total_images,
            "validated_images": validated_images,
            "pending_images": pending_images,
            "rejected_images": rejected_images,
            "total_annotations": total_annotations,
        },
        "category_breakdown": category_stats,
        "daily_uploads": daily_stats,
        "monthly_uploads": monthly_stats,
        "annotation_types": annotation_types,
        "dataset_growth": growth_stats,
        "training": {
            "status_counts": status_stats,
            "average_duration_minutes": avg_duration
        },
        "top_contributors": contributor_stats
    }
