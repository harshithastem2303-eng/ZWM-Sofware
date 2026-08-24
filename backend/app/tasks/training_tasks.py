import logging
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from celery.exceptions import MaxRetriesExceededError

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.training import TrainingJob, ModelVersion
from app.models.category import Category
from app.config import settings

# Reuse core functions from training_worker
from worker.training_worker import (
    build_dataset_from_permanent,
    run_ultralytics_training,
    MODELS_DIR,
    RUNS_ROOT,
)

logger = logging.getLogger("celery_training")

def _mark_job_failed(db, job, error_msg: str):
    """Safely mark a job as failed and write error metadata."""
    try:
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc)
        
        # Save metadata containing error info
        metadata = {
            "job_id": job.job_id,
            "version": job.version,
            "status": "failed",
            "error": error_msg,
            "failed_at": str(job.completed_at),
        }
        metadata_path = MODELS_DIR / f"{job.version}_{job.job_id[:8]}_metadata.json"
        with open(metadata_path, 'w') as mh:
            json.dump(metadata, mh)
        job.metadata_path = str(metadata_path)
        
        db.add(job)
        db.commit()
        logger.info(f"celery_training: Marked job {job.job_id} as failed in database.")
    except Exception as e:
        logger.exception(f"Failed to mark job {job.job_id} as failed: {e}")
        db.rollback()

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def train_model(self, training_job_id: str):
    logger.info(f"celery_training: Task received for job {training_job_id}", extra={"job_id": training_job_id, "status": "queued"})
    
    db = SessionLocal()
    try:
        # Atomic lock / claim job using row locking with skip_locked
        job = (
            db.query(TrainingJob)
            .filter(TrainingJob.job_id == training_job_id)
            .with_for_update(skip_locked=True)
            .first()
        )
        
        if not job:
            logger.warning(f"celery_training: Job {training_job_id} not found or locked by another worker.")
            return f"Job {training_job_id} skipped (not found or locked)"
            
        if job.status != "queued":
            logger.warning(f"celery_training: Job {training_job_id} is already in state '{job.status}'. Skipping.")
            return f"Job {training_job_id} skipped (state is {job.status})"
            
        # Transition to RUNNING
        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        logger.info(f"celery_training: Claimed job {training_job_id} -> status=running", extra={"job_id": training_job_id, "status": "started"})
        
        # Prepare datasets
        logger.info(f"celery_training: Preparing dataset for job {training_job_id}", extra={"job_id": training_job_id, "status": "dataset preparation"})
        dataset_dir = Path(settings.UPLOAD_FOLDER).parent / "worker" / "datasets" / training_job_id
        if dataset_dir.exists():
            shutil.rmtree(dataset_dir)
        dataset_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            data_yaml, nc, names = build_dataset_from_permanent(dataset_dir)
        except Exception as e:
            logger.exception(f"celery_training: Dataset preparation failed for job {training_job_id}")
            _mark_job_failed(db, job, f"Dataset preparation failed: {str(e)}")
            return f"Job {training_job_id} failed during dataset preparation"
            
        # YOLO training
        logger.info(f"celery_training: YOLO training started for job {training_job_id}", extra={"job_id": training_job_id, "status": "training started"})
        run_name = f"train_{job.version}_{training_job_id[:8]}"
        
        try:
            best_pt, metrics = run_ultralytics_training(data_yaml, run_name)
        except Exception as e:
            logger.exception(f"celery_training: YOLO training crashed for job {training_job_id}")
            _mark_job_failed(db, job, f"Training process crashed: {str(e)}")
            return f"Job {training_job_id} failed during YOLO training"
            
        if not best_pt or not best_pt.exists():
            logger.error(f"celery_training: Training finished but best.pt not found for job {training_job_id}")
            _mark_job_failed(db, job, "Training completed but weights file (best.pt) was missing.")
            return f"Job {training_job_id} failed: missing best.pt"
            
        # Save model and copy weights
        dest_name = f"{job.version}_{training_job_id[:8]}_best.pt"
        dest_path = MODELS_DIR / dest_name
        try:
            shutil.copy2(best_pt, dest_path)
            logger.info(f"celery_training: Saved model weights to {dest_path}")
        except Exception as e:
            logger.exception(f"celery_training: Failed to copy best.pt for job {training_job_id}")
            _mark_job_failed(db, job, f"Failed to save final weights: {str(e)}")
            return f"Job {training_job_id} failed during weights saving"
            
        # Atomically update the configured active model path (best-effort)
        try:
            target_model_path = Path(settings.YOLO_MODEL_PATH)
            target_model_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_target = target_model_path.with_suffix('.tmp')
            shutil.copy2(dest_path, tmp_target)
            os.replace(tmp_target, target_model_path)
        except Exception as e:
            logger.warning(f"celery_training: Failed to update active YOLO path: {e}")
            
        # Update DB models versioning
        try:
            # Unset current model version
            db.query(ModelVersion).filter(ModelVersion.is_current == True).update({"is_current": False})
            
            new_model = ModelVersion(
                job_id=job.job_id,
                version=job.version,
                is_current=True,
                map_score=(metrics.get('map50') if isinstance(metrics, dict) else None),
            )
            db.add(new_model)
            
            # Save metadata file
            metadata = {
                "job_id": job.job_id,
                "version": job.version,
                "run_name": run_name,
                "metrics": metrics,
                "data_yaml": str(data_yaml),
                "completed_at": str(datetime.now(timezone.utc)),
            }
            metadata_path = MODELS_DIR / f"{job.version}_{training_job_id[:8]}_metadata.json"
            with open(metadata_path, 'w') as mh:
                json.dump(metadata, mh)
            job.metadata_path = str(metadata_path)
            
            job.best_model_path = str(dest_path)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            
            db.add(job)
            db.commit()
            logger.info(f"celery_training: Training completed and model saved for job {training_job_id}", extra={"job_id": training_job_id, "status": "completed"})
        except SQLAlchemyError as db_err:
            db.rollback()
            logger.exception(f"celery_training: Database error when saving metrics/version for job {training_job_id}")
            _mark_job_failed(db, job, f"Database finalization failed: {str(db_err)}")
            return f"Job {training_job_id} failed during database finalization"
            
        # Cleanup dataset folder
        try:
            if dataset_dir.exists():
                shutil.rmtree(dataset_dir)
        except Exception:
            pass
            
        return f"Job {training_job_id} completed successfully"
        
    except (OperationalError, ConnectionError, TimeoutError) as exc:
        logger.warning(f"celery_training: Retrying job {training_job_id} due to transient error: {exc}", extra={"job_id": training_job_id, "status": "retrying"})
        db.rollback()
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError as max_exc:
            logger.error(f"celery_training: Max retries exceeded for job {training_job_id}", extra={"job_id": training_job_id, "status": "failed"})
            fresh_db = SessionLocal()
            try:
                job = fresh_db.query(TrainingJob).filter(TrainingJob.job_id == training_job_id).first()
                if job:
                    _mark_job_failed(fresh_db, job, f"Transient retries exhausted: {str(exc)}")
            finally:
                fresh_db.close()
            raise max_exc
            
    except Exception as exc:
        logger.exception(f"celery_training: Non-retryable error during job {training_job_id}: {exc}", extra={"job_id": training_job_id, "status": "failed"})
        db.rollback()
        fresh_db = SessionLocal()
        try:
            job = fresh_db.query(TrainingJob).filter(TrainingJob.job_id == training_job_id).first()
            if job:
                _mark_job_failed(fresh_db, job, str(exc))
        finally:
            fresh_db.close()
        return f"Job {training_job_id} failed: {str(exc)}"
        
    finally:
        db.close()
