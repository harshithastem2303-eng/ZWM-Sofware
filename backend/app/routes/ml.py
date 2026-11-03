import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.training import TrainingJob, ModelVersion
from app.models.user import User
from app.dependencies.auth import get_current_user, require_admin
from app.config import settings
from typing import Optional

from app.schemas.schemas import (
    CandidateApprovalRequest,
    CandidateRejectionRequest,
    EvaluationPolicyUpdate,
    FeedbackDecisionRequest,
    ModelActivationRequest,
    ModelRollbackRequest,
    PredictionFeedbackCreate,
)
from app.services.training_service import check_dataset_readiness, trigger_training_job

router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok", "service": "ml"}


# ---- Training Jobs ----

_JOB_STATUSES = "^(queued|running|completed|failed)$"
_JOB_TRIGGERS = "^(manual|auto|admin_snapshot)$"


@router.get("/jobs")
def list_training_jobs(
    status_filter: Optional[str] = Query(default=None, alias="status", pattern=_JOB_STATUSES),
    trigger: Optional[str] = Query(default=None, pattern=_JOB_TRIGGERS),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Training jobs, newest first. Optional status/trigger filters and limit/offset
    pagination (Block A5; no limit = all rows, as before). Weight locations are
    reported as file names only — absolute paths are never returned.
    """
    from app.services.monitoring_service import basename, redact
    q = db.query(TrainingJob)
    if status_filter:
        q = q.filter(TrainingJob.status == status_filter)
    if trigger:
        q = q.filter(TrainingJob.trigger == trigger)
    total = q.count()
    q = q.order_by(TrainingJob.created_at.desc(), TrainingJob.job_id).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    results = [
        {
            "job_id": j.job_id,
            "version": j.version,
            "status": j.status,
            "class_counts": j.class_counts,
            "best_model_path": basename(j.best_model_path),
            "started_at": str(j.started_at) if j.started_at else None,
            "completed_at": str(j.completed_at) if j.completed_at else None,
            # Snapshot pipeline fields (NULL for legacy/manual jobs)
            "trigger": j.trigger,
            "snapshot_id": j.snapshot_id,
            "dataset_status": j.dataset_status,
            "error_message": redact(j.error_message),
            "dispatch_attempts": j.dispatch_attempts,
            "attempt_count": j.attempt_count,
            "created_at": str(j.created_at) if j.created_at else None,
            "lease_expires_at": str(j.lease_expires_at) if j.lease_expires_at else None,
        }
        for j in q.all()
    ]
    return {"jobs": results, "total": total, "limit": limit, "offset": offset}


@router.get("/jobs/{job_id}")
def get_training_job(
    job_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.training import TrainingJobEvent
    from app.services.monitoring_service import basename, job_event_to_dict, redact
    job = db.query(TrainingJob).filter(TrainingJob.job_id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Training job not found")
    attempts = (db.query(TrainingJobEvent).filter(TrainingJobEvent.job_id == job_id)
                .order_by(TrainingJobEvent.created_at, TrainingJobEvent.event_id).all())
    return {
        "job_id": job.job_id,
        "version": job.version,
        "status": job.status,
        "class_counts": job.class_counts,
        "best_model_path": basename(job.best_model_path),
        "metadata_path": basename(job.metadata_path),
        "started_at": str(job.started_at) if job.started_at else None,
        "completed_at": str(job.completed_at) if job.completed_at else None,
        "attempt_count": job.attempt_count,
        "error_message": redact(job.error_message),
        "history": [job_event_to_dict(e) for e in attempts],
    }


@router.post("/training/dispatch")
def dispatch_training_jobs(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Recovery: prepare and queue snapshot jobs that are not (or no longer) queued."""
    from app.services.training_pipeline_service import dispatch_pending_training_jobs
    return {"results": dispatch_pending_training_jobs(db)}


@router.post("/snapshots/{snapshot_id}/train", status_code=status.HTTP_201_CREATED)
def train_snapshot(
    snapshot_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Explicit admin action to train an existing locked snapshot that has no job
    (e.g. locked while auto_train_toggle was off). Never retrains a snapshot twice.
    """
    from app.services.training_pipeline_service import (
        SnapshotJobExistsError,
        create_snapshot_training_job,
        dispatch_pending_training_jobs,
        job_to_dict,
    )
    try:
        job = create_snapshot_training_job(db, snapshot_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    except SnapshotJobExistsError:
        raise HTTPException(status_code=409, detail="This snapshot already has a training job")
    job_id = job.job_id
    dispatch = dispatch_pending_training_jobs(db)
    job = db.query(TrainingJob).filter(TrainingJob.job_id == job_id).one()
    from app.services.monitoring_service import public_paths
    return public_paths({"job": job_to_dict(job), "dispatch": dispatch})   # A5.1: no absolute paths


# ---- Candidate evaluation & quality gates (Block A3; activation is Block A4) ----

def _actor_id(admin) -> str:
    return getattr(admin, "user_id", None) or getattr(admin, "admin_id", None)


@router.get("/candidates")
def list_candidates(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Snapshot-trained candidate models with their latest evaluation."""
    from app.models.training import ModelEvaluation
    from app.services.model_evaluation_service import evaluation_to_dict

    rows = (
        db.query(ModelVersion, TrainingJob)
        .join(TrainingJob, TrainingJob.job_id == ModelVersion.job_id)
        .filter(TrainingJob.snapshot_id.isnot(None))
        .order_by(ModelVersion.created_at.desc())
        .all()
    )
    out = []
    for mv, job in rows:
        latest = (
            db.query(ModelEvaluation).filter(ModelEvaluation.model_id == mv.model_id)
            .order_by(ModelEvaluation.created_at.desc()).first()
        )
        out.append({
            "model_id": mv.model_id,
            "version": mv.version,
            "is_current": mv.is_current,
            "job_id": job.job_id,
            "snapshot_id": job.snapshot_id,
            "weights_path": job.best_model_path,
            "latest_evaluation": evaluation_to_dict(latest) if latest else None,
        })
    from app.services.monitoring_service import public_paths
    return public_paths({"candidates": out})                 # A5.1: file names only, never absolute paths


@router.post("/candidates/{model_id}/evaluations", status_code=status.HTTP_202_ACCEPTED)
def request_candidate_evaluation(
    model_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Request (idempotently) an evaluation of a candidate on its snapshot's test split."""
    from app.models.training import ModelEvaluation
    from app.services.model_evaluation_service import (
        EvaluationRequestError,
        dispatch_pending_evaluations,
        evaluation_to_dict,
        request_evaluation,
    )
    try:
        evaluation, created = request_evaluation(db, model_id, _actor_id(admin))
    except LookupError:
        raise HTTPException(status_code=404, detail="Model version not found")
    except EvaluationRequestError as exc:
        raise HTTPException(status_code=422, detail=f"Evaluation cannot be requested: {exc}")
    evaluation_id = evaluation.evaluation_id
    if created:
        dispatch_pending_evaluations(db)
    evaluation = db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == evaluation_id).one()
    return {"created": created, "evaluation": evaluation_to_dict(evaluation)}


@router.get("/evaluations")
def list_evaluations(
    model_id: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status", pattern="^(pending|running|passed|failed|error)$"),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models.training import ModelEvaluation
    from app.services.model_evaluation_service import evaluation_to_dict
    q = db.query(ModelEvaluation)
    if model_id:
        q = q.filter(ModelEvaluation.model_id == model_id)
    if status_filter:
        q = q.filter(ModelEvaluation.status == status_filter)
    total = q.count()
    q = q.order_by(ModelEvaluation.created_at.desc(), ModelEvaluation.evaluation_id).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    items = []
    from app.services.monitoring_service import redact
    for e in q.all():                                       # A5: headline metrics for list views (additive)
        m = e.metrics or {}
        items.append({**evaluation_to_dict(e), "error_message": redact(e.error_message),
                      "metrics": {k: m.get(k) for k in ("map50", "map50_95", "precision", "recall")}})
    return {"evaluations": items, "total": total, "limit": limit, "offset": offset}


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(
    evaluation_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Full metrics, per-class results, quality-gate outcomes, baseline and failure reasons."""
    from app.models.training import ModelEvaluation
    from app.services.model_evaluation_service import evaluation_to_dict
    ev = db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == evaluation_id).first()
    if ev is None:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    from app.services.monitoring_service import public_paths
    return public_paths(evaluation_to_dict(ev, detail=True))  # A5.1: weights/manifest as file names


@router.get("/evaluation-policy")
def get_evaluation_policy(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.services.model_evaluation_service import get_policy, policy_configured
    policy = get_policy(db)
    return {**policy, "configured": policy_configured(policy)}


@router.put("/evaluation-policy")
def update_evaluation_policy(
    policy_in: EvaluationPolicyUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.services.model_evaluation_service import update_policy
    return update_policy(db, policy_in.model_dump(exclude_unset=True), _actor_id(admin))


@router.post("/train", status_code=status.HTTP_201_CREATED)
def trigger_training(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Create a training job and queue it for Celery execution.
    """
    ready, stats = check_dataset_readiness(db)

    # Compute next version
    job_count = db.query(TrainingJob).count()
    version = f"v{job_count + 1}"

    # Build class counts from stats
    class_counts = {s["class_name"]: s["validated_count"] for s in stats} if stats else {}

    job = trigger_training_job(db, version=version, class_counts=class_counts)
    if not job:
        raise HTTPException(status_code=500, detail="Failed to create training job")

    # Enqueue in Celery or execute in background thread fallback if Celery worker is offline
    try:
        from app.tasks.training_tasks import train_model
        res = train_model.delay(job.job_id)
    except Exception as e:
        logger.warning(f"Celery queue note: {e}. Spawning background thread for YOLO training...")
        import threading
        def run_bg_training(j_id):
            from app.tasks.training_tasks import train_model
            try:
                train_model(j_id)
            except Exception as ex:
                logger.exception(f"Background thread training error: {ex}")
        t = threading.Thread(target=run_bg_training, args=(job.job_id,), daemon=True)
        t.start()

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

def _file_name(path):
    from app.services.monitoring_service import basename
    return basename(path)


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
        "model_path": _file_name(best_model_path),            # A5.1: file name only
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
    body: Optional[ModelActivationRequest] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Activate a model version through the controlled deployment engine (Block A4).

    Snapshot-trained candidates require a valid administrator approval of their
    latest passed A3 evaluation; every piece of evidence is re-verified, weights
    are staged, the serving file is switched atomically and readiness is checked
    before the database switch. Legacy models keep v1.0 semantics (no evaluation)
    behind ALLOW_LEGACY_MODEL_ACTIVATION.
    """
    from app.services.model_deployment_service import DeploymentError, activate_model_version
    try:
        result = activate_model_version(db, model_id, _actor_id(admin), body.reason if body else None)
    except LookupError:
        raise HTTPException(status_code=404, detail="Model version not found")
    except DeploymentError as exc:
        raise _deployment_http_error(exc)
    model = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).one()
    message = ("Model version is already active" if result["result"] == "already_active"
               else "Model version activated successfully")
    return {"message": message, "model_id": model.model_id, "version": model.version, **result}


# ---- Controlled approval, activation & rollback (Block A4) ----

def _deployment_http_error(exc) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail="; ".join(exc.reasons))


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail="Evaluation not found" if "evaluation" in str(exc)
                         else "Model version not found")


@router.get("/approvals/pending")
def list_pending_approvals(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Snapshot candidates whose latest evaluation is eligible for review and undecided."""
    from app.services.model_deployment_service import pending_candidates
    return {"candidates": pending_candidates(db)}


@router.get("/approvals")
def list_approval_history(
    model_id: Optional[str] = None,
    decision: Optional[str] = Query(default=None, pattern="^(approved|rejected)$"),
    limit: Optional[int] = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approval records, newest first. Optional decision filter and limit/offset (A5; no limit = all rows)."""
    from app.models.training import ModelApproval
    from app.services.model_deployment_service import approval_to_dict
    q = db.query(ModelApproval)
    if model_id:
        q = q.filter(ModelApproval.model_id == model_id)
    if decision:
        q = q.filter(ModelApproval.decision == decision)
    total = q.count()
    q = q.order_by(ModelApproval.decided_at.desc(), ModelApproval.approval_id).offset(offset)
    if limit is not None:
        q = q.limit(limit)
    return {"approvals": [approval_to_dict(a) for a in q.all()], "total": total, "limit": limit, "offset": offset}


@router.get("/candidates/{model_id}/approval")
def get_candidate_approval_status(
    model_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Review + deployment state, evaluation summary, decision history and blocking reasons."""
    from app.models.training import ModelApproval, ModelEvaluation
    from app.services.model_deployment_service import approval_to_dict, candidate_status
    from app.services.model_evaluation_service import evaluation_to_dict
    mv = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if mv is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    status_info = candidate_status(db, mv, deep=True)
    evaluation = None
    if status_info["latest_evaluation_id"]:
        ev = db.query(ModelEvaluation).filter(
            ModelEvaluation.evaluation_id == status_info["latest_evaluation_id"]).one()
        evaluation = evaluation_to_dict(ev, detail=True)
        for key in ("weights_path", "dataset_manifest_path"):
            evaluation.pop(key, None)
    history = (db.query(ModelApproval).filter(ModelApproval.model_id == model_id)
               .order_by(ModelApproval.decided_at.desc()).all())
    return {**status_info, "evaluation": evaluation, "decisions": [approval_to_dict(a) for a in history]}


@router.post("/candidates/{model_id}/approve")
def approve_candidate_model(
    model_id: str,
    body: CandidateApprovalRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve the named (latest, passed, eligible) evaluation. Repeats are idempotent."""
    from app.services.model_deployment_service import DeploymentError, approval_to_dict, approve_candidate
    try:
        approval, created = approve_candidate(db, model_id, body.evaluation_id, _actor_id(admin), body.reason)
    except LookupError as exc:
        raise _not_found(exc)
    except DeploymentError as exc:
        raise _deployment_http_error(exc)
    return {"created": created, "approval": approval_to_dict(approval)}


@router.post("/candidates/{model_id}/reject")
def reject_candidate_model(
    model_id: str,
    body: CandidateRejectionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reject with a recorded reason. Weights and evaluation results are kept."""
    from app.services.model_deployment_service import DeploymentError, approval_to_dict, reject_candidate
    try:
        decision, created = reject_candidate(db, model_id, body.evaluation_id, _actor_id(admin), body.reason)
    except LookupError as exc:
        raise _not_found(exc)
    except DeploymentError as exc:
        raise _deployment_http_error(exc)
    return {"created": created, "approval": approval_to_dict(decision)}


@router.get("/deployments")
def list_deployments(
    kind: Optional[str] = None,
    model_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Active deployment, rollback target and history (kind=activation|rollback|legacy_activation)."""
    from app.models.training import ModelDeployment
    from app.services.model_deployment_service import deployment_overview, deployment_to_dict
    from app.services.monitoring_service import redact_deployment
    if kind is not None and kind not in ("activation", "rollback", "legacy_activation"):
        raise HTTPException(status_code=422, detail="kind must be activation, rollback or legacy_activation")
    q = db.query(ModelDeployment)
    if kind:
        q = q.filter(ModelDeployment.kind == kind)
    if model_id:
        q = q.filter(ModelDeployment.model_id == model_id)
    total = q.count()
    history = [redact_deployment(deployment_to_dict(d)) for d in q.order_by(
        ModelDeployment.requested_at.desc(), ModelDeployment.deployment_id).offset(offset).limit(limit).all()]
    overview = deployment_overview(db)
    for key in ("active_deployment", "in_progress"):
        overview[key] = redact_deployment(overview.get(key))
    return {**overview, "history": history, "total": total, "limit": limit, "offset": offset}


@router.get("/deployments/events")
def list_deployment_events(
    model_id: Optional[str] = None,
    deployment_id: Optional[str] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Audit trail: approvals, rejections, activation and rollback events."""
    from app.models.training import DeploymentEvent
    from app.services.model_deployment_service import event_to_dict
    q = db.query(DeploymentEvent)
    if model_id:
        q = q.filter(DeploymentEvent.model_id == model_id)
    if deployment_id:
        q = q.filter(DeploymentEvent.deployment_id == deployment_id)
    return {"events": [event_to_dict(e) for e in q.order_by(DeploymentEvent.created_at.desc()).limit(500).all()]}


@router.post("/deployments/rollback")
def rollback_deployment(
    body: ModelRollbackRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Restore the previously active (or a named, previously deployed) model from its retained artifact."""
    from app.services.model_deployment_service import DeploymentError, rollback
    try:
        return rollback(db, _actor_id(admin), body.reason, body.target_model_id)
    except DeploymentError as exc:
        raise _deployment_http_error(exc)


@router.post("/deployments/recover")
def recover_deployments(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Recover activations/rollbacks interrupted by a crash (lease expired) and reconcile the serving file."""
    from app.services.model_deployment_service import run_deployment_maintenance
    return run_deployment_maintenance(db)


# ---- Administrator monitoring (Block A5; strictly read-only) ----

@router.get("/monitoring/summary")
def monitoring_summary(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """One-call pipeline overview: jobs, readiness, evaluations, approvals, deployment, health, alerts."""
    from app.services.monitoring_service import summary
    try:
        return summary(db)
    except Exception as exc:
        import logging
        logging.getLogger("ml_routes").error("MONITORING_SUMMARY_FAILED | %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Monitoring data is temporarily unavailable")


@router.get("/monitoring/timeline")
def monitoring_timeline(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=800),
    source: Optional[str] = Query(default=None, pattern="^(training|deployment|evaluation)(,(training|deployment|evaluation))*$"),
    since: Optional[str] = Query(default=None, max_length=40),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Paginated, newest-first merge of training attempts, deployment audit events and evaluations."""
    from datetime import datetime
    from app.services.monitoring_service import timeline
    since_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="since must be an ISO-8601 timestamp")
    sources = set(source.split(",")) if source else None
    try:
        return timeline(db, limit=limit, offset=offset, sources=sources, since=since_dt)
    except Exception as exc:
        import logging
        logging.getLogger("ml_routes").error("MONITORING_TIMELINE_FAILED | %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Monitoring data is temporarily unavailable")


# ---- YOLO Prediction ----

@router.post("/predict")
def predict(
    file: UploadFile = File(...),
    image_id: Optional[str] = Form(default=None, max_length=36),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run YOLO inference on an uploaded image.
    BLOCKED if no trained model (.pt file) is available.

    Block A6.1: every inference is stored as an immutable PredictionRecord attributed
    to the exact artifact the model was loaded from; the response gains
    ``prediction_id``. ``image_id`` (optional) links the prediction to one of the
    caller's images (any image for administrators).
    """
    from app.models.image import Image
    from app.models.prediction import SOURCE_ML_PREDICT, STATUS_FAILED, STATUS_SUCCEEDED
    from app.services import prediction_service as ps

    # 1. Validate file is an image
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only image files are allowed for prediction."
        )
    if image_id is not None:
        img = db.query(Image).filter(Image.image_id == image_id).first()
        if img is None:
            raise HTTPException(status_code=404, detail="Image not found")
        if img.user_id != current_user.user_id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to predict for this image")
        # A6.0 rule, unchanged: boxes served for an image are AI suggestions, so its
        # labels then need an administrator review (recorded before inference).
        from app.services.training_dataset_service import record_ai_suggestion
        record_ai_suggestion(db, image_id)

    # 2. Get active cached model together with the identity of its artifact
    try:
        model, identity = model_cache.get_model_with_identity()
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

    # Attribution is fixed now, before inference: a concurrent activation/rollback
    # cannot change which model this prediction belongs to.
    attribution = ps.resolve_deployed_identity(db, identity)
    class_names = ps.class_names_of(model)
    params = {"conf": settings.YOLO_CONFIDENCE_THRESHOLD}

    def _store(rec):
        db.add(rec)
        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.error("PREDICTION_RECORD_FAILED | source=%s", SOURCE_ML_PREDICT)
            raise HTTPException(status_code=500, detail="Prediction could not be recorded")
        return rec

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

    except Exception as e:
        _store(ps.new_record(source=SOURCE_ML_PREDICT, status=STATUS_FAILED, identity=attribution, detections=[],
                             confidence_is_model_score=True, image_id=image_id, requested_by=current_user.user_id,
                             class_names=class_names, request_params=params, error=type(e).__name__))
        raise HTTPException(
            status_code=500,
            detail=f"Prediction inference failed: {str(e)}"
        )

    detections = [{"class_id": p["class"], "label": (class_names or {}).get(str(p["class"])),
                   "confidence": p["confidence"], "bbox": p["bbox"]} for p in predictions]
    rec = _store(ps.new_record(source=SOURCE_ML_PREDICT, status=STATUS_SUCCEEDED, identity=attribution,
                               detections=detections, confidence_is_model_score=True, image_id=image_id,
                               requested_by=current_user.user_id, class_names=class_names,
                               result={"predictions": predictions, "count": len(predictions)},
                               request_params=params))
    return {"predictions": predictions, "count": len(predictions), "prediction_id": rec.prediction_id}


# ---- Prediction provenance (Block A6.1; read-only) ----

_PRED_SOURCES = "^(ml_predict|upload_validation|ai_segment|ai_polygon_click)$"
_PRED_STATUSES = "^(succeeded|no_result|failed)$"


@router.get("/predictions")
def list_predictions(
    source: Optional[str] = Query(default=None, pattern=_PRED_SOURCES),
    status_filter: Optional[str] = Query(default=None, alias="status", pattern=_PRED_STATUSES),
    image_id: Optional[str] = Query(default=None, max_length=36),
    model_version_id: Optional[str] = Query(default=None, max_length=36),
    user_id: Optional[str] = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest first. Users see only their own predictions; administrators may filter by user."""
    from app.services import prediction_service as ps
    is_admin = current_user.role == "admin"
    if user_id is not None and not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can view other users' predictions")
    owner = (user_id if is_admin else current_user.user_id)
    return ps.list_predictions(db, requested_by=owner, image_id=image_id, source=source, status=status_filter,
                               model_version_id=model_version_id, limit=limit, offset=offset,
                               include_requester=is_admin)


@router.get("/predictions/{prediction_id}")
def get_prediction(
    prediction_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Full provenance of one prediction (its requester or an administrator; otherwise 404)."""
    from app.models.prediction import PredictionRecord
    from app.services import prediction_service as ps
    rec = db.query(PredictionRecord).filter(PredictionRecord.prediction_id == prediction_id).first()
    is_admin = current_user.role == "admin"
    if rec is None or (not is_admin and rec.requested_by != current_user.user_id):
        raise HTTPException(status_code=404, detail="Prediction not found")
    return ps.to_dict(rec, include_requester=is_admin)


# ---- Prediction feedback (Block A6.2) ----
# Feedback never changes the prediction, annotations, labels or training eligibility;
# an approval only accepts it for a later, governed correction workflow.

_FB_STATUSES = "^(pending|approved|rejected)$"
_FB_TYPES = "^(incorrect_class|incorrect_geometry|missed_object|false_detection|other)$"


@router.post("/predictions/{prediction_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_prediction_feedback(
    prediction_id: str,
    payload: PredictionFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Report an incorrect prediction the caller can see (its requester, or an administrator)."""
    from app.services import feedback_service as fs
    fb = fs.submit_feedback(db, current_user, prediction_id, **payload.model_dump())
    return fs.get_feedback(db, current_user, fb.feedback_id)


@router.get("/feedback")
def list_my_feedback(
    status_filter: Optional[str] = Query(default=None, alias="status", pattern=_FB_STATUSES),
    feedback_type: Optional[str] = Query(default=None, pattern=_FB_TYPES),
    prediction_id: Optional[str] = Query(default=None, max_length=36),
    image_id: Optional[str] = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The caller's own feedback, newest first, with its review status."""
    from app.services import feedback_service as fs
    return fs.list_feedback(db, admin=False, submitted_by=current_user.user_id, status_=status_filter,
                            feedback_type=feedback_type, prediction_id=prediction_id, image_id=image_id,
                            limit=limit, offset=offset)


@router.get("/feedback/{feedback_id}")
def get_my_feedback(
    feedback_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """One feedback and its review status (its submitter or an administrator; otherwise 404)."""
    from app.services import feedback_service as fs
    return fs.get_feedback(db, current_user, feedback_id)


@router.get("/feedback-review")
def list_feedback_for_review(
    status_filter: Optional[str] = Query(default=None, alias="status", pattern=_FB_STATUSES),
    feedback_type: Optional[str] = Query(default=None, pattern=_FB_TYPES),
    submitted_from: Optional[datetime] = Query(default=None),
    submitted_to: Optional[datetime] = Query(default=None),
    user_id: Optional[str] = Query(default=None, max_length=36),
    prediction_id: Optional[str] = Query(default=None, max_length=36),
    order: str = Query(default="newest", pattern="^(newest|oldest)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100_000),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Administrator queue: all feedback, filterable by status, type, submission date and user."""
    from app.services import feedback_service as fs
    return fs.list_feedback(db, admin=True, submitted_by=user_id, status_=status_filter,
                            feedback_type=feedback_type, prediction_id=prediction_id,
                            submitted_from=submitted_from, submitted_to=submitted_to,
                            oldest_first=(order == "oldest"), limit=limit, offset=offset)


@router.get("/feedback-review/{feedback_id}")
def get_feedback_for_review(
    feedback_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Feedback, its suggested correction, decision history and the original immutable prediction."""
    from app.services import feedback_service as fs
    return fs.get_feedback(db, admin, feedback_id)


def _decide_feedback(db, admin, feedback_id, decision, reason):
    from app.services import feedback_service as fs
    _, replayed = fs.decide(db, admin, feedback_id, decision, reason)
    data = fs.get_feedback(db, admin, feedback_id)
    data["idempotent_replay"] = replayed
    return data


@router.post("/feedback-review/{feedback_id}/approve")
def approve_feedback(
    feedback_id: str,
    payload: Optional[FeedbackDecisionRequest] = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Accept the feedback for a later governed correction workflow (no label is changed)."""
    return _decide_feedback(db, admin, feedback_id, "approved", payload.reason if payload else None)


@router.post("/feedback-review/{feedback_id}/reject")
def reject_feedback(
    feedback_id: str,
    payload: FeedbackDecisionRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reject the feedback; a reason is required."""
    return _decide_feedback(db, admin, feedback_id, "rejected", payload.reason)
