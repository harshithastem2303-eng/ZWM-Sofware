from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.image import Image
from app.dependencies.auth import get_current_user
from app.schemas.schemas import UserProfile

router = APIRouter()
users_router = APIRouter()

@router.get("/profile", response_model=UserProfile)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/stats", response_model=dict)
def get_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    validated_images = db.query(Image).filter(Image.user_id == current_user.user_id, Image.is_validated == True).count()
    total_images = db.query(Image).filter(Image.user_id == current_user.user_id).count()

    pts = current_user.reward_points or 0
    return {
        "total_uploads": total_images,
        "validated_images": validated_images,
        "pending_images": total_images - validated_images,
        "reward_points": pts,
        "points": pts
    }

@router.get("/history", response_model=dict)
def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    images = db.query(Image).filter(Image.user_id == current_user.user_id).order_by(Image.uploaded_at.desc()).all()
    
    results = []
    for img in images:
        results.append({
            "image_id": img.image_id,
            "original_filename": img.original_filename,
            "status": img.status,
            "is_validated": img.is_validated,
            "credits_awarded": img.credits_awarded,
            "uploaded_at": img.uploaded_at
        })

    return {"history": results}

@router.get("/rewards", response_model=dict)
def get_rewards(current_user: User = Depends(get_current_user)):
    return {
        "reward_points": current_user.reward_points or 0,
        "points": current_user.reward_points or 0,
        "total_images_contributed": current_user.image_count or 0
    }

@router.get("/rewards/history", response_model=dict)
def get_reward_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.user import RewardTransaction
    from app.models.image import Image
    from app.models.category import Category
    import re

    # Cache category lookup map
    categories = {c.category_id: c.class_name for c in db.query(Category).all()}

    txs = (
        db.query(RewardTransaction)
        .filter(RewardTransaction.user_id == current_user.user_id)
        .order_by(RewardTransaction.created_at.desc())
        .all()
    )

    results = []

    if txs:
        for t in txs:
            cat_name = None
            img = None

            if t.image_id:
                img = db.query(Image).filter(Image.image_id == t.image_id).first()
            if not img:
                m = re.search(r'([A-Za-z0-9_.\-]+\.(?:jpg|jpeg|png|webp))', t.description or '', re.IGNORECASE)
                if m:
                    img = db.query(Image).filter(Image.original_filename == m.group(1)).first()

            if img:
                if img.selected_category_id and img.selected_category_id in categories:
                    cat_name = categories[img.selected_category_id]
                elif img.ai_predicted_category:
                    cat_name = img.ai_predicted_category.replace('_', ' ').title()

            raw_desc = t.description or "Reward Transaction"
            desc = raw_desc
            if cat_name:
                if "annotation" in raw_desc.lower():
                    desc = f"{cat_name} Annotation Verified"
                elif "upload" in raw_desc.lower() or "validation" in raw_desc.lower() or "approved" in raw_desc.lower():
                    desc = f"Verified {cat_name} Upload"
                else:
                    desc = f"{cat_name} Contribution Bonus"
            elif "annotation" in raw_desc.lower():
                desc = "Dataset Annotation Verified"
            elif "upload" in raw_desc.lower() or "validation" in raw_desc.lower() or "approved" in raw_desc.lower():
                desc = "Verified Waste Photo Upload"

            results.append({
                "transaction_id": t.transaction_id,
                "image_id": t.image_id if t.image_id else (img.image_id if img else None),
                "points": t.points,
                "class_name": cat_name,
                "description": desc,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })
    else:
        # Fallback: Generate transactions strictly for this user based on their uploaded images
        user_images = (
            db.query(Image)
            .filter(Image.user_id == current_user.user_id)
            .order_by(Image.uploaded_at.desc())
            .all()
        )
        for img in user_images:
            cat_name = None
            if img.selected_category_id and img.selected_category_id in categories:
                cat_name = categories[img.selected_category_id]
            elif img.ai_predicted_category:
                cat_name = img.ai_predicted_category.replace('_', ' ').title()

            class_label = cat_name or "Waste Photo"
            pts = img.credits_awarded or (15 if img.is_validated else 10)
            results.append({
                "transaction_id": f"img-{img.image_id}",
                "image_id": img.image_id,
                "points": pts,
                "class_name": cat_name,
                "description": f"Verified {class_label} Upload" if img.is_validated else f"{class_label} Upload",
                "created_at": img.uploaded_at.isoformat() if img.uploaded_at else None,
            })

        if not results and (current_user.reward_points or 0) > 0:
            results.append({
                "transaction_id": "welcome-bonus",
                "image_id": None,
                "points": current_user.reward_points,
                "class_name": "Bonus",
                "description": "Contributor Welcome Bonus",
                "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            })

    return {"history": results}

@users_router.get("/me/dashboard", response_model=dict)
def get_user_dashboard(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total_submissions = db.query(Image).filter(Image.user_id == current_user.user_id).count()

    higher_users = db.query(User).filter(User.reward_points > current_user.reward_points).count()
    rank = higher_users + 1

    recent_imgs = (
        db.query(Image)
        .filter(Image.user_id == current_user.user_id)
        .order_by(Image.uploaded_at.desc())
        .limit(10)
        .all()
    )

    recent_submissions = [
        {
            "id": img.image_id,
            "filename": img.original_filename,
            "status": img.status or "uploaded",
            "is_validated": bool(img.is_validated),
            "credits_awarded": img.credits_awarded or 0,
            "uploaded_at": img.uploaded_at.isoformat() if img.uploaded_at else None,
        }
        for img in recent_imgs
    ]

    pts = current_user.reward_points or 0
    return {
        "user": {
            "id": current_user.user_id,
            "email": current_user.email,
            "full_name": current_user.full_name or ""
        },
        "stats": {
            "total_submissions": total_submissions,
            "points": pts,
            "reward_points": pts,
            "rank": rank
        },
        "recent_submissions": recent_submissions
    }

