"""
Category routes.

GET /api/categories/active  - Fetch active admin-created categories for user upload page
GET /api/categories         - Fetch categories (optional active_only filter)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category
from app.models.image import Image
from app.schemas.schemas import CategoryResponse

router = APIRouter()


@router.get("/active", response_model=dict)
def get_active_categories(db: Session = Depends(get_db)):
    """
    Fetch all active waste classes created by Admin.
    Used by User Upload Page to dynamically populate category selectors.
    """
    categories = (
        db.query(Category)
        .filter(Category.is_active == True)
        .order_by(Category.class_name.asc())
        .all()
    )
    
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


@router.get("/", response_model=dict)
def list_categories(active_only: bool = False, db: Session = Depends(get_db)):
    """List categories with optional active_only filter."""
    query = db.query(Category)
    if active_only:
        query = query.filter(Category.is_active == True)
        
    categories = query.order_by(Category.class_name.asc()).all()
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
