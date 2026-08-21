"""
Background cleanup worker for expired temporary images.

Uses APScheduler to run run_cleanup() every CLEANUP_INTERVAL_HOURS.
Registered at FastAPI startup / shutdown via lifespan context manager.

Usage (in main.py):
    from app.services.cleanup_worker import start_scheduler, stop_scheduler
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings
from app.database import SessionLocal
from app.services.lifecycle_service import run_cleanup

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _cleanup_job() -> None:
    """Periodic job: open a DB session, run cleanup, close session."""
    db = SessionLocal()
    try:
        stats = run_cleanup(db)
        logger.info(
            "Scheduled cleanup complete | cleaned=%d errors=%d skipped=%d",
            stats["cleaned"], stats["errors"], stats["skipped"],
        )
    except Exception as exc:
        logger.error("Scheduled cleanup raised an exception: %s", exc)
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
