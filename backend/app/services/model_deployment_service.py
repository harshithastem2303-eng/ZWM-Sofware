"""
Controlled model approval, activation & rollback (ZWM v1.1.0, Block A4).

  A3 evaluation (passed / eligible_for_review)
     └─> approve_candidate / reject_candidate          [ModelApproval, immutable, one per evaluation]
           └─> activate_model_version                  [ModelDeployment state machine]
                 recover interrupted -> verify preconditions -> lock (inflight UNIQUE)
                 -> stage content-addressed artifact -> back up the serving file
                 -> load/class-map check -> atomic switch of YOLO_MODEL_PATH
                 -> serving readiness -> ONE transaction: is_current + deployment active
  rollback        same engine, target = a previously served, retained artifact

Consistency model
-----------------
The database is the source of truth for which model is active. A database
commit and a file replacement can never be atomic together, so the serving file
is switched first (os.replace of a verified copy), readiness is checked, and only
then is the database switched in one transaction. Any failure restores the
previous serving file from its retained backup. A crash between the file switch
and the commit leaves the deployment 'activating'; after its lease expires,
recover_interrupted_deployments() puts the serving file back to match the
database. Retained artifacts are content-addressed and never overwritten.
"""
import hashlib
import json
import logging
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.training import (
    CURRENT_MODEL_CHANGE_KEY,
    DeploymentEvent,
    ModelApproval,
    ModelDeployment,
    ModelEvaluation,
    ModelVersion,
    TrainingJob,
    TrainingSnapshot,
)
from app.services.model_evaluation_service import (
    DECISION_ELIGIBLE,
    EVAL_PASSED,
    _class_names,
    _names_list,
    ultralytics_model_names,
)
from app.services.model_cache import replace_with_retry
from app.services.training_pipeline_service import _aware, _sha256

logger = logging.getLogger(__name__)

APPROVED, REJECTED = "approved", "rejected"
KIND_ACTIVATION, KIND_ROLLBACK, KIND_LEGACY = "activation", "rollback", "legacy_activation"
KIND_RECONCILE = "reconcile"
DEP_PENDING, DEP_ACTIVATING, DEP_ACTIVE = "pending", "activating", "active"
DEP_FAILED, DEP_SUPERSEDED, DEP_ROLLED_BACK = "failed", "superseded", "rolled_back"
DEP_RECONCILED = "reconciled"
_IN_FLIGHT = (DEP_PENDING, DEP_ACTIVATING)
_SERVED = (DEP_ACTIVE, DEP_SUPERSEDED, DEP_ROLLED_BACK)
_TRANSITIONS = {
    DEP_PENDING: {DEP_ACTIVATING, DEP_FAILED},
    DEP_ACTIVATING: {DEP_ACTIVE, DEP_FAILED, DEP_RECONCILED},
    DEP_ACTIVE: {DEP_SUPERSEDED, DEP_ROLLED_BACK},
}
INFLIGHT_LOCK = "global"

_EVENTS = {
    KIND_ACTIVATION: ("activation_requested", "activation_started", "activation_succeeded", "activation_failed"),
    KIND_LEGACY: ("activation_requested", "activation_started", "activation_succeeded", "activation_failed"),
    KIND_ROLLBACK: ("rollback_requested", "rollback_started", "rollback_succeeded", "rollback_failed"),
    KIND_RECONCILE: ("reconcile_requested", "reconcile_started", "serving_reconciled", "reconcile_failed"),
}


class DeploymentError(Exception):
    """Base error; ``status_code`` is the HTTP status the API should answer with."""

    def __init__(self, message: str, reasons: Optional[list] = None, status_code: int = 409):
        self.reasons = reasons or [message]
        self.status_code = status_code
        super().__init__(message)


class ReviewError(DeploymentError):
    pass


class PreconditionFailed(DeploymentError):
    pass


class DeploymentConflict(DeploymentError):
    pass


class DeploymentFailed(DeploymentError):
    def __init__(self, message: str, deployment_id: Optional[str] = None):
        self.deployment_id = deployment_id
        super().__init__(message, status_code=500)


class InvalidTransition(Exception):
    pass


class _StageError(Exception):
    """Expected, safe-to-show failure during staging/switching."""


class _LeaseLost(Exception):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _file_sha(path) -> Optional[str]:
    return _sha256(Path(path)) if path and os.path.isfile(path) else None


def _deployed_dir() -> Path:
    return Path(settings.DEPLOYED_MODELS_DIR)


def _serving_path() -> Path:
    return Path(settings.YOLO_MODEL_PATH)


def _transition(dep: ModelDeployment, new_status: str) -> None:
    if new_status not in _TRANSITIONS.get(dep.status, set()):
        raise InvalidTransition(f"deployment {dep.deployment_id}: {dep.status} -> {new_status} is not allowed")
    dep.status = new_status


def _event(db: Session, event_type: str, *, actor_id=None, model_id=None, deployment_id=None,
           approval_id=None, **details) -> None:
    """Audit details must stay free of filesystem paths and stack traces."""
    db.add(DeploymentEvent(event_type=event_type, actor_id=actor_id, model_id=model_id,
                           deployment_id=deployment_id, approval_id=approval_id, details=details or None))


@contextmanager
def allow_current_change(db: Session):
    """Authorise is_current changes on snapshot candidates for this session (deployment engine only)."""
    previous = db.info.get(CURRENT_MODEL_CHANGE_KEY)
    db.info[CURRENT_MODEL_CHANGE_KEY] = True
    if db.get_bind().dialect.name == "postgresql":
        # Transaction-local switch read by the zwm_guard_snapshot_activation trigger (A4.1).
        db.execute(text("SELECT set_config('zwm.allow_current_change', 'on', true)"))
    try:
        yield
    finally:
        if previous is None:
            db.info.pop(CURRENT_MODEL_CHANGE_KEY, None)
        else:
            db.info[CURRENT_MODEL_CHANGE_KEY] = previous


def _current_model(db: Session) -> Optional[ModelVersion]:
    return (db.query(ModelVersion).filter(ModelVersion.is_current.is_(True))
            .order_by(ModelVersion.updated_at.desc()).first())


def _active_deployment(db: Session) -> Optional[ModelDeployment]:
    return (db.query(ModelDeployment).filter(ModelDeployment.status == DEP_ACTIVE)
            .order_by(ModelDeployment.finished_at.desc()).first())


def _latest_evaluation(db: Session, model_id: str) -> Optional[ModelEvaluation]:
    return (db.query(ModelEvaluation).filter(ModelEvaluation.model_id == model_id)
            .order_by(ModelEvaluation.created_at.desc()).first())


def _decision_for(db: Session, evaluation_id: str) -> Optional[ModelApproval]:
    return db.query(ModelApproval).filter(ModelApproval.evaluation_id == evaluation_id).first()


def _reload_cache() -> None:
    from app.services.model_cache import YOLOModelCache
    YOLOModelCache().reload()


def _default_inspect(weights_path: str):
    """Class names of a weights file (real YOLO load; replaced by fakes in tests)."""
    return ultralytics_model_names(weights_path)


def _default_warm(expected_sha: str) -> None:
    """Load the serving model through the shared cache; raise unless it is usable and is the target."""
    from app.services.model_cache import YOLOModelCache
    cache = YOLOModelCache()
    cache.reload()
    if cache.get_model(expected_sha=expected_sha) is None or cache.loaded_sha256 != expected_sha:
        raise _StageError("serving model is not available after the switch")


def _fsync(path: Path) -> None:
    with open(path, "rb+") as fh:
        os.fsync(fh.fileno())


def _copy_verified(src: Path, dst: Path, sha: str) -> None:
    """Copy src to dst through a verified temp file + os.replace (dst gets a fresh mtime)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        shutil.copyfile(src, tmp)
        _fsync(tmp)
        if _sha256(tmp) != sha:
            raise _StageError(f"copy of {dst.name} does not match its expected SHA-256")
        replace_with_retry(tmp, dst)          # Windows: retried while a reader holds dst open
    finally:
        if tmp.exists():
            tmp.unlink()


def _retain(src: Path, name: str, sha: str) -> Path:
    """Immutable, content-addressed retained copy. An existing copy is verified, never overwritten."""
    dst = _deployed_dir() / name
    if dst.exists():
        if _sha256(dst) != sha:
            raise _StageError(f"retained artifact {name} is corrupted")
        return dst
    if _sha256(src) != sha:
        raise _StageError("source weights do not match the expected SHA-256")
    _copy_verified(src, dst, sha)
    return dst


def _install(src: Path, sha: str) -> None:
    """Atomically replace the serving file with a verified copy of src."""
    serving = _serving_path()
    _copy_verified(src, serving, sha)
    if _sha256(serving) != sha:
        raise _StageError("serving file does not match the deployed artifact after the switch")


def _restore_serving(previous_sha: Optional[str], previous_artifact: Optional[str], target_sha: str) -> bool:
    """Put the serving file back to its pre-deployment state. False = could not be done safely."""
    serving = _serving_path()
    try:
        current = _file_sha(serving)
        if current == previous_sha:
            return True
        if current not in (target_sha, None):
            logger.error("DEPLOYMENT_RESTORE_SKIPPED | serving file was changed by another writer")
            return False
        if previous_sha is None:
            serving.unlink(missing_ok=True)          # nothing was served before; the target stays retained
            return True
        backup = _deployed_dir() / (previous_artifact or "")
        if not previous_artifact or not backup.is_file() or _sha256(backup) != previous_sha:
            logger.error("DEPLOYMENT_RESTORE_FAILED | retained backup of the previous model is missing or corrupted")
            return False
        _install(backup, previous_sha)
        return True
    except Exception:
        logger.exception("DEPLOYMENT_RESTORE_FAILED")
        return False


def _safe_error(stage: str, exc: Exception) -> str:
    if isinstance(exc, _StageError):
        return f"{stage}: {exc}"
    if isinstance(exc, _LeaseLost):
        return f"{stage}: deployment lease was lost (recovered by another process)"
    ref = uuid.uuid4().hex[:8]
    logger.error("DEPLOYMENT_ERROR | ref=%s | stage=%s", ref, stage, exc_info=exc)
    return f"{stage}: {type(exc).__name__} (ref {ref})"


# ---------------------------------------------------------------------------
# 1. Review (approve / reject)
# ---------------------------------------------------------------------------

def _snapshot_candidate(db: Session, model_id: str):
    mv = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if mv is None:
        raise LookupError("model_not_found")
    job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).first()
    if job is None or job.snapshot_id is None:
        raise ReviewError("only snapshot-trained candidates go through approval", status_code=422)
    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == job.snapshot_id).first()
    return mv, job, snapshot


def _evaluation_of(db: Session, model_id: str, evaluation_id: str) -> ModelEvaluation:
    ev = db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == evaluation_id).first()
    if ev is None or ev.model_id != model_id:
        raise LookupError("evaluation_not_found")
    return ev


def _class_map_problems(snapshot: Optional[TrainingSnapshot]) -> list:
    if snapshot is None:
        return ["the candidate's snapshot no longer exists"]
    cmap = snapshot.class_map or []
    indices = sorted(c.get("yolo_index") for c in cmap)
    names = [c.get("class_name") for c in cmap]
    if not cmap or indices != list(range(len(cmap))) or len(set(names)) != len(names):
        return ["the frozen class mapping is empty or not a contiguous, unique YOLO index mapping"]
    return []


def _approval_problems(db: Session, job: TrainingJob, snapshot, ev: ModelEvaluation) -> list:
    problems = []
    if job.status != "completed":
        problems.append(f"training job is '{job.status}', not completed")
    latest = _latest_evaluation(db, ev.model_id)
    if latest is not None and latest.evaluation_id != ev.evaluation_id:
        problems.append("a newer evaluation exists for this candidate; review the latest evaluation")
    if ev.status != EVAL_PASSED or ev.gate_decision != DECISION_ELIGIBLE:
        state = ev.gate_decision or ev.status
        problems.append(f"evaluation is not eligible for approval (status '{ev.status}', decision '{state}')")
    if ev.job_id != job.job_id or ev.snapshot_id != job.snapshot_id:
        problems.append("evaluation does not belong to this candidate's training job and snapshot")
    if ev.dataset_manifest_path != job.dataset_manifest_path or not os.path.isfile(ev.dataset_manifest_path or ""):
        problems.append("the evaluated snapshot dataset manifest is missing or no longer referenced by the job")
    weights = job.best_model_path
    if not weights or not os.path.isfile(weights):
        problems.append("candidate weights file is missing")
    elif ev.weights_path != weights or _sha256(Path(weights)) != ev.weights_sha256:
        problems.append("candidate weights changed since they were evaluated")
    return problems + _class_map_problems(snapshot)


def _new_decision(db, mv, job, snapshot, ev, decision, actor_id, reason) -> ModelApproval:
    return ModelApproval(
        model_id=mv.model_id, model_version=mv.version, job_id=job.job_id, snapshot_id=job.snapshot_id,
        evaluation_id=ev.evaluation_id, evaluation_config_hash=ev.config_hash, evaluation_status=ev.status,
        gate_decision=ev.gate_decision, weights_sha256=ev.weights_sha256,
        class_map_sha256=_json_sha(snapshot.class_map if snapshot else None),
        manifest_sha256=_file_sha(ev.dataset_manifest_path),
        decision=decision, reason=reason, decided_by=actor_id, decided_at=_now(),
    )


def _commit_decision(db: Session, ap: ModelApproval, event_type: str):
    _event(db, event_type, actor_id=ap.decided_by, model_id=ap.model_id, approval_id=ap.approval_id,
           evaluation_id=ap.evaluation_id, weights_sha256=ap.weights_sha256, reason=ap.reason)
    try:
        db.commit()
    except IntegrityError:                       # concurrent decision on the same evaluation
        db.rollback()
        existing = _decision_for(db, ap.evaluation_id)
        if existing is not None and existing.decision == ap.decision:
            return existing, False
        raise ReviewError("a contradictory decision was recorded concurrently for this evaluation")
    db.refresh(ap)
    return ap, True


def approve_candidate(db: Session, model_id: str, evaluation_id: str, actor_id: str,
                      reason: Optional[str] = None) -> tuple:
    """Explicit approval of one A3 evaluation. Returns (approval, created); repeats are idempotent."""
    if not actor_id:
        raise ReviewError("an authenticated administrator is required", status_code=403)
    mv, job, snapshot = _snapshot_candidate(db, model_id)
    ev = _evaluation_of(db, model_id, evaluation_id)
    existing = _decision_for(db, evaluation_id)
    if existing is not None:
        if existing.decision == APPROVED:
            return existing, False
        raise ReviewError(f"this evaluation was already {existing.decision}; a new evaluation is required for re-review")
    problems = _approval_problems(db, job, snapshot, ev)
    if problems:
        _event(db, "approval_refused", actor_id=actor_id, model_id=model_id, evaluation_id=evaluation_id,
               reasons=problems)
        db.commit()
        raise ReviewError(problems[0], problems)
    ap = _new_decision(db, mv, job, snapshot, ev, APPROVED, actor_id, reason)
    ap.approval_id = str(uuid.uuid4())
    db.add(ap)
    logger.info("CANDIDATE_APPROVED | model_id=%s | evaluation_id=%s | by=%s", model_id, evaluation_id, actor_id)
    return _commit_decision(db, ap, "approval_granted")


def reject_candidate(db: Session, model_id: str, evaluation_id: str, actor_id: str, reason: str) -> tuple:
    """Record a rejection. Weights and evaluation results are kept. Returns (decision, created)."""
    if not actor_id:
        raise ReviewError("an authenticated administrator is required", status_code=403)
    if not reason or not reason.strip():
        raise ReviewError("a rejection reason is required", status_code=422)
    mv, job, snapshot = _snapshot_candidate(db, model_id)
    ev = _evaluation_of(db, model_id, evaluation_id)
    existing = _decision_for(db, evaluation_id)
    if existing is not None:
        if existing.decision == REJECTED:
            return existing, False
        raise ReviewError("this evaluation was already approved; a new evaluation is required for re-review")
    latest = _latest_evaluation(db, model_id)
    if latest is not None and latest.evaluation_id != evaluation_id:
        raise ReviewError("a newer evaluation exists for this candidate; review the latest evaluation")
    if mv.is_current:
        raise ReviewError("the active model cannot be rejected; roll back to another model first")
    if db.query(ModelDeployment).filter(ModelDeployment.model_id == model_id,
                                        ModelDeployment.status.in_(_IN_FLIGHT)).first():
        raise ReviewError("this candidate is being deployed")
    ap = _new_decision(db, mv, job, snapshot, ev, REJECTED, actor_id, reason.strip())
    ap.approval_id = str(uuid.uuid4())
    db.add(ap)
    logger.info("CANDIDATE_REJECTED | model_id=%s | evaluation_id=%s | by=%s", model_id, evaluation_id, actor_id)
    return _commit_decision(db, ap, "approval_rejected")


# ---------------------------------------------------------------------------
# 2. Activation preconditions (re-verified at every activation)
# ---------------------------------------------------------------------------

def verify_activation_preconditions(db: Session, mv: ModelVersion, job: TrainingJob) -> dict:
    """
    Checks 1-8 of the A4 contract for a snapshot candidate (9 = class names of the
    staged file and 10 = the in-flight lock happen inside the engine).
    Returns {approval, evaluation, snapshot, reasons, evidence_changed}.
    """
    reasons, evidence_changed = [], False
    out = {"approval": None, "evaluation": None, "snapshot": None, "reasons": reasons}
    if job.status != "completed":
        reasons.append(f"training job is '{job.status}', not completed")
    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == job.snapshot_id).first()
    out["snapshot"] = snapshot
    ev = _latest_evaluation(db, mv.model_id)
    out["evaluation"] = ev
    if ev is None:
        reasons.append("candidate has no A3 evaluation")
        return {**out, "evidence_changed": False}
    decision = _decision_for(db, ev.evaluation_id)
    if decision is None:
        older = (db.query(ModelApproval).filter(ModelApproval.model_id == mv.model_id,
                                                ModelApproval.decision == APPROVED)
                 .order_by(ModelApproval.decided_at.desc()).first())
        if older is not None:
            out["approval"] = older
            reasons.append("a newer evaluation replaced the approved one; the candidate must be re-reviewed")
            return {**out, "evidence_changed": True}
        reasons.append("candidate has not been approved by an administrator")
        return {**out, "evidence_changed": False}
    if decision.decision != APPROVED:
        reasons.append("candidate was rejected")
        return {**out, "evidence_changed": False}
    ap = decision
    out["approval"] = ap
    if ev.status != EVAL_PASSED or ev.gate_decision != DECISION_ELIGIBLE or ap.gate_decision != DECISION_ELIGIBLE:
        reasons.append("the approved evaluation did not pass its quality gates")
    if ev.config_hash != ap.evaluation_config_hash:
        reasons.append("evaluation configuration changed since approval")
        evidence_changed = True
    if not (job.snapshot_id == ev.snapshot_id == ap.snapshot_id) or ap.job_id != job.job_id:
        reasons.append("candidate no longer matches the approved training job / snapshot")
        evidence_changed = True
    if snapshot is None or _json_sha(snapshot.class_map) != ap.class_map_sha256:
        reasons.append("the snapshot's frozen class mapping changed since approval")
        evidence_changed = True
    if job.dataset_manifest_path != ev.dataset_manifest_path or _file_sha(ev.dataset_manifest_path) != ap.manifest_sha256:
        reasons.append("the snapshot dataset manifest is missing or changed since approval")
        evidence_changed = True
    weights = job.best_model_path
    if not weights or not os.path.isfile(weights):
        reasons.append("candidate weights file is missing")
        evidence_changed = True
    elif _sha256(Path(weights)) != ap.weights_sha256 or ap.weights_sha256 != ev.weights_sha256:
        reasons.append("candidate weights changed since approval (SHA-256 mismatch)")
        evidence_changed = True
    reasons.extend(_class_map_problems(snapshot))
    return {**out, "evidence_changed": evidence_changed}


# ---------------------------------------------------------------------------
# 3. Deployment engine
# ---------------------------------------------------------------------------

def _fenced(db: Session, deployment_id: str, token: str, event: Optional[tuple] = None, **fields) -> None:
    dep = (db.query(ModelDeployment).filter(ModelDeployment.deployment_id == deployment_id)
           .with_for_update().populate_existing().one())
    if dep.lease_token != token or dep.status not in _IN_FLIGHT:
        db.rollback()
        raise _LeaseLost()
    if "status" in fields:
        _transition(dep, fields.pop("status"))
    for key, value in fields.items():
        setattr(dep, key, value)
    if event:
        event_type, kwargs = event
        _event(db, event_type, **kwargs)
    db.commit()


def _finalize(db: Session, deployment_id: str, token: str, success_event: str, actor_id) -> None:
    """One transaction: demote the old model, promote the target, close the deployment."""
    dep = (db.query(ModelDeployment).filter(ModelDeployment.deployment_id == deployment_id)
           .with_for_update().populate_existing().one())
    if dep.lease_token != token or dep.status != DEP_ACTIVATING:
        db.rollback()
        raise _LeaseLost()
    with allow_current_change(db):
        db.query(ModelVersion).filter(ModelVersion.is_current.is_(True)).update(
            {"is_current": False}, synchronize_session=False)
        target = (db.query(ModelVersion).filter(ModelVersion.model_id == dep.model_id)
                  .with_for_update().populate_existing().one())
        target.is_current = True
        replaced_status = DEP_ROLLED_BACK if dep.kind == KIND_ROLLBACK else DEP_SUPERSEDED
        for old in db.query(ModelDeployment).filter(ModelDeployment.status == DEP_ACTIVE).all():
            _transition(old, replaced_status)
            old.replaced_by = dep.deployment_id
        _transition(dep, DEP_ACTIVE)
        dep.finished_at = _now()
        dep.inflight = None
        dep.lease_token = None
        dep.lease_expires_at = None
        _event(db, success_event, actor_id=actor_id, model_id=dep.model_id, deployment_id=dep.deployment_id,
               approval_id=dep.approval_id, previous_model_id=dep.previous_model_id,
               weights_sha256=dep.weights_sha256, artifact=dep.artifact_file)
        db.commit()


def _mark_failed(db: Session, deployment_id: str, token: str, message: str, failed_event: str, actor_id) -> None:
    try:
        dep = (db.query(ModelDeployment).filter(ModelDeployment.deployment_id == deployment_id)
               .with_for_update().populate_existing().one())
        if dep.lease_token != token or dep.status not in _IN_FLIGHT:
            db.rollback()
            return
        _transition(dep, DEP_FAILED)
        dep.error_message = message
        dep.finished_at = _now()
        dep.inflight = None
        dep.lease_token = None
        dep.lease_expires_at = None
        _event(db, failed_event, actor_id=actor_id, model_id=dep.model_id, deployment_id=deployment_id,
               approval_id=dep.approval_id, error=message, previous_model_preserved=True)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("DEPLOYMENT_MARK_FAILED_ERROR | deployment_id=%s (left for recovery)", deployment_id)


def _refuse(db: Session, kind: str, model_id: Optional[str], actor_id, reasons: list, stage: str,
            approval_id=None, status_code: int = 409, extra_events: tuple = ()):
    requested, _, _, failed = _EVENTS[kind]
    _event(db, requested, actor_id=actor_id, model_id=model_id, approval_id=approval_id)
    for name in extra_events:
        _event(db, name, actor_id=actor_id, model_id=model_id, approval_id=approval_id, reasons=reasons)
    _event(db, failed, actor_id=actor_id, model_id=model_id, approval_id=approval_id, stage=stage, reasons=reasons)
    db.commit()
    raise PreconditionFailed(reasons[0], reasons, status_code=status_code)


class _DeploymentHeartbeat:
    """Renews the deployment lease from a separate session while the engine works (A4.1)."""

    def __init__(self, db: Session, deployment_id: str, token: str):
        import threading
        self._factory = sessionmaker(bind=db.get_bind(), autocommit=False, autoflush=False)
        self._id, self._token = deployment_id, token
        self._stop = threading.Event()
        self.lost = False
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"deploy-lease-{deployment_id[:8]}")

    def _run(self):
        while not self._stop.wait(settings.DEPLOYMENT_HEARTBEAT_SECONDS):
            s = self._factory()
            try:
                n = (s.query(ModelDeployment)
                     .filter(ModelDeployment.deployment_id == self._id, ModelDeployment.lease_token == self._token,
                             ModelDeployment.status.in_(_IN_FLIGHT))
                     .update({"lease_expires_at": _now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS)},
                             synchronize_session=False))
                s.commit()
                if n == 0:
                    self.lost = True
                    return
            except Exception:
                s.rollback()
                logger.warning("DEPLOYMENT_HEARTBEAT_FAILED | deployment_id=%s", self._id, exc_info=True)
            finally:
                s.close()

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)
        return False


def _ensure_no_inflight(db: Session, kind: str, model_id: Optional[str], actor_id) -> None:
    """Refuse (audited) while another activation/rollback runs; the UNIQUE lock is the race backstop."""
    running = db.query(ModelDeployment).filter(ModelDeployment.status.in_(_IN_FLIGHT)).first()
    if running is None:
        return
    requested, _, _, failed = _EVENTS[kind]
    _event(db, requested, actor_id=actor_id, model_id=model_id)
    _event(db, failed, actor_id=actor_id, model_id=model_id, stage="lock",
           reasons=["another activation or rollback is in progress"], blocking_deployment_id=running.deployment_id)
    db.commit()
    raise DeploymentConflict("another activation or rollback is in progress")


def _deploy(db: Session, *, kind: str, mv: ModelVersion, sha: str, actor_id, reason: Optional[str],
            source: Optional[Path] = None, artifact_file: Optional[str] = None, approval=None,
            evaluation=None, snapshot_id=None, expected_names: Optional[list] = None, verify: bool = True,
            inspect_fn: Optional[Callable] = None, warm_fn: Optional[Callable] = None) -> dict:
    inspect_fn = inspect_fn or _default_inspect
    warm_fn = warm_fn or _default_warm
    requested_evt, started_evt, success_evt, failed_evt = _EVENTS[kind]
    token = str(uuid.uuid4())
    previous = _current_model(db)
    dep = ModelDeployment(
        deployment_id=str(uuid.uuid4()), kind=kind, status=DEP_PENDING, model_id=mv.model_id,
        model_version=mv.version, approval_id=approval.approval_id if approval else None,
        evaluation_id=evaluation.evaluation_id if evaluation else None, snapshot_id=snapshot_id,
        weights_sha256=sha, previous_model_id=previous.model_id if previous else None, reason=reason,
        requested_by=actor_id, requested_at=_now(), lease_token=token,
        lease_expires_at=_now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS),
        inflight=INFLIGHT_LOCK, serving_switched=False,
    )
    dep_id = dep.deployment_id
    db.add(dep)
    _event(db, requested_evt, actor_id=actor_id, model_id=mv.model_id, deployment_id=dep_id,
           approval_id=dep.approval_id, previous_model_id=dep.previous_model_id, reason=reason)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        running = db.query(ModelDeployment).filter(ModelDeployment.inflight == INFLIGHT_LOCK).first()
        _event(db, requested_evt, actor_id=actor_id, model_id=mv.model_id, approval_id=dep.approval_id)
        _event(db, failed_evt, actor_id=actor_id, model_id=mv.model_id, approval_id=dep.approval_id,
               stage="lock", reasons=["another activation or rollback is in progress"],
               blocking_deployment_id=running.deployment_id if running else None)
        db.commit()
        raise DeploymentConflict("another activation or rollback is in progress")

    previous_sha = previous_artifact = None
    marked_switch = False
    stage = "start"
    heartbeat = _DeploymentHeartbeat(db, dep_id, token)
    try:
        with heartbeat:
            _fenced(db, dep_id, token, status=DEP_ACTIVATING, started_at=_now(),
                    event=(started_evt, {"actor_id": actor_id, "model_id": mv.model_id, "deployment_id": dep_id}))

            stage = "staging"
            if artifact_file is None:
                artifact_file = f"{mv.model_id}_{sha[:16]}.pt"
                staged = _retain(source, artifact_file, sha)
            else:
                staged = _deployed_dir() / artifact_file
                if not staged.is_file() or _sha256(staged) != sha:
                    raise _StageError("retained artifact is missing or corrupted")
            serving = _serving_path()
            if serving.is_file():
                previous_sha = _sha256(serving)
                previous_artifact = f"serving_{previous_sha[:16]}.pt"
                _retain(serving, previous_artifact, previous_sha)
            _fenced(db, dep_id, token, artifact_file=artifact_file, previous_sha256=previous_sha,
                    previous_artifact_file=previous_artifact)

            if verify:
                stage = "validation"
                names = _names_list(inspect_fn(str(staged)))
                if expected_names is not None and names != expected_names:
                    raise _StageError("model classes do not match the frozen class mapping")

            stage = "switch"
            if heartbeat.lost:
                raise _LeaseLost()
            _fenced(db, dep_id, token, serving_switched=True)
            marked_switch = True
            _install(staged, sha)

            if verify:
                stage = "readiness"
                warm_fn(sha)

            stage = "commit"
            _finalize(db, dep_id, token, success_evt, actor_id)
    except Exception as exc:
        db.rollback()
        message = _safe_error(stage, exc)
        if isinstance(exc, _LeaseLost):
            # Recovery took this deployment over; the serving file is now its responsibility.
            _reload_cache()
            logger.error("DEPLOYMENT_LEASE_LOST | deployment_id=%s | %s", dep_id, message)
            raise DeploymentFailed(f"{kind.replace('_', ' ')} failed at {message}; reconciled by recovery",
                                   deployment_id=dep_id)
        restored = (not marked_switch) or _restore_serving(previous_sha, previous_artifact, sha)
        _reload_cache()
        if restored:
            _mark_failed(db, dep_id, token, message, failed_evt, actor_id)
        elif not restored:
            try:
                _event(db, failed_evt, actor_id=actor_id, model_id=mv.model_id, deployment_id=dep_id,
                       error=message, previous_model_preserved=False, recovery_required=True)
                db.commit()
            except Exception:
                db.rollback()
        logger.error("DEPLOYMENT_FAILED | deployment_id=%s | kind=%s | %s", dep_id, kind, message)
        raise DeploymentFailed(f"{kind.replace('_', ' ')} failed at {message}; the previous model was preserved"
                               if restored else
                               f"{kind.replace('_', ' ')} failed at {message}; serving file restore is pending "
                               "recovery", deployment_id=dep_id)

    _reload_cache()
    logger.info("MODEL_DEPLOYED | deployment_id=%s | kind=%s | model_id=%s | sha256=%s",
                dep_id, kind, mv.model_id, sha)
    db.expire_all()
    dep = db.query(ModelDeployment).filter(ModelDeployment.deployment_id == dep_id).one()
    return {"result": "rolled_back" if kind == KIND_ROLLBACK else "activated", "deployment": deployment_to_dict(dep)}


def activate_model_version(db: Session, model_id: str, actor_id, reason: Optional[str] = None, *,
                           inspect_fn: Optional[Callable] = None, warm_fn: Optional[Callable] = None) -> dict:
    """
    The only activation path for existing model versions. Snapshot candidates need a
    valid approval; legacy models keep v1.0 semantics behind ALLOW_LEGACY_MODEL_ACTIVATION.
    """
    recover_interrupted_deployments(db)
    mv = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if mv is None:
        raise LookupError("model_not_found")
    job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).first()
    legacy = job is None or job.snapshot_id is None
    kind = KIND_LEGACY if legacy else KIND_ACTIVATION
    _ensure_no_inflight(db, kind, model_id, actor_id)
    report = deployment_consistency(db)
    if report["state"] == "inconsistent":                      # fail closed; rollback stays available
        _refuse(db, kind, model_id, actor_id,
                ["deployment state is inconsistent (" + "; ".join(report["issues"]) + "); "
                 "run recovery or roll back first"], "consistency")
    if legacy:
        return _activate_legacy(db, mv, job, actor_id, reason)

    if mv.is_current:
        active = _active_deployment(db)
        return {"result": "already_active", "deployment": deployment_to_dict(active) if active else None}
    check = verify_activation_preconditions(db, mv, job)
    approval = check["approval"]
    if check["reasons"]:
        _refuse(db, KIND_ACTIVATION, model_id, actor_id, check["reasons"], "preconditions",
                approval_id=approval.approval_id if approval else None,
                extra_events=("approval_invalidated",) if check["evidence_changed"] and approval else ())
    return _deploy(db, kind=KIND_ACTIVATION, mv=mv, sha=approval.weights_sha256, actor_id=actor_id,
                   reason=reason, source=Path(job.best_model_path), approval=approval,
                   evaluation=check["evaluation"], snapshot_id=job.snapshot_id,
                   expected_names=_class_names(check["snapshot"].class_map),
                   inspect_fn=inspect_fn, warm_fn=warm_fn)


def _activate_legacy(db: Session, mv: ModelVersion, job: Optional[TrainingJob], actor_id, reason) -> dict:
    """v1.0 manual activation of a non-snapshot model, now locked, staged, backed up and audited."""
    if not settings.ALLOW_LEGACY_MODEL_ACTIVATION:
        _refuse(db, KIND_LEGACY, mv.model_id, actor_id, ["legacy model activation is disabled"], "preconditions")
    if job is None or job.status != "completed":
        _refuse(db, KIND_LEGACY, mv.model_id, actor_id,
                ["Cannot activate model from an incomplete/failed training job"], "preconditions", status_code=400)
    if not job.best_model_path or not os.path.isfile(job.best_model_path):
        _refuse(db, KIND_LEGACY, mv.model_id, actor_id, ["Model file is missing or invalid on disk"],
                "preconditions", status_code=400)
    sha = _sha256(Path(job.best_model_path))
    if mv.is_current and _file_sha(_serving_path()) == sha:
        active = _active_deployment(db)
        return {"result": "already_active", "deployment": deployment_to_dict(active) if active else None}
    # Legacy weights carry no evaluation or class map; v1.0 never load-checked them either.
    return _deploy(db, kind=KIND_LEGACY, mv=mv, sha=sha, actor_id=actor_id, reason=reason,
                   source=Path(job.best_model_path), verify=False)


# ---------------------------------------------------------------------------
# 4. Rollback
# ---------------------------------------------------------------------------

def _retained_artifact(db: Session, model_id: str) -> Optional[tuple]:
    """(artifact_file, sha256) of a copy of this model that was actually served before."""
    dep = (db.query(ModelDeployment).filter(ModelDeployment.model_id == model_id,
                                            ModelDeployment.status.in_(_SERVED))
           .order_by(ModelDeployment.finished_at.desc()).first())
    if dep is not None and dep.artifact_file:
        return dep.artifact_file, dep.weights_sha256
    dep = (db.query(ModelDeployment).filter(ModelDeployment.previous_model_id == model_id,
                                            ModelDeployment.previous_artifact_file.isnot(None),
                                            ModelDeployment.status.in_(_SERVED))
           .order_by(ModelDeployment.finished_at.desc()).first())
    if dep is not None:
        return dep.previous_artifact_file, dep.previous_sha256
    return None


def rollback_target(db: Session) -> Optional[str]:
    active = _active_deployment(db)
    return active.previous_model_id if active else None


def rollback(db: Session, actor_id, reason: str, target_model_id: Optional[str] = None, *,
             inspect_fn: Optional[Callable] = None, warm_fn: Optional[Callable] = None) -> dict:
    """Restore a previously served, retained and verified model artifact."""
    recover_interrupted_deployments(db)
    _ensure_no_inflight(db, KIND_ROLLBACK, target_model_id, actor_id)
    target_model_id = target_model_id or rollback_target(db)
    if not target_model_id:
        _refuse(db, KIND_ROLLBACK, None, actor_id, ["there is no previously deployed model to roll back to"],
                "preconditions")
    current = _current_model(db)
    if current is not None and current.model_id == target_model_id:
        active = _active_deployment(db)
        return {"result": "already_active", "deployment": deployment_to_dict(active) if active else None}
    mv = db.query(ModelVersion).filter(ModelVersion.model_id == target_model_id).first()
    if mv is None:
        _refuse(db, KIND_ROLLBACK, target_model_id, actor_id, ["rollback target model no longer exists"],
                "preconditions", status_code=404)
    retained = _retained_artifact(db, target_model_id)
    reasons = []
    if retained is None:
        reasons.append("rollback target was never deployed through the controlled workflow (no retained artifact)")
    else:
        path = _deployed_dir() / retained[0]
        if not path.is_file():
            reasons.append("retained rollback artifact is missing")
        elif _sha256(path) != retained[1]:
            reasons.append("retained rollback artifact is corrupted (SHA-256 mismatch)")
    job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).first()
    expected_names, snapshot_id = None, None
    if job is not None and job.snapshot_id is not None:
        snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == job.snapshot_id).first()
        problems = _class_map_problems(snapshot)
        reasons.extend(problems)
        if not problems:
            expected_names, snapshot_id = _class_names(snapshot.class_map), snapshot.snapshot_id
    if reasons:
        _refuse(db, KIND_ROLLBACK, target_model_id, actor_id, reasons, "preconditions")
    return _deploy(db, kind=KIND_ROLLBACK, mv=mv, sha=retained[1], actor_id=actor_id, reason=reason,
                   artifact_file=retained[0], snapshot_id=snapshot_id, expected_names=expected_names,
                   inspect_fn=inspect_fn, warm_fn=warm_fn)


# ---------------------------------------------------------------------------
# 5. Recovery of interrupted deployments
# ---------------------------------------------------------------------------

def recover_interrupted_deployments(db: Session, now: Optional[datetime] = None) -> list:
    """
    Reconcile deployments whose lease expired while pending/activating (process crash).
    The database still names the previous model (the switch commit never happened), so
    the serving file is put back to match it. Live deployments are never touched.
    """
    now = now or _now()
    ids = [d for (d,) in db.query(ModelDeployment.deployment_id).filter(
        ModelDeployment.status.in_(_IN_FLIGHT), ModelDeployment.lease_expires_at < now).all()]
    db.rollback()
    results = []
    for dep_id in ids:
        dep = (db.query(ModelDeployment).filter(ModelDeployment.deployment_id == dep_id)
               .populate_existing().first())
        lease = _aware(dep.lease_expires_at) if dep else None
        if dep is None or dep.status not in _IN_FLIGHT or lease is None or lease >= now:
            db.rollback()
            continue
        # Claim by compare-and-swap on the lease token (portable; works without row locks):
        # exactly one recoverer wins, a live owner or a concurrent recoverer makes it a no-op.
        mine = f"recovery-{uuid.uuid4().hex[:24]}"
        old_token = ModelDeployment.lease_token.is_(None) if dep.lease_token is None \
            else ModelDeployment.lease_token == dep.lease_token
        claimed = (db.query(ModelDeployment)
                   .filter(ModelDeployment.deployment_id == dep_id, old_token,
                           ModelDeployment.status.in_(_IN_FLIGHT), ModelDeployment.lease_expires_at < now)
                   .update({"lease_token": mine,
                            "lease_expires_at": now + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS)},
                           synchronize_session=False))
        db.commit()
        if claimed != 1:
            continue
        dep = db.query(ModelDeployment).filter(ModelDeployment.deployment_id == dep_id).populate_existing().one()
        current = _file_sha(_serving_path())
        if dep.kind == KIND_RECONCILE:
            outcome = "interrupted reconcile; the next maintenance run re-checks the serving file"
        elif not dep.serving_switched or current == dep.previous_sha256:
            outcome = "interrupted; serving model already matches the database (nothing to restore)"
        elif current == dep.weights_sha256:
            if not _restore_serving(dep.previous_sha256, dep.previous_artifact_file, dep.weights_sha256):
                db.rollback()
                logger.error("DEPLOYMENT_RECOVERY_DEFERRED | deployment_id=%s", dep_id)
                continue
            outcome = "interrupted after the serving file switch; previous model restored"
        else:
            outcome = "interrupted; serving file was changed by another writer and left untouched (manual check)"
        _, _, _, failed_evt = _EVENTS[dep.kind]
        _transition(dep, DEP_FAILED)
        dep.error_message = outcome
        dep.finished_at = now
        dep.inflight = None
        dep.lease_token = None
        dep.lease_expires_at = None
        _event(db, "deployment_recovered", model_id=dep.model_id, deployment_id=dep_id, outcome=outcome)
        _event(db, failed_evt, model_id=dep.model_id, deployment_id=dep_id, error=outcome, recovered=True)
        db.commit()
        _reload_cache()
        logger.warning("DEPLOYMENT_RECOVERED | deployment_id=%s | %s", dep_id, outcome)
        results.append({"deployment_id": dep_id, "outcome": outcome})
    return results


# ---------------------------------------------------------------------------
# 6. Read models (no filesystem paths)
# ---------------------------------------------------------------------------

def _ts(value) -> Optional[str]:
    return str(value) if value else None


def approval_to_dict(ap: ModelApproval) -> dict:
    return {
        "approval_id": ap.approval_id, "model_id": ap.model_id, "model_version": ap.model_version,
        "job_id": ap.job_id, "snapshot_id": ap.snapshot_id, "evaluation_id": ap.evaluation_id,
        "evaluation_config_hash": ap.evaluation_config_hash, "evaluation_status": ap.evaluation_status,
        "gate_decision": ap.gate_decision, "weights_sha256": ap.weights_sha256,
        "decision": ap.decision, "reason": ap.reason, "decided_by": ap.decided_by, "decided_at": _ts(ap.decided_at),
    }


def deployment_to_dict(dep: ModelDeployment) -> dict:
    return {
        "deployment_id": dep.deployment_id, "kind": dep.kind, "status": dep.status,
        "model_id": dep.model_id, "model_version": dep.model_version, "approval_id": dep.approval_id,
        "evaluation_id": dep.evaluation_id, "snapshot_id": dep.snapshot_id, "weights_sha256": dep.weights_sha256,
        "artifact": dep.artifact_file, "previous_model_id": dep.previous_model_id,
        "previous_sha256": dep.previous_sha256, "reason": dep.reason, "error_message": dep.error_message,
        "requested_by": dep.requested_by, "requested_at": _ts(dep.requested_at), "started_at": _ts(dep.started_at),
        "finished_at": _ts(dep.finished_at), "replaced_by": dep.replaced_by,
    }


def event_to_dict(e: DeploymentEvent) -> dict:
    return {"event_id": e.event_id, "event_type": e.event_type, "model_id": e.model_id,
            "deployment_id": e.deployment_id, "approval_id": e.approval_id, "actor_id": e.actor_id,
            "details": e.details, "created_at": _ts(e.created_at)}


def _deployment_state(dep: Optional[ModelDeployment]) -> Optional[str]:
    if dep is None:
        return None
    return {DEP_PENDING: "activation_pending", DEP_FAILED: "activation_failed"}.get(dep.status, dep.status)


def candidate_status(db: Session, mv: ModelVersion, deep: bool = False) -> dict:
    """Human review state and technical deployment state, kept separate, plus one lifecycle label."""
    ev = _latest_evaluation(db, mv.model_id)
    decision = _decision_for(db, ev.evaluation_id) if ev else None
    if ev is None:
        review = "not_evaluated"
    elif decision is not None:
        review = decision.decision
    elif ev.status in ("pending", "running"):
        review = "evaluation_in_progress"
    elif ev.status == EVAL_PASSED and ev.gate_decision == DECISION_ELIGIBLE:
        review = "awaiting_review"
    else:
        review = "not_eligible"
    dep = (db.query(ModelDeployment).filter(ModelDeployment.model_id == mv.model_id)
           .order_by(ModelDeployment.requested_at.desc()).first())
    dep_state = _deployment_state(dep)
    if mv.is_current:
        lifecycle = "active"
    elif dep_state in ("activation_pending", "activating"):
        lifecycle = dep_state
    elif review == REJECTED:
        lifecycle = "rejected"
    elif dep_state in ("rolled_back", "activation_failed"):
        lifecycle = dep_state
    else:
        lifecycle = review
    out = {
        "model_id": mv.model_id, "version": mv.version, "is_current": bool(mv.is_current),
        "review_state": review, "deployment_state": dep_state, "lifecycle": lifecycle,
        "latest_evaluation_id": ev.evaluation_id if ev else None,
        "latest_decision": approval_to_dict(decision) if decision else None,
        "latest_deployment": deployment_to_dict(dep) if dep else None,
    }
    if deep:
        job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).first()
        if mv.is_current:
            out["blocking_reasons"] = []
        elif job is None or job.snapshot_id is None:
            out["blocking_reasons"] = ["not a snapshot-trained candidate"]
        else:
            out["blocking_reasons"] = verify_activation_preconditions(db, mv, job)["reasons"]
        out["deployable"] = not mv.is_current and not out["blocking_reasons"]
    return out


def pending_candidates(db: Session) -> list:
    rows = (db.query(ModelVersion).join(TrainingJob, TrainingJob.job_id == ModelVersion.job_id)
            .filter(TrainingJob.snapshot_id.isnot(None)).order_by(ModelVersion.created_at.desc()).all())
    return [s for s in (candidate_status(db, mv) for mv in rows) if s["lifecycle"] == "awaiting_review"]


def deployment_overview(db: Session) -> dict:
    current = _current_model(db)
    active = _active_deployment(db)
    running = db.query(ModelDeployment).filter(ModelDeployment.status.in_(_IN_FLIGHT)).first()
    target = rollback_target(db)
    target_mv = db.query(ModelVersion).filter(ModelVersion.model_id == target).first() if target else None
    return {
        "consistency": deployment_consistency(db),
        "active_model": {"model_id": current.model_id, "version": current.version} if current else None,
        "active_deployment": deployment_to_dict(active) if active else None,
        "in_progress": deployment_to_dict(running) if running else None,
        "rollback_target": ({"model_id": target_mv.model_id, "version": target_mv.version,
                             "artifact_retained": _retained_artifact(db, target) is not None}
                            if target_mv else None),
    }


# ---------------------------------------------------------------------------
# 7. Legacy training hand-off (Block A4.1)
# ---------------------------------------------------------------------------

LEGACY_TRAINING_ACTOR = "system:legacy-training"


def activate_after_legacy_training(db: Session, model_id: str) -> str:
    """
    Legacy (non-snapshot) training registers its model inactive and then asks the
    deployment engine to activate it: same lock, staging, backup and audit as an
    admin activation. Any refusal or failure leaves the previous model serving.
    """
    if not settings.LEGACY_AUTO_ACTIVATE_TRAINED_MODELS:
        _event(db, "activation_skipped", actor_id=LEGACY_TRAINING_ACTOR, model_id=model_id,
               reason="LEGACY_AUTO_ACTIVATE_TRAINED_MODELS is disabled")
        db.commit()
        return "registered (automatic activation disabled)"
    try:
        result = activate_model_version(db, model_id, LEGACY_TRAINING_ACTOR,
                                        "automatic activation after legacy training")
        return result["result"]
    except DeploymentError as exc:
        db.rollback()
        logger.warning("LEGACY_AUTO_ACTIVATION_REFUSED | model_id=%s | %s", model_id, exc)
        return f"registered, not activated: {exc}"
    except Exception:
        db.rollback()
        logger.exception("LEGACY_AUTO_ACTIVATION_ERROR | model_id=%s", model_id)
        return "registered, not activated: activation error"


# ---------------------------------------------------------------------------
# 8. Consistency: database <-> deployment record <-> serving file <-> cache
# ---------------------------------------------------------------------------

def _current_ids(db: Session) -> list:
    return [m for (m,) in db.query(ModelVersion.model_id).filter(ModelVersion.is_current.is_(True)).all()]


def _expected_sha(db: Session) -> Optional[str]:
    """
    SHA-256 the database says should be served.
    None  = unmanaged (no controlled deployment has ever been recorded for the
            current state, e.g. a pre-A4 install): nothing to verify against.
    raise = the state is inconsistent and the expected model is unknown (fail closed).
    """
    from app.services.model_cache import IntegrityStateUnknown
    currents = _current_ids(db)
    if len(currents) > 1:
        raise IntegrityStateUnknown("more than one model is marked current")
    active = _active_deployment(db)
    if active is not None and currents == [active.model_id]:
        return active.weights_sha256
    running = db.query(ModelDeployment).filter(ModelDeployment.status.in_(_IN_FLIGHT)).first()
    if running is not None and running.previous_model_id == (currents[0] if currents else None):
        return running.previous_sha256            # mid-deployment: the database still names the previous model
    if active is not None and db.query(ModelVersion).filter(ModelVersion.model_id == active.model_id).first():
        raise IntegrityStateUnknown("the database's current model differs from the active deployment")
    return None


def serving_expectation(session_factory) -> Callable[[], Optional[str]]:
    """Integrity hook for YOLOModelCache (registered by the app)."""
    from app.services.model_cache import IntegrityStateUnknown

    def check() -> Optional[str]:
        try:
            db = session_factory()
        except Exception as exc:
            raise IntegrityStateUnknown(f"database unavailable ({type(exc).__name__})")
        try:
            return _expected_sha(db)
        except IntegrityStateUnknown:
            raise
        except Exception as exc:                  # database unreachable: fail closed
            logger.error("SERVING_EXPECTATION_UNAVAILABLE | %s", type(exc).__name__)
            raise IntegrityStateUnknown(f"database unavailable ({type(exc).__name__})")
        finally:
            db.close()
    return check


def deployment_consistency(db: Session) -> dict:
    from app.services.model_cache import YOLOModelCache
    currents = _current_ids(db)
    active = _active_deployment(db)
    running = db.query(ModelDeployment).filter(ModelDeployment.status.in_(_IN_FLIGHT)).first()
    serving_sha = _file_sha(_serving_path())
    cache_sha = YOLOModelCache().loaded_sha256
    issues, notes, expected = [], [], None
    if len(currents) > 1:
        issues.append("more than one model is marked current")
    if active is not None:
        active_exists = db.query(ModelVersion).filter(ModelVersion.model_id == active.model_id).first() is not None
        if not active_exists:
            notes.append("the last active deployment's model no longer exists (unmanaged)")
        elif currents != [active.model_id]:
            issues.append("the database's current model differs from the active deployment")
        else:
            expected = active.weights_sha256
            artifact = _deployed_dir() / (active.artifact_file or "")
            if not active.artifact_file or not artifact.is_file() or _sha256(artifact) != expected:
                issues.append("the active deployment's retained artifact is missing or corrupted")
            if serving_sha != expected:
                issues.append("the serving file does not match the active deployment")
    if cache_sha and serving_sha and cache_sha != serving_sha:
        notes.append("this process's cache holds a different file (it reloads on the next request)")
    if running is not None:
        state = "in_progress"
    elif issues:
        state = "inconsistent"
    elif expected is None:
        state = "unmanaged"
    else:
        state = "consistent"
    return {"state": state, "issues": issues, "notes": notes, "database_current_model_ids": currents,
            "active_deployment_id": active.deployment_id if active else None,
            "in_progress_deployment_id": running.deployment_id if running else None,
            "expected_sha256": expected, "serving_sha256": serving_sha, "cache_sha256": cache_sha}


def _fingerprint(report: dict) -> str:
    return _json_sha({k: report[k] for k in ("state", "issues", "database_current_model_ids",
                                             "active_deployment_id", "serving_sha256")})


def reconcile_serving_state(db: Session) -> dict:
    """
    Fail-closed reconciliation. The only automatic repair is putting the active
    deployment's verified, retained artifact back on the serving path (the database
    is the source of truth), done under the global deployment lock. Every other
    inconsistency is reported and audited (once per distinct state), never guessed at.
    """
    report = deployment_consistency(db)
    db.rollback()
    if report["state"] != "inconsistent":
        return {**report, "action": None}
    active = _active_deployment(db)
    repairable = report["issues"] == ["the serving file does not match the active deployment"]
    if not repairable:
        fp = _fingerprint(report)
        last = (db.query(DeploymentEvent).filter(DeploymentEvent.event_type == "consistency_alert")
                .order_by(DeploymentEvent.created_at.desc()).first())
        if last is None or (last.details or {}).get("fingerprint") != fp:
            _event(db, "consistency_alert", model_id=active.model_id if active else None,
                   deployment_id=active.deployment_id if active else None,
                   issues=report["issues"], fingerprint=fp)
            db.commit()
            logger.error("DEPLOYMENT_INCONSISTENT | %s", report["issues"])
        return {**report, "action": "alerted"}

    token = str(uuid.uuid4())
    rec = ModelDeployment(
        deployment_id=str(uuid.uuid4()), kind=KIND_RECONCILE, status=DEP_ACTIVATING, model_id=active.model_id,
        model_version=active.model_version, weights_sha256=active.weights_sha256,
        artifact_file=active.artifact_file, previous_sha256=report["serving_sha256"], serving_switched=True,
        reason="serving file did not match the active deployment", requested_at=_now(), started_at=_now(),
        lease_token=token, lease_expires_at=_now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS),
        inflight=INFLIGHT_LOCK,
    )
    rec_id = rec.deployment_id
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {**report, "action": "skipped (a deployment is in progress)"}
    try:
        _install(_deployed_dir() / active.artifact_file, active.weights_sha256)
        outcome, status = "serving file restored from the active deployment's artifact", DEP_RECONCILED
    except Exception as exc:
        outcome, status = _safe_error("reconcile", exc), DEP_FAILED
    rec = (db.query(ModelDeployment).filter(ModelDeployment.deployment_id == rec_id)
           .with_for_update().populate_existing().one())
    _transition(rec, status)
    rec.error_message = None if status == DEP_RECONCILED else outcome
    rec.finished_at, rec.inflight, rec.lease_token, rec.lease_expires_at = _now(), None, None, None
    _event(db, "serving_reconciled" if status == DEP_RECONCILED else "reconcile_failed",
           model_id=active.model_id, deployment_id=rec_id, active_deployment_id=active.deployment_id,
           outcome=outcome)
    db.commit()
    _reload_cache()
    logger.warning("SERVING_RECONCILED | %s", outcome)
    return {**deployment_consistency(db), "action": outcome}


def run_deployment_maintenance(db: Session) -> dict:
    """Scheduler / admin entry point: recover expired deployments, then reconcile."""
    recovered = recover_interrupted_deployments(db)
    return {"recovered": recovered, "consistency": reconcile_serving_state(db)}
