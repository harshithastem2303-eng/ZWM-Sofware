"""
Background cleanup worker for expired temporary images.

Uses APScheduler to run run_cleanup() every CLEANUP_INTERVAL_HOURS.
Registered at FastAPI startup / shutdown via lifespan context manager.

Usage (in main.py):
    from app.services.cleanup_worker import start_scheduler, stop_scheduler
"""
import functools
import logging
import os
import socket
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.lifecycle_service import run_cleanup

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


# ---------------------------------------------------------------------------
# Persisted scheduler heartbeats (Block A5)
# ---------------------------------------------------------------------------

def _process_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def _beat(job_name: str, interval_seconds: int, finished: bool, status: str,
          error: str | None = None, duration: float | None = None) -> None:
    """Upsert this job's heartbeat in its own session; never lets monitoring break the job."""
    from app.models.training import SchedulerHeartbeat

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        row = db.get(SchedulerHeartbeat, job_name)
        if row is None:
            row = SchedulerHeartbeat(job_name=job_name, run_count=0, consecutive_failures=0,
                                     interval_seconds=interval_seconds)
            db.add(row)
        row.interval_seconds = interval_seconds
        row.process_id = _process_id()
        row.last_status = status
        row.updated_at = now
        if finished:
            row.last_finished_at = now
            row.last_duration_seconds = duration
            row.last_error = error
            row.run_count = (row.run_count or 0) + 1
            row.consecutive_failures = 0 if status == "ok" else (row.consecutive_failures or 0) + 1
        else:
            row.last_started_at = now
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Scheduler heartbeat for %s could not be recorded: %s", job_name, type(exc).__name__)
    finally:
        db.close()


def _tracked(job_name: str, interval_seconds):
    """Record start/finish/status/duration of every run; errors are recorded, logged and contained."""
    def decorate(fn):
        @functools.wraps(fn)
        def run() -> None:
            interval = int(interval_seconds())
            _beat(job_name, interval, finished=False, status="running")
            started = time.monotonic()
            try:
                fn()
            except Exception as exc:
                logger.error("Scheduled job %s raised an exception: %s", job_name, exc)
                _beat(job_name, interval, finished=True, status="error",
                      error=f"{type(exc).__name__}: {str(exc)[:400]}", duration=round(time.monotonic() - started, 3))
                return
            _beat(job_name, interval, finished=True, status="ok", duration=round(time.monotonic() - started, 3))
        return run
    return decorate


SCHEDULER_JOBS = {
    "image_cleanup": lambda: settings.CLEANUP_INTERVAL_HOURS * 3600,
    "training_dispatch": lambda: settings.TRAINING_DISPATCH_INTERVAL_MINUTES * 60,
    "deployment_recovery": lambda: settings.DEPLOYMENT_RECOVERY_INTERVAL_SECONDS,
}


@_tracked("image_cleanup", SCHEDULER_JOBS["image_cleanup"])
def _cleanup_job() -> None:
    """Periodic job: open a DB session, run cleanup, close session."""
    db = SessionLocal()
    try:
        stats = run_cleanup(db)
        logger.info(
            "Scheduled cleanup complete | cleaned=%d errors=%d skipped=%d",
            stats["cleaned"], stats["errors"], stats["skipped"],
        )
    finally:
        db.close()


@_tracked("training_dispatch", SCHEDULER_JOBS["training_dispatch"])
def _training_dispatch_job() -> None:
    """Periodic outbox sweep: queue snapshot training jobs whose delivery failed or was lost."""
    from app.services.training_pipeline_service import dispatch_pending_training_jobs

    db = SessionLocal()
    try:
        results = dispatch_pending_training_jobs(db)
        from app.services.model_evaluation_service import dispatch_pending_evaluations
        results += dispatch_pending_evaluations(db)
        if results:
            logger.info("Scheduled training/evaluation dispatch | %s", results)
    finally:
        db.close()


@_tracked("deployment_recovery", SCHEDULER_JOBS["deployment_recovery"])
def _deployment_recovery_job() -> None:
    """Block A4.1: recover expired activations/rollbacks and reconcile the serving file."""
    from app.services.model_deployment_service import run_deployment_maintenance

    db = SessionLocal()
    try:
        result = run_deployment_maintenance(db)
        if result["recovered"] or result["consistency"].get("action"):
            logger.warning("Scheduled deployment maintenance | %s", result)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def start_scheduler() -> None:
    """Start the background scheduler. Called at FastAPI startup."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return  # already started (e.g. hot-reload)

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _cleanup_job,
        trigger=IntervalTrigger(hours=settings.CLEANUP_INTERVAL_HOURS),
        id="image_cleanup",
        name="Expired temporary image cleanup",
        replace_existing=True,
    )
    _scheduler.add_job(
        _training_dispatch_job,
        trigger=IntervalTrigger(minutes=settings.TRAINING_DISPATCH_INTERVAL_MINUTES),
        id="training_dispatch",
        name="Snapshot training job outbox sweep",
        replace_existing=True,
    )
    _scheduler.add_job(
        _deployment_recovery_job,
        trigger=IntervalTrigger(seconds=settings.DEPLOYMENT_RECOVERY_INTERVAL_SECONDS),
        id="deployment_recovery",
        name="Model deployment recovery and reconciliation",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()
    logger.info(
        "Cleanup scheduler started (interval=%dh)", settings.CLEANUP_INTERVAL_HOURS
    )


def stop_scheduler() -> None:
    """Gracefully stop the background scheduler. Called at FastAPI shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Cleanup scheduler stopped")
    _scheduler = None
