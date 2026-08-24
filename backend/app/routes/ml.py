import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.training import TrainingJob, ModelVersion
from app.models.user import User
from app.dependencies.auth import get_current_user, require_admin
from app.config import settings
from app.services.training_service import check_dataset_readiness, trigger_training_job

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "ml"}


# ---- Training Jobs ----

@router.get("/jobs")
def list_training_jobs(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    jobs = db.query(TrainingJob).order_by(TrainingJob.started_at.desc()).all()
    results = [
        {
            "job_id": j.job_id,
            "version": j.version,
            "status": j.status,
            "class_counts": j.class_counts,
            "best_model_path": j.best_model_path,
            "started_at": str(j.started_at) if j.started_at else None,
            "completed_at": str(j.completed_at) if j.completed_at else None,
        }
        for j in jobs
    ]
    return {"jobs": results}


@router.get("/jobs/{job_id}")
def get_training_job(
    job_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    job = db.query(TrainingJob).filter(TrainingJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")
    return {
        "job_id": job.job_id,
        "version": job.version,
        "status": job.status,
        "class_counts": job.class_counts,
        "best_model_path": job.best_model_path,
        "metadata_path": job.metadata_path,
        "started_at": str(job.started_at) if job.started_at else None,
        "completed_at": str(job.completed_at) if job.completed_at else None,
    }


@router.post("/train", status_code=status.HTTP_201_CREATED)
def trigger_training(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a training job if the dataset is ready and queue it for Celery execution.
    """
    ready, stats = check_dataset_readiness(db)
    if not ready:
        raise HTTPException(
            status_code=400,
            detail="Dataset not ready. Not all categories meet the validated threshold.",
        )

    # Compute next version
    job_count = db.query(TrainingJob).count()
    version = f"v{job_count + 1}"

    # Build class counts from stats
    class_counts = {s["class_name"]: s["validated_count"] for s in stats}

    job = trigger_training_job(db, version=version, class_counts=class_counts)
    if not job:
        raise HTTPException(status_code=500, detail="Failed to create training job")

    # Enqueue in Celery
    from app.tasks.training_tasks import train_model
    train_model.delay(job.job_id)

    return {
        "message": "Training job created and queued for execution.",
        "job_id": job.job_id,
        "version": job.version,
        "status": job.status,
    }


# ---- Model Versions ----

import logging
import json
import shutil
from pathlib import Path
from app.services.model_cache import YOLOModelCache

logger = logging.getLogger("ml_routes")
model_cache = YOLOModelCache()

def _enrich_model_version(db: Session, m: ModelVersion) -> dict:
    job = db.query(TrainingJob).filter(TrainingJob.job_id == m.job_id).first()
    best_model_path = job.best_model_path if job else None
    class_counts = job.class_counts if job else None
    
    metrics = None
    parameters = None
    if job and job.metadata_path and os.path.exists(job.metadata_path):
        try:
            with open(job.metadata_path, 'r') as fh:
                meta = json.load(fh)
                metrics = meta.get("metrics")
                parameters = meta.get("parameters") or {
                    "epochs": meta.get("epochs"),
                    "imgsz": meta.get("imgsz"),
                    "batch": meta.get("batch")
                }
        except Exception:
            pass
            
    return {
        "model_id": m.model_id,
        "job_id": m.job_id,
        "version": m.version,
        "is_current": m.is_current,
        "map_score": m.map_score,
        "model_path": best_model_path,
        "dataset_info": class_counts,
        "metrics": metrics,
        "parameters": parameters,
        "status": "active" if m.is_current else "inactive",
        "created_at": str(m.created_at) if m.created_at else None,
        "updated_at": str(m.updated_at) if m.updated_at else None,
    }


@router.get("/models")
def list_models(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    models = db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).all()
    results = [_enrich_model_version(db, m) for m in models]
    return {"models": results}


@router.get("/models/current")
@router.get("/models/active")
def get_current_model(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = db.query(ModelVersion).filter(ModelVersion.is_current == True).first()
    if not model:
        raise HTTPException(status_code=404, detail="No active model available")
    return _enrich_model_version(db, model)


@router.get("/models/{model_id}")
def get_model(
    model_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    model = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model version not found")
    return _enrich_model_version(db, model)


@router.post("/models/{model_id}/activate")
def activate_model(
    model_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Transactionally activate a trained model version and deactivate the previous active model.
    """
    model = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model version not found")
        
    job = db.query(TrainingJob).filter(TrainingJob.job_id == model.job_id).first()
    if not job or job.status != "completed":
        raise HTTPException(
            status_code=400,
            detail="Cannot activate model from an incomplete/failed training job"
        )
        
    if not job.best_model_path or not os.path.exists(job.best_model_path):
        raise HTTPException(
            status_code=400,
            detail="Model file is missing or invalid on disk"
        )
        
    # Transactional update: deactivate old active model(s), activate new one
    db.query(ModelVersion).filter(ModelVersion.is_current == True).update({"is_current": False})
    model.is_current = True
    db.add(model)
    db.commit()
    db.refresh(model)
    
    # Safely copy to standard settings path best.pt
    try:
        target_model_path = Path(settings.YOLO_MODEL_PATH)
        target_model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_target = target_model_path.with_suffix('.tmp')
        shutil.copy2(job.best_model_path, tmp_target)
        os.replace(tmp_target, target_model_path)
    except Exception as e:
        logger.exception(f"Failed to copy activated weights to settings path: {e}")
        raise HTTPException(status_code=500, detail="Activated weights file propagation failed")
        
    # Flush model cache so that next prediction request reloads the active model
    model_cache.reload()
    
    return {
        "message": "Model version activated successfully",
        "model_id": model.model_id,
        "version": model.version,
    }


# ---- YOLO Prediction ----

@router.post("/predict")
def predict(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """
    Run YOLO inference on an uploaded image.
    BLOCKED if no trained model (.pt file) is available.
    """
    # 1. Validate file is an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only image files are allowed for prediction."
        )

    # 2. Get active cached model
    try:
        model = model_cache.get_model()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"BLOCKED: YOLO model loading failed: {str(e)}"
        )

    if model is None:
        raise HTTPException(
            status_code=503,
            detail=f"BLOCKED: YOLO model not available at '{settings.YOLO_MODEL_PATH}'. "
                   f"A trained .pt model file is required for prediction.",
        )

    try:
        import tempfile, shutil
        suffix = os.path.splitext(file.filename or ".jpg")[1]
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        # 3. Perform inference with threshold
        results = model(tmp_path, conf=settings.YOLO_CONFIDENCE_THRESHOLD)
        os.unlink(tmp_path)

        predictions = []
        for result in results:
            for box in result.boxes:
                predictions.append({
                    "class": int(box.cls[0]),
                    "confidence": float(box.conf[0]),
                    "bbox": box.xyxy[0].tolist(),
                })

        return {"predictions": predictions, "count": len(predictions)}

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Prediction inference failed: {str(e)}"
        )
