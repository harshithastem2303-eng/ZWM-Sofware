from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.image import Image
from app.dependencies.auth import get_current_user
from app.schemas.schemas import UserProfile

router = APIRouter()

@router.get("/profile", response_model=UserProfile)
def get_profile(current_user: User = Depends(get_current_user)):
    return current_user

@router.get("/stats", response_model=dict)
def get_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    validated_images = db.query(Image).filter(Image.user_id == current_user.user_id, Image.is_validated == True).count()
    total_images = db.query(Image).filter(Image.user_id == current_user.user_id).count()

    return {
        "total_uploads": total_images,
        "validated_images": validated_images,
        "pending_images": total_images - validated_images,
        "reward_points": current_user.reward_points
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
        "reward_points": current_user.reward_points,
        "total_images_contributed": current_user.image_count
    }

@router.get("/rewards/history", response_model=dict)
def get_reward_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models.user import RewardTransaction
    txs = db.query(RewardTransaction).filter(RewardTransaction.user_id == current_user.user_id).order_by(RewardTransaction.created_at.desc()).all()
    results = [
        {
            "transaction_id": t.transaction_id,
            "image_id": t.image_id,
            "points": t.points,
            "description": t.description,
            "created_at": t.created_at
        }
        for t in txs
    ]
    return {"history": results}
