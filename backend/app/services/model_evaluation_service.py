"""
Candidate model evaluation & quality gates (ZWM v1.1.0, Block A3).

  admin request ──> ModelEvaluation(status=pending)            [idempotent per model + config]
        └─> dispatch_pending_evaluations()  (scheduler sweep / admin request) -> Celery
              └─> evaluate_candidate -> run_evaluation()   [worker, leased + fenced]
                    validate candidate/snapshot/manifest/class map/test split/hashes
                    build isolated TEST-only dataset -> evaluate -> metrics
                    baseline comparison (only if compatible) -> quality gates

Guarantees
----------
* Only the snapshot's held-out TEST split is ever evaluated; it is copied into
  an isolated directory that contains nothing else. Missing test images are an
  error, never substituted.
* Sources (images, labels, split assignments, prepared datasets, weights) are
  read-only. Evaluation never touches ModelVersion.is_current or YOLO_MODEL_PATH.
* Metrics are only recorded as the evaluator reports them; anything it cannot
  compute is stored as null and can never satisfy a gate.
* Quality gates come exclusively from the admin EvaluationPolicy. With no policy
  the decision is 'policy_not_configured'. 'passed' = eligible for human review.
"""
import hashlib
import json
import logging
import math
import os
import shutil
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.training import (
    EvaluationPolicy,
    ModelEvaluation,
    ModelVersion,
    TrainingJob,
    TrainingSnapshot,
    TrainingSnapshotImage,
)
from app.services.training_pipeline_service import (
    MANIFEST_SCHEMA,
    LeaseHeartbeat,
    _aware,
    _fenced_update,
    _label_errors,
    _sha256,
    new_worker_id,
)

logger = logging.getLogger(__name__)

EVAL_PENDING, EVAL_RUNNING, EVAL_PASSED, EVAL_FAILED, EVAL_ERROR = "pending", "running", "passed", "failed", "error"
DECISION_ELIGIBLE = "eligible_for_review"
DECISION_REJECTED = "rejected"
DECISION_INSUFFICIENT = "insufficient_evidence"
DECISION_NO_POLICY = "policy_not_configured"
EVALUATOR_ID = "ultralytics-val/1"

POLICY_FIELDS = (
    "min_test_images", "min_objects_per_class", "require_class_coverage", "min_map50", "min_map50_95",
    "min_precision", "min_recall", "min_class_recall", "max_map50_regression",
)
_METRIC_GATES = (("min_map50", "map50"), ("min_map50_95", "map50_95"),
                 ("min_precision", "precision"), ("min_recall", "recall"))


class EvaluationRequestError(Exception):
    pass


class EvaluationValidationError(Exception):
    def __init__(self, errors: list):
        self.errors = errors
        super().__init__("; ".join(errors[:30]) + (f" (+{len(errors) - 30} more)" if len(errors) > 30 else ""))


# ---------------------------------------------------------------------------
# 1. Policy
# ---------------------------------------------------------------------------

def get_policy(db: Session) -> dict:
    row = db.query(EvaluationPolicy).filter(EvaluationPolicy.id == 1).first()
    policy = {f: getattr(row, f) if row else None for f in POLICY_FIELDS}
    if policy["require_class_coverage"] is None:
        policy["require_class_coverage"] = True
    return policy


def policy_configured(policy: dict) -> bool:
    return policy.get("min_test_images") is not None and any(policy.get(k) is not None for k, _ in _METRIC_GATES)


def update_policy(db: Session, values: dict, admin_id: Optional[str]) -> dict:
    """values are pre-validated by the API schema; None clears a gate."""
    row = db.query(EvaluationPolicy).filter(EvaluationPolicy.id == 1).first()
    if row is None:
        row = EvaluationPolicy(id=1)
        db.add(row)
    for field, value in values.items():
        if field in POLICY_FIELDS:
            setattr(row, field, value)
    row.updated_by = admin_id
    db.commit()
    return {**get_policy(db), "configured": policy_configured(get_policy(db))}


# ---------------------------------------------------------------------------
# 2. Request (idempotent)
# ---------------------------------------------------------------------------

def evaluation_config(db: Session) -> dict:
    return {
        "evaluator": EVALUATOR_ID,
        "split": "test",
        "imgsz": settings.EVAL_IMGSZ,
        "conf": settings.EVAL_CONF,
        "iou": settings.EVAL_IOU,
        "policy": get_policy(db),
    }


def _config_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()


def candidate_context(db: Session, model_id: str):
    """(model_version, job, snapshot) for a snapshot-trained candidate, else EvaluationRequestError."""
    mv = db.query(ModelVersion).filter(ModelVersion.model_id == model_id).first()
    if mv is None:
        raise LookupError("model_not_found")
    job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).first()
    if job is None or job.snapshot_id is None:
        raise EvaluationRequestError("model was not trained from a locked snapshot; no held-out test split exists")
    if job.status != "completed":
        raise EvaluationRequestError(f"training job is '{job.status}', not completed")
    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == job.snapshot_id).one()
    return mv, job, snapshot


def request_evaluation(db: Session, model_id: str, requested_by: Optional[str] = None) -> tuple:
    """
    Create (or return the existing) evaluation for this candidate + current config.
    Returns (evaluation, created). An 'error' evaluation is reset to pending (retry).
    """
    mv, job, snapshot = candidate_context(db, model_id)
    weights = job.best_model_path
    if not weights or not os.path.isfile(weights):
        raise EvaluationRequestError("candidate weights file is missing")
    if not job.dataset_manifest_path or not os.path.isfile(job.dataset_manifest_path):
        raise EvaluationRequestError("prepared snapshot dataset manifest is missing")

    config = evaluation_config(db)
    chash = _config_hash(config)
    existing = (
        db.query(ModelEvaluation)
        .filter(ModelEvaluation.model_id == model_id, ModelEvaluation.config_hash == chash)
        .first()
    )
    if existing is not None:
        if existing.status == EVAL_ERROR:
            existing.status = EVAL_PENDING
            existing.dispatched_at = None
            existing.attempt_count = 0
            existing.error_message = None
            db.commit()
            return existing, True
        return existing, False

    evaluation = ModelEvaluation(
        model_id=model_id,
        job_id=job.job_id,
        snapshot_id=snapshot.snapshot_id,
        config_hash=chash,
        config=config,
        status=EVAL_PENDING,
        weights_path=weights,
        weights_sha256=_sha256(Path(weights)),
        dataset_manifest_path=job.dataset_manifest_path,
        model_version=mv.version,
        requested_by=requested_by,
        dispatch_attempts=0,
        attempt_count=0,
    )
    db.add(evaluation)
    try:
        db.commit()
    except IntegrityError:  # concurrent identical request
        db.rollback()
        return (
            db.query(ModelEvaluation)
            .filter(ModelEvaluation.model_id == model_id, ModelEvaluation.config_hash == chash)
            .one(),
            False,
        )
    db.refresh(evaluation)
    return evaluation, True


# ---------------------------------------------------------------------------
# 3. Validation + isolated test-split dataset
# ---------------------------------------------------------------------------

def _class_names(class_map: list) -> list:
    return [c["class_name"] for c in sorted(class_map or [], key=lambda c: c["yolo_index"])]


def _names_list(model_names) -> list:
    if isinstance(model_names, dict):
        return [model_names[k] for k in sorted(model_names, key=int)]
    return list(model_names or [])


def validate_evaluation_inputs(db: Session, evaluation: ModelEvaluation, model_names) -> dict:
    """
    Every check of Task 3. Returns the context for evaluation or raises
    EvaluationValidationError listing ALL problems.
    """
    errors = []
    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == evaluation.snapshot_id).one()
    job = db.query(TrainingJob).filter(TrainingJob.job_id == evaluation.job_id).one()
    class_names = _class_names(snapshot.class_map)

    # 1. weights
    weights = Path(evaluation.weights_path)
    if not weights.is_file():
        errors.append("candidate weights file is missing")
    elif _sha256(weights) != evaluation.weights_sha256:
        errors.append("candidate weights changed since the evaluation was requested")

    # 2. snapshot <-> manifest
    manifest_path = Path(evaluation.dataset_manifest_path)
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError):
        raise EvaluationValidationError(errors + ["dataset manifest is missing or unreadable"])
    if manifest.get("schema") != MANIFEST_SCHEMA:
        errors.append("unknown manifest schema")
    if manifest.get("snapshot_id") != snapshot.snapshot_id or manifest.get("job_id") != job.job_id:
        errors.append("manifest does not belong to this candidate's snapshot/training job")
    if job.snapshot_id != snapshot.snapshot_id or job.dataset_manifest_path != evaluation.dataset_manifest_path:
        errors.append("training job no longer points at this snapshot dataset")

    # 3. frozen class map
    if manifest.get("class_map") != snapshot.class_map:
        errors.append("manifest class map differs from the snapshot's frozen class map")
    if _names_list(model_names) != class_names:
        errors.append(f"model classes {_names_list(model_names)} do not match frozen class map {class_names}")

    # 4/5. test split membership + no overlap
    members = (
        db.query(TrainingSnapshotImage)
        .filter(TrainingSnapshotImage.snapshot_id == snapshot.snapshot_id)
        .all()
    )
    db_split = {m.image_id: m.split_type for m in members}
    entries = manifest.get("images", [])
    ids = [e.get("image_id") for e in entries]
    if len(ids) != len(set(ids)):
        errors.append("manifest lists an image more than once")
    if set(ids) != set(db_split) or any(db_split.get(e.get("image_id")) != e.get("split") for e in entries):
        errors.append("manifest membership/splits differ from the locked snapshot")
    test_entries = [e for e in entries if e.get("split") == "test"]
    db_test = {i for i, s in db_split.items() if s == "test"}
    if {e["image_id"] for e in test_entries} != db_test:
        errors.append("manifest test split differs from the snapshot's test split")
    if db_test & {i for i, s in db_split.items() if s in ("train", "val")}:
        errors.append("an image is assigned to both test and train/val")
    if not test_entries:
        errors.append("snapshot has no test images")

    # 6. hashes + label validity (prepared copies)
    root = manifest_path.parent
    valid_classes = {c["yolo_index"] for c in snapshot.class_map or []}
    for e in test_entries:
        for rel, digest in ((e.get("image_file"), e.get("image_sha256")), (e.get("label_file"), e.get("label_sha256"))):
            path = root / (rel or "")
            if not rel or not path.is_file():
                errors.append(f"test image {e['image_id']}: {rel} missing")
            elif _sha256(path) != digest:
                errors.append(f"test image {e['image_id']}: {rel} does not match manifest hash")
        if e.get("label_file") and (root / e["label_file"]).is_file():
            errors.extend(f"test image {e['image_id']}: {p}" for p in _label_errors(str(root / e["label_file"]), valid_classes))

    if errors:
        raise EvaluationValidationError(errors)
    return {"snapshot": snapshot, "job": job, "manifest": manifest, "root": root,
            "test_entries": test_entries, "class_names": class_names}


def build_test_only_dataset(evaluation: ModelEvaluation, ctx: dict) -> Path:
    """
    Copy ONLY the test split into an isolated directory and write a data.yaml whose
    train/val/test all point at those test images (ultralytics requires the keys).
    Copies are hash-verified. Returns the data.yaml path.
    """
    import yaml

    final_dir = Path(settings.EVALUATION_DIR) / evaluation.evaluation_id
    work = final_dir.with_name(f"{final_dir.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        (work / "images" / "test").mkdir(parents=True)
        (work / "labels" / "test").mkdir(parents=True)
        for e in ctx["test_entries"]:
            for rel, digest, kind in ((e["image_file"], e["image_sha256"], "images"),
                                      (e["label_file"], e["label_sha256"], "labels")):
                dst = work / kind / "test" / Path(rel).name
                shutil.copy2(ctx["root"] / rel, dst)
                if _sha256(dst) != digest:
                    raise EvaluationValidationError([f"copy of {rel} does not match manifest hash"])
        names = ctx["class_names"]
        with open(work / "data.yaml", "w", encoding="utf-8") as fh:
            yaml.safe_dump({"path": str(final_dir), "train": "images/test", "val": "images/test",
                            "test": "images/test", "nc": len(names), "names": names}, fh, sort_keys=False)
        if final_dir.exists():
            shutil.rmtree(work, ignore_errors=True)   # earlier attempt already published; reuse
        else:
            os.rename(work, final_dir)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return final_dir / "data.yaml"


def ground_truth_counts(ctx: dict) -> dict:
    """Objects per class in the TEST labels, and classes present anywhere in the snapshot."""
    def count(entries):
        counts = Counter()
        for e in entries:
            with open(ctx["root"] / e["label_file"]) as fh:
                for line in fh:
                    if line.strip():
                        counts[int(line.split()[0])] += 1
        return counts
    return {"test": count(ctx["test_entries"]), "snapshot": count(ctx["manifest"]["images"])}


# ---------------------------------------------------------------------------
# 4. Metrics normalisation (never fabricate)
# ---------------------------------------------------------------------------

def _metric(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v) or v < 0 or v > 1:
        return None
    return round(v, 6)


def normalize_metrics(raw: dict, class_map: list, gt: dict, test_images: int) -> dict:
    """
    raw = {"map50","map50_95","precision","recall",
           "per_class": [{"class_index","ap50","ap50_95","precision","recall"}]}
    Missing / invalid values become None. Per-class rows are keyed by YOLO index
    and associated with the frozen class map; classes the evaluator did not
    report get None metrics (not zero).
    """
    reported = {}
    for row in raw.get("per_class") or []:
        try:
            reported[int(row["class_index"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    per_class = []
    for c in sorted(class_map or [], key=lambda c: c["yolo_index"]):
        row = reported.get(c["yolo_index"], {})
        per_class.append({
            "class_index": c["yolo_index"],
            "class_name": c["class_name"],
            "class_code": c["class_code"],
            "category_id": c["category_id"],
            "gt_objects": gt["test"].get(c["yolo_index"], 0),
            "ap50": _metric(row.get("ap50")),
            "ap50_95": _metric(row.get("ap50_95")),
            "precision": _metric(row.get("precision")),
            "recall": _metric(row.get("recall")),
        })
    unknown = sorted(set(reported) - {c["yolo_index"] for c in class_map or []})
    return {
        "map50": _metric(raw.get("map50")),
        "map50_95": _metric(raw.get("map50_95")),
        "precision": _metric(raw.get("precision")),
        "recall": _metric(raw.get("recall")),
        "per_class": per_class,
        "unknown_reported_classes": unknown,
        "test_images": test_images,
        "gt_objects_total": sum(gt["test"].values()),
    }


# ---------------------------------------------------------------------------
# 5. Baseline comparison (only when genuinely comparable)
# ---------------------------------------------------------------------------

def baseline_candidate(db: Session, evaluation: ModelEvaluation, snapshot: TrainingSnapshot) -> dict:
    active = db.query(ModelVersion).filter(ModelVersion.is_current.is_(True)).first()
    if active is None:
        return {"status": "no_baseline", "reason": "no active model"}
    if active.model_id == evaluation.model_id:
        return {"status": "no_baseline", "reason": "candidate is the active model"}
    job = db.query(TrainingJob).filter(TrainingJob.job_id == active.job_id).first()
    base = {"model_id": active.model_id, "version": active.version}
    if job is None or job.snapshot_id is None:
        return {**base, "status": "incompatible",
                "reason": "active model was not trained from a snapshot; its class mapping cannot be verified"}
    base_snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == job.snapshot_id).first()
    if base_snapshot is None or base_snapshot.class_map != snapshot.class_map:
        return {**base, "status": "incompatible", "reason": "active model uses a different class mapping"}
    if not job.best_model_path or not os.path.isfile(job.best_model_path):
        return {**base, "status": "incompatible", "reason": "active model weights artifact is missing"}
    return {**base, "status": "comparable", "weights_path": job.best_model_path,
            "weights_sha256": _sha256(Path(job.best_model_path))}


def compare_with_baseline(baseline: dict, candidate: dict, evaluate_fn, inspect_fn, data_yaml: Path,
                          eval_kwargs: dict, ctx: dict, gt: dict) -> dict:
    """Evaluate the baseline on the SAME isolated test set and config; record deltas."""
    if baseline.get("status") != "comparable":
        return baseline
    try:
        if _names_list(inspect_fn(baseline["weights_path"])) != ctx["class_names"]:
            return {**baseline, "status": "incompatible", "reason": "active model classes differ from the frozen class map"}
        raw = evaluate_fn(baseline["weights_path"], data_yaml, **eval_kwargs)
    except Exception as exc:
        return {**baseline, "status": "error", "reason": f"baseline evaluation failed: {exc}"}
    if _sha256(Path(baseline["weights_path"])) != baseline["weights_sha256"]:
        return {**baseline, "status": "error", "reason": "baseline weights changed during evaluation"}
    base_metrics = normalize_metrics(raw, ctx["snapshot"].class_map, gt, len(ctx["test_entries"]))
    deltas = {
        k: (round(candidate[k] - base_metrics[k], 6) if candidate[k] is not None and base_metrics[k] is not None else None)
        for k in ("map50", "map50_95", "precision", "recall")
    }
    return {**baseline, "status": "compared", "conditions": "same isolated test split, same evaluator config",
            "metrics": base_metrics, "deltas": deltas}


# ---------------------------------------------------------------------------
# 6. Quality gates
# ---------------------------------------------------------------------------

def evidence_check(policy: dict, test_images: int, gt: dict) -> list:
    """Sample-size gates; evaluated before any model metric is trusted."""
    results = []
    if policy.get("min_test_images") is not None:
        results.append({"gate": "min_test_images", "threshold": policy["min_test_images"], "value": test_images,
                        "outcome": "pass" if test_images >= policy["min_test_images"] else "insufficient"})
    if policy.get("require_class_coverage", True):
        need = policy.get("min_objects_per_class") or 1
        for cls in sorted(gt["snapshot"]):
            have = gt["test"].get(cls, 0)
            results.append({"gate": "class_coverage", "class_index": cls, "threshold": need, "value": have,
                            "outcome": "pass" if have >= need else "insufficient"})
    return results


def apply_quality_gates(policy: dict, metrics: Optional[dict], evidence: list, baseline: dict) -> tuple:
    """Returns (decision, gate_results). Missing metrics never pass."""
    results = list(evidence)
    if not policy_configured(policy):
        return DECISION_NO_POLICY, results + [{
            "gate": "policy", "outcome": "not_configured",
            "reason": "an administrator must set min_test_images and at least one metric gate",
        }]
    if any(r["outcome"] == "insufficient" for r in results) or metrics is None:
        return DECISION_INSUFFICIENT, results

    def gate(name, threshold, value, **extra):
        outcome = "not_computable" if value is None else ("pass" if value >= threshold else "fail")
        results.append({"gate": name, "threshold": threshold, "value": value, "outcome": outcome, **extra})

    for policy_key, metric_key in _METRIC_GATES:
        if policy.get(policy_key) is not None:
            gate(policy_key, policy[policy_key], metrics.get(metric_key))
    if policy.get("min_class_recall") is not None:
        for row in metrics["per_class"]:
            if row["gt_objects"] > 0:
                gate("min_class_recall", policy["min_class_recall"], row["recall"], class_index=row["class_index"])
    if policy.get("max_map50_regression") is not None:
        if baseline.get("status") == "compared":
            delta = baseline["deltas"].get("map50")
            outcome = "not_computable" if delta is None else (
                "pass" if delta >= -policy["max_map50_regression"] else "fail")
            results.append({"gate": "max_map50_regression", "threshold": policy["max_map50_regression"],
                            "value": delta, "outcome": outcome})
        elif baseline.get("status") == "error":
            results.append({"gate": "max_map50_regression", "outcome": "not_computable",
                            "reason": baseline.get("reason")})
        else:
            results.append({"gate": "max_map50_regression", "outcome": "skipped",
                            "reason": f"baseline {baseline.get('status')}: {baseline.get('reason')}"})

    outcomes = {r["outcome"] for r in results}
    if "fail" in outcomes:
        return DECISION_REJECTED, results
    if "not_computable" in outcomes or "insufficient" in outcomes:
        return DECISION_INSUFFICIENT, results
    return DECISION_ELIGIBLE, results


# ---------------------------------------------------------------------------
# 7. Dispatch + worker runtime (leased, fenced, read-only on models)
# ---------------------------------------------------------------------------

def _send_eval_to_queue(evaluation_id: str) -> str:
    from app.tasks.training_tasks import evaluate_candidate
    result = evaluate_candidate.apply_async(
        args=[evaluation_id], retry=True,
        retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
    )
    return result.id


def _abandoned_before(now: datetime) -> datetime:
    return now - timedelta(seconds=settings.TRAINING_LEASE_GRACE_SECONDS)


def dispatch_pending_evaluations(db: Session, limit: int = 20) -> list:
    """Recover abandoned evaluations, then enqueue pending ones. Never evaluates inline."""
    now = datetime.now(timezone.utc)
    results = []
    abandoned = [e for (e,) in db.query(ModelEvaluation.evaluation_id).filter(
        ModelEvaluation.status == EVAL_RUNNING, ModelEvaluation.lease_expires_at < _abandoned_before(now)).all()]
    db.rollback()
    for eid in abandoned:
        ev = (db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == eid)
              .with_for_update(skip_locked=True).populate_existing().first())
        lease = _aware(ev.lease_expires_at) if ev else None
        if ev is None or ev.status != EVAL_RUNNING or lease is None or lease >= _abandoned_before(now):
            db.rollback()
            continue
        if ev.attempt_count >= settings.TRAINING_MAX_ATTEMPTS:
            ev.status, ev.error_message = EVAL_ERROR, f"abandoned by {ev.worker_id}; retry limit reached"
        else:
            ev.status, ev.dispatched_at = EVAL_PENDING, None
            ev.error_message = f"attempt {ev.attempt_count} abandoned by {ev.worker_id}"
        ev.worker_id, ev.lease_expires_at = None, None
        db.commit()
        results.append({"evaluation_id": eid, "result": ev.status})

    stale = now - timedelta(minutes=settings.TRAINING_DISPATCH_STALE_MINUTES)
    ids = [e for (e,) in db.query(ModelEvaluation.evaluation_id).filter(
        ModelEvaluation.status == EVAL_PENDING,
        or_(ModelEvaluation.dispatched_at.is_(None), ModelEvaluation.dispatched_at < stale),
    ).order_by(ModelEvaluation.created_at).limit(limit).all()]
    db.rollback()
    for eid in ids:
        ev = (db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == eid)
              .with_for_update(skip_locked=True).populate_existing().first())
        sent = _aware(ev.dispatched_at) if ev else None
        if ev is None or ev.status != EVAL_PENDING or (sent is not None and sent >= stale):
            db.rollback()
            continue
        ev.dispatch_attempts = (ev.dispatch_attempts or 0) + 1
        try:
            _send_eval_to_queue(eid)
            ev.dispatched_at = now
            results.append({"evaluation_id": eid, "result": "dispatched"})
        except Exception as exc:
            ev.error_message = f"queue dispatch failed (attempt {ev.dispatch_attempts}): {exc}"
            results.append({"evaluation_id": eid, "result": "dispatch_failed", "error": str(exc)})
        db.commit()
    return results


def claim_evaluation(db: Session, evaluation_id: str, worker_id: str) -> Optional[int]:
    now = datetime.now(timezone.utc)
    ev = (db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == evaluation_id)
          .with_for_update(skip_locked=True).populate_existing().first())
    if ev is None:
        db.rollback()
        return None
    lease = _aware(ev.lease_expires_at)
    abandoned = ev.status == EVAL_RUNNING and lease is not None and lease < _abandoned_before(now)
    if ev.status != EVAL_PENDING and not abandoned:
        db.rollback()
        return None
    if ev.attempt_count >= settings.TRAINING_MAX_ATTEMPTS:
        ev.status, ev.error_message = EVAL_ERROR, "retry limit reached"
        db.commit()
        return None
    ev.attempt_count += 1
    ev.status, ev.worker_id = EVAL_RUNNING, worker_id
    ev.started_at = now
    ev.lease_expires_at = now + timedelta(seconds=settings.TRAINING_LEASE_SECONDS)
    attempt = ev.attempt_count
    db.commit()
    return attempt


def run_evaluation(evaluation_id: str, *, session_factory, evaluate_fn: Callable, inspect_fn: Callable,
                   worker_id: Optional[str] = None, heartbeat_interval: Optional[float] = None) -> str:
    """
    Execute one evaluation. evaluate_fn(weights, data_yaml, split, imgsz, conf, iou) -> raw metrics;
    inspect_fn(weights) -> class names. Neither may write anything; this function
    never changes ModelVersion.is_current, weights, sources or snapshot data.
    """
    worker_id = worker_id or new_worker_id()
    db = session_factory()
    try:
        attempt = claim_evaluation(db, evaluation_id, worker_id)
    finally:
        db.close()
    if attempt is None:
        return f"Evaluation {evaluation_id} skipped (not claimable)"

    def finish(**fields):
        fields.setdefault("worker_id", None)
        fields.setdefault("lease_expires_at", None)
        return _fenced_update(session_factory, evaluation_id, worker_id, attempt, model=ModelEvaluation, **fields)

    with LeaseHeartbeat(session_factory, evaluation_id, worker_id, attempt, heartbeat_interval, model=ModelEvaluation) as hb:
        db = session_factory()
        try:
            ev = db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == evaluation_id).one()
            config = ev.config
            policy = config["policy"]
            eval_kwargs = {"split": "test", "imgsz": config["imgsz"], "conf": config["conf"], "iou": config["iou"]}
            started = time.monotonic()
            try:
                ctx = validate_evaluation_inputs(db, ev, inspect_fn(ev.weights_path))
                data_yaml = build_test_only_dataset(ev, ctx)
            except EvaluationValidationError as exc:
                finish(status=EVAL_ERROR, error_message=f"validation failed: {exc}",
                       evaluated_at=datetime.now(timezone.utc))
                return f"Evaluation {evaluation_id} error: validation failed"
            except Exception as exc:
                finish(status=EVAL_ERROR, error_message=f"evaluation setup failed: {exc}",
                       evaluated_at=datetime.now(timezone.utc))
                return f"Evaluation {evaluation_id} error: {exc}"

            gt = ground_truth_counts(ctx)
            test_images = len(ctx["test_entries"])
            evidence = evidence_check(policy, test_images, gt)
            baseline = baseline_candidate(db, ev, ctx["snapshot"])
            metrics = None
            if not any(r["outcome"] == "insufficient" for r in evidence):
                try:
                    raw = evaluate_fn(ev.weights_path, data_yaml, **eval_kwargs)
                except Exception as exc:
                    finish(status=EVAL_ERROR, error_message=f"evaluator failed: {exc}",
                           evaluated_at=datetime.now(timezone.utc))
                    return f"Evaluation {evaluation_id} error: evaluator failed"
                metrics = normalize_metrics(raw, ctx["snapshot"].class_map, gt, test_images)
                baseline = compare_with_baseline(baseline, metrics, evaluate_fn, inspect_fn, data_yaml,
                                                 eval_kwargs, ctx, gt)
            else:
                metrics_note = {"test_images": test_images, "gt_objects_per_class": dict(gt["test"]),
                                "model_evaluated": False}
                if baseline.get("status") == "comparable":
                    baseline = {**baseline, "status": "not_compared",
                                "reason": "candidate not evaluated (insufficient evidence)"}
            baseline.pop("weights_path", None)
            decision, gate_results = apply_quality_gates(policy, metrics, evidence, baseline)
            if hb.lost:
                return f"Evaluation {evaluation_id} lost its lease; result discarded"
            stored_metrics = metrics if metrics is not None else metrics_note
            ok = finish(
                status=EVAL_PASSED if decision == DECISION_ELIGIBLE else EVAL_FAILED,
                gate_decision=decision, metrics=stored_metrics, gate_results=gate_results, baseline=baseline,
                test_image_count=test_images, duration_seconds=round(time.monotonic() - started, 3),
                evaluated_at=datetime.now(timezone.utc), error_message=None,
            )
        finally:
            db.close()
    if not ok:
        return f"Evaluation {evaluation_id} lost its lease; result discarded"
    logger.info("CANDIDATE_EVALUATED | evaluation_id=%s | decision=%s", evaluation_id, decision)
    return f"Evaluation {evaluation_id} finished: {decision}"


# ---------------------------------------------------------------------------
# 8. Real evaluator adapters (used only by the Celery task; mocked in tests)
# ---------------------------------------------------------------------------

def ultralytics_model_names(weights_path: str):
    from ultralytics import YOLO
    return YOLO(weights_path).names


def ultralytics_evaluate(weights_path: str, data_yaml, split: str, imgsz: int, conf: float, iou: float) -> dict:
    """Run YOLO .val() on the isolated test-only dataset; report only what it computes."""
    from ultralytics import YOLO
    results = YOLO(weights_path).val(data=str(data_yaml), split=split, imgsz=imgsz, conf=conf, iou=iou,
                                     plots=False, save_json=False, verbose=False)
    box = results.box
    per_class = []
    for i, cls in enumerate(getattr(box, "ap_class_index", []) or []):
        per_class.append({
            "class_index": int(cls),
            "ap50": float(box.ap50[i]) if len(box.ap50) > i else None,
            "ap50_95": float(box.ap[i]) if len(box.ap) > i else None,
            "precision": float(box.p[i]) if len(box.p) > i else None,
            "recall": float(box.r[i]) if len(box.r) > i else None,
        })
    return {"map50": box.map50, "map50_95": box.map, "precision": box.mp, "recall": box.mr, "per_class": per_class}


def evaluation_to_dict(ev: ModelEvaluation, detail: bool = False) -> dict:
    data = {
        "evaluation_id": ev.evaluation_id,
        "model_id": ev.model_id,
        "model_version": ev.model_version,
        "job_id": ev.job_id,
        "snapshot_id": ev.snapshot_id,
        "status": ev.status,
        "gate_decision": ev.gate_decision,
        "test_image_count": ev.test_image_count,
        "error_message": ev.error_message,
        "created_at": str(ev.created_at) if ev.created_at else None,
        "evaluated_at": str(ev.evaluated_at) if ev.evaluated_at else None,
        "duration_seconds": ev.duration_seconds,
        "attempt_count": ev.attempt_count,
    }
    if detail:
        data.update({
            "config": ev.config,
            "config_hash": ev.config_hash,
            "weights_path": ev.weights_path,
            "weights_sha256": ev.weights_sha256,
            "dataset_manifest_path": ev.dataset_manifest_path,
            "metrics": ev.metrics,
            "gate_results": ev.gate_results,
            "baseline": ev.baseline,
        })
    return data
