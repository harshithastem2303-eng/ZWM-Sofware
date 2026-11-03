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


def _record_segmentation(db: Session, source: str, image_id: Optional[str], user: User, polygons: list,
                         status_: str, params: dict) -> str:
    """
    Block A6.1: immutable provenance of a segmentation-assist inference. The image is
    linked only when the request named an existing image; base64-only requests are
    recorded without an image (never a fabricated id). Fails closed: if the record
    cannot be stored, the suggestions are not returned.
    """
    from app.services import prediction_service as ps
    linked = image_id if image_id and db.query(Image.image_id).filter(Image.image_id == image_id).first() else None
    detections = ps.segmentation_detections(polygons)
    engines = sorted({d["engine"] for d in detections if d.get("engine")})
    rec = ps.new_record(source=source, status=status_, identity=ps.segmentation_identity(ai_detector_instance),
                        detections=detections, confidence_is_model_score=False, image_id=linked,
                        requested_by=user.user_id, engine=",".join(engines) or None,
                        request_params={**params, "input": "image_id" if linked else "base64"})
    db.add(rec)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("PREDICTION_RECORD_FAILED | source=%s", source)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Prediction could not be recorded")
    return rec.prediction_id


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
    # Block A6.0: record (and commit) that AI suggestions were served for this image
    # BEFORE returning them; its labels then need an administrator review.
    from app.services.training_dataset_service import record_ai_suggestion
    record_ai_suggestion(db, payload.image_id)

    try:
        polygon_res = ai_detector_instance.segment_from_click(
            image_path=image_path,
            x=payload.x,
            y=payload.y,
            conf=payload.conf,
        )

        params = {"x": payload.x, "y": payload.y, "conf": payload.conf}
        if not polygon_res or not polygon_res.get("points"):
            _record_segmentation(db, "ai_polygon_click", payload.image_id, current_user, [], "no_result", params)
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

        prediction_id = _record_segmentation(db, "ai_polygon_click", payload.image_id, current_user,
                                             [polygon_res], "succeeded", params)
        return {
            "success": True,
            "status": "success",
            "image_id": payload.image_id,
            "ai_generated": True,
            "prediction_id": prediction_id,
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
    from app.services.training_dataset_service import record_ai_suggestion
    record_ai_suggestion(db, payload.image_id)                     # Block A6.0 (see segment_from_click)

    try:
        polygons = ai_detector_instance.segment_image(
            image_path=image_path,
            conf=payload.conf,
        )

        prediction_id = _record_segmentation(db, "ai_segment", payload.image_id, current_user, polygons,
                                             "succeeded" if polygons else "no_result", {"conf": payload.conf})
        return {
            "success": True,
            "status": "success",
            "image_id": payload.image_id,
            "ai_generated": True,
            "prediction_id": prediction_id,
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
