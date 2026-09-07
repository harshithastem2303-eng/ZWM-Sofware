from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.user import User, Admin
from app.models.category import Category
from app.models.image import Image
from app.dependencies.auth import require_admin
from app.schemas.schemas import CategoryCreate, MessageResponse, SystemSettingUpdate, SystemSettingResponse
from sqlalchemy import func
from app.config import settings
from app.schemas.schemas import UserLogin, TokenResponse
from app.routes.auth import get_password_hash, verify_password
from app.dependencies.auth import create_access_token, create_refresh_token

from typing import Optional
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/login", response_model=TokenResponse)
def admin_login(login_in: UserLogin, db: Session = Depends(get_db)):
    """Authenticate Admin using the admins database table & secure environment configuration."""
    req_email = login_in.email.strip().lower()
    plain_pw = login_in.password.strip()
    admin_email = settings.ADMIN_EMAIL.strip().lower()
    admin_password = settings.ADMIN_PASSWORD.strip()
    
    # Query admins table ONLY
    admin_rec = db.query(Admin).filter(func.lower(Admin.admin_email) == req_email).first()
    
    is_valid = False
    if req_email == admin_email and plain_pw == admin_password:
        is_valid = True
    elif admin_rec and verify_password(plain_pw, admin_rec.hash_password):
        is_valid = True
        
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
        )
        
    # Ensure record exists in admins table ONLY
    if not admin_rec:
        admin_rec = Admin(
            admin_email=req_email,
            admin_name="System Admin",
            hash_password=get_password_hash(plain_pw),
            is_email_verified=True,
        )
        db.add(admin_rec)
        db.commit()
        db.refresh(admin_rec)

    # Clean up any legacy admin rows from users table so users table contains no admin data
    legacy_user = db.query(User).filter(func.lower(User.email) == req_email).first()
    if legacy_user:
        db.delete(legacy_user)
        db.commit()
            
    access_token = create_access_token(identity=admin_rec.admin_id, role="admin")
    refresh_token = create_refresh_token(identity=admin_rec.admin_id)
    
    return {
        "message": "Admin login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": admin_rec.admin_id,
        "role": "admin",
    }

class CreateAdminRequest(BaseModel):
    email: str
    password: Optional[str] = None
    confirm_password: Optional[str] = None
    admin_id: Optional[str] = None
    role: str = "Admin"

@router.post("/create", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_admin(request_in: CreateAdminRequest, current_admin = Depends(require_admin), db: Session = Depends(get_db)):
    """Register a new admin user in the system (stored in admins table ONLY)."""
    email_clean = request_in.email.strip().lower()
    password_clean = (request_in.password or "ZWMAdmin123!").strip()

    if request_in.confirm_password and password_clean != request_in.confirm_password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and confirm password do not match",
        )
    
    # Check if admin already exists in admins table
    existing = db.query(Admin).filter(func.lower(Admin.admin_email) == email_clean).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An admin with this email already exists",
        )
        
    admin_name = request_in.admin_id.strip() if request_in.admin_id else email_clean.split('@')[0].capitalize()
    new_admin = Admin(
        admin_email=email_clean,
        admin_name=admin_name,
        hash_password=get_password_hash(password_clean),
        is_email_verified=True,
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    
    return {
        "message": "Admin created successfully",
        "admin_id": new_admin.admin_id,
        "user_id": new_admin.admin_id,
        "email": new_admin.admin_email,
        "role": request_in.role,
        "temp_password": password_clean,
    }


class ImageApproveRequest(BaseModel):
    action: str

@router.get("/categories", response_model=dict)
def get_categories(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.class_name.asc()).all()
    results = [
        {
            "id": c.category_id,
            "category_id": c.category_id,
            "name": c.class_name,
            "class_name": c.class_name,
            "code": c.class_code,
            "class_code": c.class_code,
            "description": c.description,
            "is_active": c.is_active,
            "validated_count": c.validated_count or 0,
            "total_images": db.query(Image).filter(Image.selected_category_id == c.category_id).count()
        }
        for c in categories
    ]
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
        class_code=category_in.class_code,
        description=category_in.description,
        is_active=category_in.is_active if category_in.is_active is not None else True
    )
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    
    # Auto-create dataset folder structure: uploads/dataset/{category_slug}/images & labels
    try:
        from app.services.lifecycle_service import slugify_category_name
        from app.config import settings
        slug = slugify_category_name(new_category.class_name)
        cat_dir = os.path.join(settings.UPLOAD_FOLDER, "dataset", slug)
        os.makedirs(os.path.join(cat_dir, "images"), exist_ok=True)
        os.makedirs(os.path.join(cat_dir, "labels"), exist_ok=True)
    except Exception as exc:
        logger.warning(f"Could not auto-create dataset directory for category '{new_category.class_name}': {exc}")

    return {
        "message": "Category created successfully",
        "category_id": new_category.category_id,
        "class_name": new_category.class_name,
        "is_active": new_category.is_active
    }


from app.schemas.schemas import CategoryUpdate

@router.patch("/categories/{category_id}", response_model=dict)
def update_category(category_id: int, category_in: CategoryUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.category_id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if category_in.class_name is not None:
        category.class_name = category_in.class_name
    if category_in.class_code is not None:
        category.class_code = category_in.class_code
    if category_in.description is not None:
        category.description = category_in.description
    if category_in.is_active is not None:
        category.is_active = category_in.is_active

    db.commit()
    db.refresh(category)
    return {
        "message": "Category updated successfully",
        "category_id": category.category_id,
        "is_active": category.is_active
    }


@router.delete("/categories/{category_id}", response_model=dict)
def delete_category(category_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.category_id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    cat_name = category.class_name
    from app.services.lifecycle_service import slugify_category_name
    from app.models.annotation import Annotation

    category_slug = slugify_category_name(cat_name)

    # Safely clear FK references from annotations and images before deletion
    db.query(Annotation).filter(Annotation.category_id == category_id).update({"category_id": None}, synchronize_session=False)
    db.query(Image).filter(Image.selected_category_id == category_id).update({"selected_category_id": None}, synchronize_session=False)

    db.delete(category)
    db.commit()

    # Delete corresponding folder from uploads/dataset/{category_slug}
    try:
        cat_dir = os.path.join(settings.UPLOAD_FOLDER, "dataset", category_slug)
        if os.path.exists(cat_dir):
            import shutil
            shutil.rmtree(cat_dir, ignore_errors=True)
            logger.info(f"Deleted dataset folder for category '{cat_name}' at {cat_dir}")
    except Exception as exc:
        logger.warning(f"Could not delete dataset directory for category '{cat_name}': {exc}")

    return {
        "message": f"Category '{cat_name}' deleted successfully",
        "category_id": category_id
    }


@router.get("/users", response_model=dict)
@router.get("/users/contributions", response_model=dict)
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Fetch user contribution statistics using PostgreSQL aggregate queries."""
    users = db.query(User).all()
    results = []
    
    for u in users:
        total_uploads = db.query(Image).filter(Image.user_id == u.user_id).count()
        approved_count = db.query(Image).filter(Image.user_id == u.user_id, Image.status == "approved").count()
        rejected_count = db.query(Image).filter(Image.user_id == u.user_id, Image.status == "rejected").count()
        pending_count = db.query(Image).filter(Image.user_id == u.user_id, Image.status == "uploaded").count()
        needs_review_count = db.query(Image).filter(Image.user_id == u.user_id, Image.status == "pending_admin_review").count()

        results.append({
            "user_id": u.user_id,
            "email": u.email,
            "full_name": u.full_name or u.email.split("@")[0],
            "role": u.role,
            "image_count": u.image_count or total_uploads,
            "reward_points": u.reward_points or 0,
            "stats": {
                "total_uploads": total_uploads,
                "approved": approved_count,
                "rejected": rejected_count,
                "pending": pending_count,
                "needs_review": needs_review_count
            }
        })
        
    return {"users": results}


@router.get("/validation-queue", response_model=dict)
def get_validation_queue(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    images = (
        db.query(Image)
        .filter(Image.status.in_(["uploaded", "pending_admin_review"]) | (Image.is_validated == False))
        .order_by(Image.uploaded_at.desc())
        .all()
    )
    
    results = []
    for img in images:
        uploader = db.query(User).filter(User.user_id == img.user_id).first()
        uploader_email = uploader.email if uploader else "Unknown User"
        uploader_name = uploader.full_name if (uploader and uploader.full_name) else uploader_email

        selected_cat = db.query(Category).filter(Category.category_id == img.selected_category_id).first() if img.selected_category_id else None
        selected_category_name = selected_cat.class_name if selected_cat else "Unspecified"

        # Gather annotations
        img_annotations = []
        for ann in img.annotations:
            cat = db.query(Category).filter(Category.category_id == ann.category_id).first()
            img_annotations.append({
                "annotation_id": ann.annotation_id,
                "category_id": ann.category_id,
                "category_name": cat.class_name if cat else "Unclassified",
                "annotation_type": ann.annotation_type,
                "label_data": ann.label_data_json,
                "ai_generated": ann.ai_generated
            })
            
        results.append({
            "image_id": img.image_id,
            "original_filename": img.original_filename,
            "temp_s3_path": img.temp_s3_path,
            "uploaded_at": str(img.uploaded_at) if img.uploaded_at else None,
            "uploader_user_id": img.user_id,
            "uploader_email": uploader_email,
            "uploader_name": uploader_name,
            "selected_category_id": img.selected_category_id,
            "selected_category_name": selected_category_name,
            "ai_predicted_category": img.ai_predicted_category,
            "ai_confidence_score": img.ai_confidence_score,
            "validation_result": img.validation_result or ("AUTO_ACCEPTED" if img.status == "approved" else "NEEDS_HUMAN_REVIEW"),
            "validation_reason": img.validation_reason,
            "status": img.status,
            "is_validated": img.is_validated,
            "annotations": img_annotations
        })
        
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
        db.query(
            Category.class_name,
            func.greatest(
                Category.validated_count,
                func.count(func.distinct(Image.image_id)),
                func.count(func.distinct(Annotation.image_id))
            )
        )
        .outerjoin(Image, Category.category_id == Image.selected_category_id)
        .outerjoin(Annotation, Category.category_id == Annotation.category_id)
        .group_by(Category.category_id, Category.class_name, Category.validated_count)
        .all()
    )
    category_stats = [{"category": row[0], "count": int(row[1] or 0)} for row in category_counts]
    
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
    
    # Detailed Monthly Pipeline metrics (uploaded vs validated vs rejected)
    monthly_validated = (
        db.query(func.date_trunc('month', Image.validated_at).label('month'), func.count(Image.image_id))
        .filter(Image.is_validated == True, Image.status == "approved")
        .group_by('month')
        .order_by('month')
        .all()
    )
    monthly_val_stats = {
        (row[0].date().strftime("%Y-%m") if row[0] else None): row[1]
        for row in monthly_validated
    }

    monthly_rejected = (
        db.query(func.date_trunc('month', Image.uploaded_at).label('month'), func.count(Image.image_id))
        .filter(Image.status == "rejected")
        .group_by('month')
        .order_by('month')
        .all()
    )
    monthly_rej_stats = {
        (row[0].date().strftime("%Y-%m") if row[0] else None): row[1]
        for row in monthly_rejected
    }

    monthly_pipeline = []
    for row in monthly_uploads:
        m_str = row[0].date().strftime("%Y-%m") if row[0] else None
        if m_str:
            monthly_pipeline.append({
                "month": m_str,
                "uploaded": row[1],
                "validated": monthly_val_stats.get(m_str, 0),
                "rejected": monthly_rej_stats.get(m_str, 0)
            })

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
        db.query(User.user_id, User.email, User.full_name, User.image_count, User.reward_points)
        .filter(User.role == "user")
        .order_by(User.image_count.desc())
        .limit(10)
        .all()
    )
    contributor_stats = []
    for row in top_contributors:
        approved_count = row[3] or 0
        uploaded_count = db.query(Image).filter(Image.user_id == row[0]).count()
        contributor_stats.append({
            "user_id": row[0],
            "email": row[1],
            "full_name": row[2],
            "approved": approved_count,
            "uploads": max(uploaded_count, approved_count),
            "reward_points": row[4] or 0
        })
    
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
        "monthly_pipeline": monthly_pipeline,
        "annotation_types": annotation_types,
        "dataset_growth": growth_stats,
        "training": {
            "status_counts": status_stats,
            "average_duration_minutes": avg_duration
        },
        "top_contributors": contributor_stats
    }


@router.get("/activities", response_model=dict)
def get_recent_activities(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Aggregate and return recent system activities from the database."""
    recent_approvals = (
        db.query(Image)
        .filter(Image.status == "approved", Image.is_validated == True)
        .order_by(Image.validated_at.desc())
        .limit(10)
        .all()
    )

    recent_uploads = (
        db.query(Image)
        .filter(Image.status == "uploaded", Image.is_validated == False)
        .order_by(Image.uploaded_at.desc())
        .limit(10)
        .all()
    )

    from app.models.training import TrainingJob
    recent_jobs = (
        db.query(TrainingJob)
        .order_by(TrainingJob.started_at.desc())
        .limit(10)
        .all()
    )

    activities = []

    for img in recent_approvals:
        activities.append({
            "id": f"approve-{img.image_id}",
            "type": "approval",
            "description": f"Admin approved image {img.original_filename}.",
            "timestamp": str(img.validated_at) if img.validated_at else str(img.uploaded_at),
            "status_color": "green"
        })

    for img in recent_uploads:
        activities.append({
            "id": f"upload-{img.image_id}",
            "type": "upload",
            "description": f"New image uploaded: {img.original_filename}.",
            "timestamp": str(img.uploaded_at),
            "status_color": "blue"
        })

    for job in recent_jobs:
        status_color = "indigo" if job.status == "completed" else "amber" if job.status in ("running", "queued") else "red"
        activities.append({
            "id": f"job-{job.job_id}",
            "type": "training",
            "description": f"Retraining job {job.version} is {job.status}.",
            "timestamp": str(job.completed_at) if job.completed_at else str(job.started_at),
            "status_color": status_color
        })

    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"activities": activities[:10]}


@router.get("/health/system", response_model=dict)
def get_system_health(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Dynamically check health status of API, Database, Storage, Redis, Celery, and ML services."""
    api_status = "operational"

    db_status = "connected"
    try:
        from sqlalchemy.sql import text
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    storage_status = "connected"
    try:
        from app.config import settings
        import os
        upload_dir = settings.UPLOAD_FOLDER
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir, exist_ok=True)
        test_file = os.path.join(upload_dir, ".health_check_temp")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
    except Exception:
        storage_status = "disconnected"

    redis_status = "connected"
    try:
        import redis
        from app.config import settings
        r = redis.from_url(settings.REDIS_URL, socket_timeout=1.0)
        r.ping()
    except Exception:
        redis_status = "disconnected"

    celery_status = "running"
    try:
        from app.celery_app import celery_app
        ins = celery_app.control.inspect(timeout=1.0)
        ping_res = ins.ping()
        if not ping_res:
            celery_status = "offline"
    except Exception:
        celery_status = "offline"

    ml_status = "available"
    try:
        from app.config import settings
        import os
        if not os.path.exists(settings.YOLO_MODEL_PATH):
            ml_status = "unavailable"
    except Exception:
        ml_status = "unavailable"

    return {
        "api": api_status,
        "database": db_status,
        "storage": storage_status,
        "redis": redis_status,
        "celery": celery_status,
        "ml_service": ml_status
    }


# ---------------------------------------------------------------------------
# System Settings Endpoints
# ---------------------------------------------------------------------------

from app.models.setting import SystemSetting

@router.get("/settings", response_model=SystemSettingResponse)
def get_system_settings(db: Session = Depends(get_db)):
    """Fetch current system and ML pipeline settings."""
    setting = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    if not setting:
        setting = SystemSetting(id=1)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


@router.put("/settings", response_model=SystemSettingResponse)
def update_system_settings(
    settings_in: SystemSettingUpdate,
    db: Session = Depends(get_db)
):
    """Update system and ML pipeline settings in database."""
    setting = db.query(SystemSetting).filter(SystemSetting.id == 1).first()
    if not setting:
        setting = SystemSetting(id=1)
        db.add(setting)
        db.commit()
        db.refresh(setting)

    update_data = settings_in.model_dump(exclude_unset=True)
    for field, val in update_data.items():
        if val is not None:
            setattr(setting, field, val)

    db.commit()
    db.refresh(setting)
    return setting


