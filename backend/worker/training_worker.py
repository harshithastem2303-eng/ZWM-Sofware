"""
Training worker for ZWM project.

Usage:
    # Run once (process a single queued job and exit):
    python worker/training_worker.py --once

    # Run continuously (poll every N seconds):
    python worker/training_worker.py

Notes:
- Uses the project's SQLAlchemy SessionLocal and TrainingJob/ModelVersion models.
- Prepares a local YOLO dataset under worker/datasets/{job_id} from uploads/permanent/*
- Calls ultralytics.YOLO.train(...) to start training (this requires ultralytics installed and GPU for reasonable speed).
- After training completes, searches for best.pt under runs/ and copies it to backend/models/{version}_{job_id}_best.pt
- Updates TrainingJob and creates a ModelVersion row; promotes the new model to is_current=True and clears previous current model.

This worker is intentionally simple for development use.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.models.training import TrainingJob, ModelVersion
from app.models.image import Image
from app.models.category import Category

logger = logging.getLogger("training_worker")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Where to place trained models locally (development)
MODELS_DIR = Path(settings.YOLO_MODEL_PATH).resolve().parent
RUNS_ROOT = Path.cwd() / "runs"
WORKER_ROOT = Path(__file__).resolve().parent
DATASETS_ROOT = WORKER_ROOT / "datasets"
DATASETS_ROOT.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def claim_queued_job(db) -> Optional[TrainingJob]:
    """Claim a single queued job atomically. Returns the TrainingJob or None."""
    try:
        # Try optimistic locking (Postgres): SELECT ... FOR UPDATE SKIP LOCKED
        q = db.query(TrainingJob).filter(TrainingJob.status == "queued")
        job = q.with_for_update(skip_locked=True).first()
    except Exception:
        # Fallback: simple select
        job = db.query(TrainingJob).filter(TrainingJob.status == "queued").first()

    if not job:
        return None

    # Mark as running and set started_at
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Claimed job %s -> running", job.job_id)
    return job


def build_dataset_from_permanent(dest_dir: Path) -> Tuple[Path, int, List[str]]:
    """
    Scan settings.UPLOAD_FOLDER/permanent and build YOLO-style dataset under dest_dir.
    Returns (data_yaml_path, nc, names).
    """
    uploads_root = Path(settings.UPLOAD_FOLDER)
    perm_root = uploads_root / "permanent"
    if not perm_root.exists():
        raise FileNotFoundError(f"Permanent uploads directory not found: {perm_root}")

    images = []  # list of (img_path, txt_path)
    for user_dir in perm_root.iterdir():
        if not user_dir.is_dir():
            continue
        for f in user_dir.iterdir():
            if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                img = f
                txt = f.with_suffix('.txt')
                if txt.exists():
                    images.append((img, txt))

    if not images:
        raise RuntimeError("No permanent images with YOLO .txt files found in uploads/permanent")

    # Read categories and build names list
    db = SessionLocal()
    try:
        cats = db.query(Category).order_by(Category.class_code).all()
        names = [c.class_name for c in cats]
        nc = len(names)
    finally:
        db.close()

    # Create train/val split (80/20)
    images.sort()  # deterministic
    split = int(len(images) * 0.8)
    train = images[:split]
    val = images[split:]

    # Create destination structure
    imgs_train = dest_dir / "images" / "train"
    imgs_val = dest_dir / "images" / "val"
    labels_train = dest_dir / "labels" / "train"
    labels_val = dest_dir / "labels" / "val"
    for p in (imgs_train, imgs_val, labels_train, labels_val):
        p.mkdir(parents=True, exist_ok=True)

    def copy_set(items, imgs_dest, labels_dest):
        for img_path, txt_path in items:
            dst_img = imgs_dest / img_path.name
            dst_txt = labels_dest / txt_path.name
            shutil.copy2(img_path, dst_img)
            shutil.copy2(txt_path, dst_txt)

    copy_set(train, imgs_train, labels_train)
    copy_set(val, imgs_val, labels_val)

    # Write data.yaml
    data_yaml = dest_dir / "data.yaml"
    content = {
        "path": str(dest_dir),
        "train": "images/train",
        "val": "images/val",
        "nc": nc,
        "names": names,
    }
    with open(data_yaml, "w") as fh:
        json.dump(content, fh)

    return data_yaml, nc, names


def find_best_pt(runs_root: Path) -> Optional[Path]:
    """Search runs/ for the most recently modified best.pt file."""
    best_files = list(runs_root.rglob("**/weights/best.pt"))
    if not best_files:
        # also check older ultralytics paths
        best_files = list(runs_root.rglob("**/best.pt"))
    if not best_files:
        return None
    best_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return best_files[0]


def run_ultralytics_training(data_yaml: Path, run_name: str, epochs: int = 50, imgsz: int = 640) -> Tuple[Optional[Path], Dict]:
    """
    Run ultralytics YOLO training. Returns (best_pt_path, metrics_dict)
    The metrics dict may include mAP if ultralytics exposes it; otherwise empty.
    """
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        logger.exception("ultralytics not installed: %s", exc)
        raise

    # Use a small default model if not configured
    model_name = getattr(settings, 'YOLO_TRAINING_MODEL', 'yolov8n.pt')
    logger.info("Starting training: model=%s data=%s epochs=%s imgsz=%s", model_name, data_yaml, epochs, imgsz)
    model = YOLO(model_name)

    # Train; the ultralytics API will save runs under ./runs
    result = model.train(data=str(data_yaml), epochs=epochs, imgsz=imgsz, name=run_name, exist_ok=True)

    # Attempt to extract metrics (may vary by ultralytics version)
    metrics = {}
    try:
        # result may be a list or object; search return for 'metrics' or 'mAP'
        if hasattr(result, 'metrics'):
            metrics = getattr(result, 'metrics') or {}
        elif isinstance(result, list) and len(result) > 0 and hasattr(result[0], 'metrics'):
            metrics = getattr(result[0], 'metrics') or {}
    except Exception:
        metrics = {}

    best = find_best_pt(RUNS_ROOT)
    return best, metrics


def process_job_once() -> bool:
    """Process a single queued job. Returns True if a job was processed."""
    db = SessionLocal()
    try:
        job = claim_queued_job(db)
        if not job:
            logger.info("No queued job found")
            return False

        job_id = job.job_id
        run_name = f"train_{job.version}_{job_id[:8]}"
        dataset_dir = DATASETS_ROOT / job_id
        if dataset_dir.exists():
            shutil.rmtree(dataset_dir)
        dataset_dir.mkdir(parents=True, exist_ok=True)

        # Prepare dataset
        try:
            data_yaml, nc, names = build_dataset_from_permanent(dataset_dir)
        except Exception as exc:
            logger.exception("Dataset preparation failed: %s", exc)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            return True

        # Run training
        try:
            best_pt, metrics = run_ultralytics_training(data_yaml, run_name)
        except Exception as exc:
            logger.exception("Training failed for job %s: %s", job_id, exc)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            return True

        if not best_pt or not best_pt.exists():
            logger.error("Training finished but no best.pt found for job %s", job_id)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            return True

        # Copy best.pt into models directory with a deterministic name
        dest_name = f"{job.version}_{job_id[:8]}_best.pt"
        dest_path = MODELS_DIR / dest_name
        try:
            shutil.copy2(best_pt, dest_path)
        except Exception as exc:
            logger.exception("Failed to copy best.pt to models dir: %s", exc)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()
            return True

        # Also atomically update the configured YOLO_MODEL_PATH so prediction uses the new model
        try:
            target_model_path = Path(settings.YOLO_MODEL_PATH)
            target_model_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_target = target_model_path.with_suffix('.tmp')
            shutil.copy2(dest_path, tmp_target)
            os.replace(tmp_target, target_model_path)
        except Exception as exc:
            logger.exception("Failed to update YOLO_MODEL_PATH (%s): %s", settings.YOLO_MODEL_PATH, exc)
            # non-fatal: proceed but record the issue in metadata

        # Create ModelVersion and update job within a transactional update
        try:
            # unset previous current model in a single UPDATE to avoid race conditions
            db.query(ModelVersion).filter(ModelVersion.is_current == True).update({"is_current": False})

            new_model = ModelVersion(
                job_id=job.job_id,
                version=job.version,
                is_current=True,
                map_score=(metrics.get('map50') if isinstance(metrics, dict) else None),
            )
            db.add(new_model)

            # Save metadata (metrics, run info) alongside the model
            try:
                metadata = {
                    "job_id": job.job_id,
                    "version": job.version,
                    "run_name": run_name,
                    "metrics": metrics,
                    "data_yaml": str(data_yaml),
                }
                metadata_path = MODELS_DIR / f"{job.version}_{job_id[:8]}_metadata.json"
                with open(metadata_path, 'w') as mh:
                    json.dump(metadata, mh)
                job.metadata_path = str(metadata_path)
            except Exception as meta_exc:
                logger.exception("Failed to write metadata for job %s: %s", job_id, meta_exc)

            job.best_model_path = str(dest_path)
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)

            db.add(job)
            db.commit()
            db.refresh(new_model)
            logger.info("Job %s completed successfully; model saved to %s", job_id, dest_path)
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("DB update failed for job %s: %s", job_id, exc)
            job.status = "failed"
            job.completed_at = datetime.now(timezone.utc)
            db.add(job)
            db.commit()

        # Cleanup dataset_dir to save disk space (best-effort)
        try:
            if dataset_dir.exists():
                shutil.rmtree(dataset_dir)
        except Exception:
            logger.warning("Failed to remove dataset dir %s (non-fatal)", dataset_dir)

        return True
    finally:
        db.close()


def run_loop(poll_interval: int = 30):
    logger.warning("DEPRECATION WARNING: Continuous DB polling via training_worker.py is deprecated in favor of Celery. Running for legacy support.")
    logger.info("Starting training worker loop (poll_interval=%s seconds)", poll_interval)
    try:
        while True:
            processed = process_job_once()
            if not processed:
                time.sleep(poll_interval)
    except KeyboardInterrupt:
        logger.info("Training worker interrupted by user")


if __name__ == '__main__':
    logger.warning("DEPRECATION WARNING: Running training_worker.py direct execution is deprecated in favor of Celery.")
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Process only a single queued job and exit')
    parser.add_argument('--poll', type=int, default=30, help='Poll interval in seconds for loop mode')
    args = parser.parse_args()

    if args.once:
        process_job_once()
    else:
        run_loop(args.poll)
