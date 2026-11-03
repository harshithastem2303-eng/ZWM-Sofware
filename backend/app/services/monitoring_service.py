"""
Administrator monitoring read models (ZWM v1.1.0, Block A5).

Everything here is READ-ONLY: no function writes to the database, the serving
file, the model cache or the queue. Every entry point ends its transaction with
a rollback, so even a concurrent or failing request cannot leave changes behind.
Responses never contain absolute filesystem paths (see redact()).

Sources reused from A1-A4.1: training jobs + attempt history, readiness,
evaluations, approvals, deployments + consistency, scheduler heartbeats.
"""
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.training import (
    DeploymentEvent,
    ModelApproval,
    ModelDeployment,
    ModelEvaluation,
    SchedulerHeartbeat,
    TrainingJob,
    TrainingJobEvent,
)

logger = logging.getLogger(__name__)

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
MAX_PAGE = 200
MAX_TIMELINE_WINDOW = 1000

# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

_WIN_PATH = re.compile(r"(?:[A-Za-z]:|\\\\[^\\\s'\"]+)\\(?:[^\\\s'\"<>|]+\\)*([^\\\s'\"<>|]*)")
_POSIX_PATH = re.compile(r"(?<![\w.:/])/(?:[^/\s'\"<>|]+/)+([^/\s'\"<>|]*)")


def redact(text: Optional[str]) -> Optional[str]:
    """Replace absolute Windows/POSIX paths with their file name."""
    if not text:
        return text
    text = _WIN_PATH.sub(lambda m: f"<path>/{m.group(1)}" if m.group(1) else "<path>", str(text))
    return _POSIX_PATH.sub(lambda m: f"<path>/{m.group(1)}" if m.group(1) else "<path>", text)


def basename(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return re.split(r"[\\/]", str(path))[-1] or None


_PATH_KEYS = re.compile(r"(^|_)(path|dir)$")
_TEXT_KEYS = ("error_message", "reason", "error", "message")


def public_paths(obj):
    """
    API-boundary sanitiser (A5.1): any ``*_path`` / ``*_dir`` / ``path`` value becomes its
    file name and free-text error fields are path-redacted, recursively. Stored data is untouched.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _PATH_KEYS.search(k) and isinstance(v, str):
                out[k] = basename(v)
            elif isinstance(k, str) and k in _TEXT_KEYS and isinstance(v, str):
                out[k] = redact(v)
            else:
                out[k] = public_paths(v)
        return out
    if isinstance(obj, list):
        return [public_paths(v) for v in obj]
    return obj


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    return ts if ts is None or ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _iso(ts: Optional[datetime]) -> Optional[str]:
    ts = _aware(ts)
    return ts.isoformat() if ts else None


# ---------------------------------------------------------------------------
# Worker availability (cached; the probe never blocks every poll)
# ---------------------------------------------------------------------------

_WORKER_CACHE = {"at": 0.0, "value": None}
_WORKER_LOCK = threading.Lock()
_PROBE = {"thread": None}
WORKER_CACHE_SECONDS = 30
WORKER_FIRST_WAIT_SECONDS = 1.0


def _probe_workers() -> dict:
    try:
        from app.celery_app import celery_app
        replies = celery_app.control.inspect(timeout=1.0).ping() or {}
        return {"status": "online" if replies else "offline", "workers": sorted(replies)}
    except Exception as exc:
        return {"status": "unavailable", "workers": [], "error": type(exc).__name__}


def _refresh_workers(started: float) -> None:
    value = {**_probe_workers(), "checked_at": _iso(datetime.now(timezone.utc))}
    with _WORKER_LOCK:
        _WORKER_CACHE.update(at=started, value=value)
        _PROBE["thread"] = None


def worker_status(now_monotonic: Optional[float] = None, wait: Optional[float] = None) -> dict:
    """
    Never blocks a request on the broker (an unreachable broker can take seconds):
    a stale cache triggers one background probe and the last known value is returned.
    Only the very first call waits briefly; with no answer the status is 'unknown'.
    """
    now_monotonic = now_monotonic if now_monotonic is not None else time.monotonic()
    wait = WORKER_FIRST_WAIT_SECONDS if wait is None else wait
    with _WORKER_LOCK:
        cached, at = _WORKER_CACHE["value"], _WORKER_CACHE["at"]
        if cached is not None and now_monotonic - at < WORKER_CACHE_SECONDS:
            return {**cached, "cached": True}
        thread = _PROBE["thread"]
        if thread is None:
            thread = threading.Thread(target=_refresh_workers, args=(now_monotonic,), daemon=True, name="worker-probe")
            _PROBE["thread"] = thread
            thread.start()
    if cached is not None:
        return {**cached, "cached": True, "refreshing": True}
    thread.join(wait)
    with _WORKER_LOCK:
        if _WORKER_CACHE["value"] is not None:
            return {**_WORKER_CACHE["value"], "cached": False}
    return {"status": "unknown", "workers": [], "checked_at": None, "cached": False, "refreshing": True}


# ---------------------------------------------------------------------------
# Serialisers (no paths)
# ---------------------------------------------------------------------------

def job_to_dict(j: TrainingJob) -> dict:
    return {
        "job_id": j.job_id, "version": j.version, "status": j.status, "trigger": j.trigger,
        "snapshot_id": j.snapshot_id, "dataset_status": j.dataset_status,
        "attempt_count": j.attempt_count, "dispatch_attempts": j.dispatch_attempts,
        "worker_id": j.worker_id, "error_message": redact(j.error_message),
        "artifact": basename(j.best_model_path),
        "created_at": _iso(j.created_at), "started_at": _iso(j.started_at), "completed_at": _iso(j.completed_at),
        "dispatched_at": _iso(j.dispatched_at), "heartbeat_at": _iso(j.heartbeat_at),
        "lease_expires_at": _iso(j.lease_expires_at),
    }


def job_event_to_dict(e: TrainingJobEvent) -> dict:
    return {"event_id": e.event_id, "job_id": e.job_id, "event_type": e.event_type,
            "status_before": e.status_before, "status_after": e.status_after, "attempt": e.attempt,
            "dispatch_attempts": e.dispatch_attempts, "worker_id": e.worker_id,
            "message": redact(e.message), "created_at": _iso(e.created_at)}


def evaluation_to_dict(ev: ModelEvaluation) -> dict:
    m = ev.metrics or {}
    return {"evaluation_id": ev.evaluation_id, "model_id": ev.model_id, "model_version": ev.model_version,
            "job_id": ev.job_id, "snapshot_id": ev.snapshot_id, "status": ev.status,
            "gate_decision": ev.gate_decision, "test_image_count": ev.test_image_count,
            "metrics": {k: m.get(k) for k in ("map50", "map50_95", "precision", "recall")},
            "error_message": redact(ev.error_message), "attempt_count": ev.attempt_count,
            "created_at": _iso(ev.created_at), "evaluated_at": _iso(ev.evaluated_at),
            "lease_expires_at": _iso(ev.lease_expires_at)}


def redact_deployment(d: Optional[dict]) -> Optional[dict]:
    """deployment_to_dict() output with free-text fields path-redacted (A4 serialiser left unchanged)."""
    if not d:
        return d
    return {**d, "error_message": redact(d.get("error_message")), "reason": redact(d.get("reason"))}


def heartbeat_to_dict(h: SchedulerHeartbeat, now: datetime) -> dict:
    finished = _aware(h.last_finished_at)
    age = (now - finished).total_seconds() if finished else None
    return {"job_name": h.job_name, "interval_seconds": h.interval_seconds, "process_id": h.process_id,
            "last_status": h.last_status, "last_error": redact(h.last_error),
            "last_started_at": _iso(h.last_started_at), "last_finished_at": _iso(h.last_finished_at),
            "last_duration_seconds": h.last_duration_seconds, "run_count": h.run_count,
            "consecutive_failures": h.consecutive_failures,
            "seconds_since_last_run": round(age, 1) if age is not None else None,
            "stale": age is None or age > 3 * max(h.interval_seconds, 1)}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def _alert(code, severity, message, **ref) -> dict:
    return {"code": code, "severity": severity, "message": redact(message), **ref}


def compute_alerts(db: Session, now: datetime, consistency: dict, workers: dict, heartbeats: list) -> list:
    alerts = []
    grace = timedelta(seconds=settings.TRAINING_LEASE_GRACE_SECONDS)
    recent = now - timedelta(days=7)
    stale_dispatch = now - timedelta(minutes=settings.TRAINING_DISPATCH_STALE_MINUTES)

    for j in db.query(TrainingJob).filter(TrainingJob.status == "running").all():
        lease = _aware(j.lease_expires_at)
        if lease is not None and lease < now:
            abandoned = lease < now - grace
            alerts.append(_alert("JOB_LEASE_EXPIRED", "critical" if abandoned else "warning",
                                 f"training job {j.version} attempt {j.attempt_count}: worker lease expired"
                                 + (" (abandoned; recovery will re-queue or fail it)" if abandoned else ""),
                                 job_id=j.job_id))
    for j in db.query(TrainingJob).filter(TrainingJob.status == "queued").all():
        dispatched = _aware(j.dispatched_at)
        created = _aware(j.created_at)
        if j.snapshot_id is not None and dispatched is None and (j.dispatch_attempts or 0) >= 3:
            alerts.append(_alert("JOB_DISPATCH_FAILING", "critical",
                                 f"training job {j.version}: {j.dispatch_attempts} queue dispatch attempts failed",
                                 job_id=j.job_id))
        elif (dispatched is not None and dispatched < stale_dispatch) or \
                (dispatched is None and created is not None and created < stale_dispatch):
            alerts.append(_alert("JOB_STUCK", "warning",
                                 f"training job {j.version} has been queued for over "
                                 f"{settings.TRAINING_DISPATCH_STALE_MINUTES} minutes without starting",
                                 job_id=j.job_id))
    for j in (db.query(TrainingJob).filter(TrainingJob.status == "failed")
              .order_by(TrainingJob.created_at.desc(), TrainingJob.job_id).limit(20).all()):
        when = _aware(j.completed_at) or _aware(j.created_at)
        if when is not None and when < recent:
            continue
        exhausted = (j.attempt_count or 0) >= settings.TRAINING_MAX_ATTEMPTS
        alerts.append(_alert("JOB_RETRIES_EXHAUSTED" if exhausted else "JOB_FAILED",
                             "critical" if exhausted else "warning",
                             f"training job {j.version} failed after {j.attempt_count} attempt(s): "
                             f"{(j.error_message or 'no error recorded')[:200]}", job_id=j.job_id))

    for ev in (db.query(ModelEvaluation).filter(ModelEvaluation.status == "error")
               .order_by(ModelEvaluation.created_at.desc(), ModelEvaluation.evaluation_id).limit(20).all()):
        when = _aware(ev.evaluated_at) or _aware(ev.created_at)
        if when is not None and when < recent:
            continue
        alerts.append(_alert("EVALUATION_FAILED", "warning",
                             f"evaluation of {ev.model_version}: {(ev.error_message or 'error')[:200]}",
                             evaluation_id=ev.evaluation_id, model_id=ev.model_id))
    for ev in db.query(ModelEvaluation).filter(ModelEvaluation.status == "running").all():
        lease = _aware(ev.lease_expires_at)
        if lease is not None and lease < now:
            alerts.append(_alert("EVALUATION_LEASE_EXPIRED", "warning",
                                 f"evaluation of {ev.model_version}: worker lease expired",
                                 evaluation_id=ev.evaluation_id, model_id=ev.model_id))

    if consistency.get("state") == "inconsistent":
        alerts.append(_alert("DEPLOYMENT_INCONSISTENT", "critical",
                             "deployment state is inconsistent: " + "; ".join(consistency.get("issues") or []),
                             deployment_id=consistency.get("active_deployment_id")))
    running = db.query(ModelDeployment).filter(ModelDeployment.status.in_(("pending", "activating"))).first()
    if running is not None and _aware(running.lease_expires_at) is not None and _aware(running.lease_expires_at) < now:
        alerts.append(_alert("DEPLOYMENT_STUCK", "critical",
                             f"{running.kind} of {running.model_version} stopped renewing its lease; "
                             "recovery will reconcile it", deployment_id=running.deployment_id))
    if consistency.get("state") != "in_progress" and not consistency.get("database_current_model_ids"):
        alerts.append(_alert("NO_ACTIVE_MODEL", "info", "no model is currently active"))

    pending_work = (db.query(func.count(TrainingJob.job_id)).filter(TrainingJob.status.in_(("queued", "running")))
                    .scalar() or 0) + (db.query(func.count(ModelEvaluation.evaluation_id))
                                       .filter(ModelEvaluation.status.in_(("pending", "running"))).scalar() or 0)
    if workers.get("status") != "online":
        alerts.append(_alert("WORKER_UNAVAILABLE", "critical" if pending_work else "warning",
                             f"no Celery worker responded ({workers.get('status')})"
                             + (f"; {pending_work} job(s)/evaluation(s) are waiting" if pending_work else "")))

    known = {h["job_name"]: h for h in heartbeats}
    from app.services.cleanup_worker import SCHEDULER_JOBS
    for name in SCHEDULER_JOBS:
        h = known.get(name)
        if h is None:
            alerts.append(_alert("SCHEDULER_NEVER_RAN", "warning", f"scheduler job {name} has never reported"))
        elif h["last_status"] == "error":
            alerts.append(_alert("SCHEDULER_JOB_FAILING", "critical" if h["consecutive_failures"] >= 3 else "warning",
                                 f"scheduler job {name} failed {h['consecutive_failures']} time(s) in a row: "
                                 f"{h['last_error'] or ''}"))
        elif h["stale"]:
            alerts.append(_alert("SCHEDULER_STALE", "critical",
                                 f"scheduler job {name} has not completed for "
                                 f"{h['seconds_since_last_run']}s (interval {h['interval_seconds']}s)"))
    alerts.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], a["code"]))
    return alerts


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def _counts(db: Session, column) -> dict:
    return {k or "unknown": v for k, v in db.query(column, func.count()).group_by(column).all()}


def summary(db: Session, now: Optional[datetime] = None) -> dict:
    from app.services.model_deployment_service import deployment_overview, pending_candidates
    from app.services.training_dataset_service import get_training_progress

    now = now or datetime.now(timezone.utc)
    try:
        progress = get_training_progress(db)
        overview = deployment_overview(db)
        for key in ("active_deployment", "in_progress"):
            overview[key] = redact_deployment(overview.get(key))
        consistency = overview.pop("consistency")
        consistency.pop("serving_sha256", None)            # hashes stay internal; expected sha is enough
        heartbeats = [heartbeat_to_dict(h, now) for h in
                      db.query(SchedulerHeartbeat).order_by(SchedulerHeartbeat.job_name).all()]
        workers = worker_status()
        running = (db.query(TrainingJob).filter(TrainingJob.status == "running")
                   .order_by(TrainingJob.created_at.desc(), TrainingJob.job_id).limit(10).all())
        recent_failures = (db.query(TrainingJobEvent)
                           .filter(TrainingJobEvent.event_type.in_(("failed", "retries_exhausted", "requeued",
                                                                     "dispatch_failed")))
                           .order_by(TrainingJobEvent.created_at.desc(), TrainingJobEvent.event_id).limit(5).all())
        latest_evals = (db.query(ModelEvaluation)
                        .order_by(ModelEvaluation.created_at.desc(), ModelEvaluation.evaluation_id).limit(5).all())
        pending = pending_candidates(db)
        decisions = _counts(db, ModelApproval.decision)
        result = {
            "generated_at": _iso(now),
            "training": {
                "by_status": _counts(db, TrainingJob.status),
                "by_trigger": _counts(db, TrainingJob.trigger),
                "undispatched": db.query(func.count(TrainingJob.job_id)).filter(
                    TrainingJob.snapshot_id.isnot(None), TrainingJob.status == "queued",
                    TrainingJob.dispatched_at.is_(None)).scalar() or 0,
                "running": [job_to_dict(j) for j in running],
                "recent_failures": [job_event_to_dict(e) for e in recent_failures],
            },
            "dataset": {k: progress.get(k) for k in (
                "threshold", "total_training_eligible_images", "last_milestone", "next_milestone",
                "remaining_to_next_milestone", "images_since_last_milestone", "snapshot_count")},
            "evaluations": {
                "by_status": _counts(db, ModelEvaluation.status),
                "by_decision": _counts(db, ModelEvaluation.gate_decision),
                "latest": [evaluation_to_dict(e) for e in latest_evals],
            },
            "approvals": {"pending_count": len(pending), "decisions": decisions,
                          "pending": [{"model_id": p["model_id"], "version": p["version"],
                                       "latest_evaluation_id": p["latest_evaluation_id"]} for p in pending[:10]]},
            "deployment": {**overview, "consistency": consistency},
            "health": {"database": "ok", "workers": workers, "scheduler": heartbeats},
        }
        result["alerts"] = compute_alerts(db, now, consistency, workers, heartbeats)
        return result
    finally:
        db.rollback()                                    # read-only: never leave a transaction open


# ---------------------------------------------------------------------------
# Timeline (paginated merge of append-only sources)
# ---------------------------------------------------------------------------

TIMELINE_SOURCES = ("training", "deployment", "evaluation")


def timeline(db: Session, limit: int = 50, offset: int = 0, sources: Optional[set] = None,
             since: Optional[datetime] = None) -> dict:
    sources = sources or set(TIMELINE_SOURCES)
    window = min(offset + limit, MAX_TIMELINE_WINDOW) + 1      # one extra row per source detects has_more
    items = []
    try:
        if "training" in sources:
            q = db.query(TrainingJobEvent)
            if since:
                q = q.filter(TrainingJobEvent.created_at >= since)
            for e in q.order_by(TrainingJobEvent.created_at.desc(), TrainingJobEvent.event_id).limit(window).all():
                items.append({"source": "training", "id": e.event_id, "type": e.event_type, "at": _iso(e.created_at),
                              "job_id": e.job_id, "attempt": e.attempt, "status": e.status_after,
                              "message": redact(e.message)})
        if "deployment" in sources:
            q = db.query(DeploymentEvent)
            if since:
                q = q.filter(DeploymentEvent.created_at >= since)
            for e in q.order_by(DeploymentEvent.created_at.desc(), DeploymentEvent.event_id).limit(window).all():
                items.append({"source": "deployment", "id": e.event_id, "type": e.event_type, "at": _iso(e.created_at),
                              "model_id": e.model_id, "deployment_id": e.deployment_id, "actor_id": e.actor_id,
                              "message": redact(_details_text(e.details))})
        if "evaluation" in sources:
            q = db.query(ModelEvaluation).filter(ModelEvaluation.evaluated_at.isnot(None))
            if since:
                q = q.filter(ModelEvaluation.evaluated_at >= since)
            for ev in q.order_by(ModelEvaluation.evaluated_at.desc(), ModelEvaluation.evaluation_id).limit(window).all():
                items.append({"source": "evaluation", "id": ev.evaluation_id,
                              "type": f"evaluation_{ev.status}", "at": _iso(ev.evaluated_at),
                              "model_id": ev.model_id, "status": ev.gate_decision or ev.status,
                              "message": redact(ev.error_message)})
        items.sort(key=lambda i: (i["at"] or "", i["id"]), reverse=True)
        page = items[offset:offset + limit]
        return {"items": page, "limit": limit, "offset": offset,
                "has_more": len(items) > offset + limit and offset + limit < MAX_TIMELINE_WINDOW}
    finally:
        db.rollback()


def _details_text(details) -> Optional[str]:
    if not details:
        return None
    parts = []
    for key in ("reason", "error", "outcome", "stage"):
        if details.get(key):
            parts.append(f"{key}: {details[key]}")
    if details.get("reasons"):
        parts.append("; ".join(map(str, details["reasons"])))
    return " | ".join(parts) or None
