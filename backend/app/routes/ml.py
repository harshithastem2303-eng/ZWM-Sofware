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
    Create a training job if the dataset is ready.
    BLOCKED: Actual training requires external infrastructure (GPU, dataset on disk).
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

    return {
        "message": "Training job created. Note: actual training requires external infrastructure.",
        "job_id": job.job_id,
        "version": job.version,
        "status": job.status,
    }


# ---- Model Versions ----

@router.get("/models")
def list_models(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    models = db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).all()
    results = [
        {
            "model_id": m.model_id,
            "job_id": m.job_id,
            "version": m.version,
            "is_current": m.is_current,
            "map_score": m.map_score,
            "created_at": str(m.created_at) if m.created_at else None,
        }
        for m in models
    ]
    return {"models": results}


@router.get("/models/current")
def get_current_model(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    model = db.query(ModelVersion).filter(ModelVersion.is_current == True).first()
    if not model:
        raise HTTPException(status_code=404, detail="No current model available")
    return {
        "model_id": model.model_id,
        "job_id": model.job_id,
        "version": model.version,
        "is_current": model.is_current,
        "map_score": model.map_score,
        "created_at": str(model.created_at) if model.created_at else None,
    }


@router.get("/models/{model_id}")
def get_model(
    model_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    model = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model version not found")
    return {
        "model_id": model.model_id,
        "job_id": model.job_id,
        "version": model.version,
        "is_current": model.is_current,
        "map_score": model.map_score,
        "created_at": str(model.created_at) if model.created_at else None,
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
    model_path = settings.YOLO_MODEL_PATH
    if not os.path.exists(model_path):
        raise HTTPException(
            status_code=503,
            detail=f"BLOCKED: YOLO model not available at '{model_path}'. "
                   f"A trained .pt model file is required for prediction.",
        )

    try:
        from ultralytics import YOLO

        model = YOLO(model_path)
        import tempfile, shutil
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file.filename or ".jpg")[1], delete=False) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name

        results = model(tmp_path)
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

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="BLOCKED: ultralytics package not available for YOLO inference.",
        )
    except Exception as e:
        # Map model-load / corrupted-checkpoint errors to 503 (service blocked)
        import pickle
        err_text = str(e).lower()
        if isinstance(e, (pickle.UnpicklingError, EOFError)) or "not a loadable checkpoint" in err_text or "pickle data was truncated" in err_text:
            raise HTTPException(
                status_code=503,
                detail=(
                    "BLOCKED: YOLO model file is missing or invalid. "
                    "A valid .pt model is required for prediction."
                ),
            )
        # Fallback: internal server error for unexpected failures
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
