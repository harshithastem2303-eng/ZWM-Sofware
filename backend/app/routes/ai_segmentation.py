import os
import tempfile
import base64
import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.image import Image
from app.models.user import User
from app.dependencies.auth import get_current_user
from app.services.ai_detector import ai_detector_instance
from app.config import settings

logger = logging.getLogger("ai_segmentation_routes")

router = APIRouter()


class AIPolygonClickRequest(BaseModel):
    image_id: Optional[str] = Field(None, description="Database Image ID")
    image: Optional[str] = Field(None, description="Base64 encoded image string if image_id is not provided")
    x: int = Field(..., description="Canvas X coordinate of click in original image resolution")
    y: int = Field(..., description="Canvas Y coordinate of click in original image resolution")
    conf: float = Field(0.25, description="Confidence threshold for segmentation")


class AISegmentRequest(BaseModel):
    image_id: Optional[str] = Field(None, description="Database Image ID")
    image: Optional[str] = Field(None, description="Base64 encoded image string")
    conf: float = Field(0.25, description="Confidence threshold")


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "ai_segmentation"}


def _resolve_image_path(image_id: Optional[str], image_b64: Optional[str], db: Session) -> str:
    """Helper to resolve local file path from image_id or base64 payload."""
    if image_id:
        img_rec = db.query(Image).filter(Image.image_id == image_id).first()
        if img_rec:
            path = img_rec.permanent_s3_path or img_rec.temp_s3_path
            if path and os.path.exists(path):
                return path

    if image_b64:
        try:
            if "," in image_b64:
                header, encoded = image_b64.split(",", 1)
            else:
                encoded = image_b64

            data = base64.b64decode(encoded)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            tmp.write(data)
            tmp.close()
            return tmp.name
        except Exception as e:
            logger.error(f"Failed to decode base64 image data: {e}")

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Image file not found on server or invalid base64 data provided."
    )


@router.post("/polygon-click")
def segment_from_click(
    payload: AIPolygonClickRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Perform AI polygon auto-segmentation at canvas click coordinates (x, y).
    Returns coordinates in ORIGINAL IMAGE RESOLUTION space.
    """
    image_path = _resolve_image_path(payload.image_id, payload.image, db)
    is_temp = payload.image is not None and not payload.image_id

    try:
        polygon_res = ai_detector_instance.segment_from_click(
            image_path=image_path,
            x=payload.x,
            y=payload.y,
            conf=payload.conf,
        )

        if not polygon_res or not polygon_res.get("points"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract polygon contour at specified click location."
            )

        points_list = polygon_res.get("points", [])
        poly_data = {
            "points": points_list,
            "bbox": polygon_res.get("bbox"),
            "class_name": polygon_res.get("class_name", "Waste Object"),
            "confidence": polygon_res.get("confidence", 0.95),
        }

        return {
            "success": True,
            "status": "success",
            "image_id": payload.image_id,
            "ai_generated": True,
            "polygon": poly_data,
            "points": points_list,
            "raw_polygon": polygon_res,
            "coordinate_space": "original_image",
            "x": payload.x,
            "y": payload.y,
        }
    finally:
        if is_temp and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except Exception:
                pass


@router.post("/segment")
def segment_full_image(
    payload: AISegmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Perform full image AI instance segmentation and return all detected polygon shapes.
    """
    image_path = _resolve_image_path(payload.image_id, payload.image, db)
    is_temp = payload.image is not None and not payload.image_id

    try:
        polygons = ai_detector_instance.segment_image(
            image_path=image_path,
            conf=payload.conf,
        )

        return {
            "success": True,
            "status": "success",
            "image_id": payload.image_id,
            "ai_generated": True,
            "count": len(polygons),
            "polygons": polygons,
            "coordinate_space": "original_image",
        }
    finally:
        if is_temp and os.path.exists(image_path):
            try:
                os.unlink(image_path)
            except Exception:
                pass
