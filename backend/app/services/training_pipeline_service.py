"""
Snapshot training pipeline (ZWM v1.1.0, Block A2).

  locked snapshot ──(same transaction)──> TrainingJob(trigger=auto, status=queued)   [outbox]
        │   (the finalize request returns here — nothing else runs in the request)
        └─> dispatch_pending_training_jobs()   [scheduler sweep / admin endpoints]
              recover abandoned leases, enqueue to Celery (enqueue only)
                └─> train_model -> run_snapshot_job()   [Celery worker]
                      claim lease -> prepare/verify dataset -> train -> candidate

Guarantees
----------
* One job per snapshot: UNIQUE(training_jobs.snapshot_id).
* Durable scheduling: the job row is committed with the snapshot; delivery is
  retried until ``dispatched_at`` is set. A crash between commit and queueing
  only delays delivery. Re-delivery is harmless: a worker must claim the job
  (FOR UPDATE SKIP LOCKED) and owns it through a heartbeat-renewed lease.
* Recovery: a running job whose lease expired (plus a grace period) is
  re-queued, up to TRAINING_MAX_ATTEMPTS attempts. All worker writes are fenced
  on (worker_id, attempt), so a stale worker can never overwrite a newer one.
* Toggle: jobs are created automatically only while ``auto_train_toggle`` is on.
  Snapshots locked while it was off never get a job implicitly; an admin must
  call ``create_snapshot_training_job`` (POST /api/ml/snapshots/{id}/train).
* Datasets are built ONLY from a snapshot's locked membership, validated, and
  written once to a job-specific directory with a manifest. Source images and
  labels are only read. Nothing is ever fabricated.

Splits (80/10/10)
-----------------
Assigned when a snapshot is locked and frozen on its membership rows:
  * images already in the previous snapshot keep their split (no leakage);
  * only the newly added images are allocated, so the cumulative totals hit
    val = test = round_half_up(N / 10), train = N - val - test
    (100 -> 80/10/10, 200 -> 160/20/20);
  * allocation is stratified by each image's primary YOLO class (largest
    remainder) and ordered by a seeded SHA-256 of the image id (deterministic).
Small datasets: N >= 3 always gets at least one val and one test image;
N < 3 cannot form three splits — such a snapshot is rejected at preparation.
"""
import hashlib
import json
import logging
import os
import shutil
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.image import Image
from app.models.setting import SystemSetting
from app.models.training import TrainingJob, TrainingSnapshot, TrainingSnapshotImage

logger = logging.getLogger(__name__)

SPLITS = ("train", "val", "test")
SPLIT_SEED = "zwm-split-v1"
MIN_SPLITTABLE_SIZE = 3
MANIFEST_SCHEMA = "zwm-snapshot-dataset/1"

JOB_TRIGGER_AUTO = "auto"
JOB_TRIGGER_ADMIN_SNAPSHOT = "admin_snapshot"
DATASET_PENDING = "pending"
DATASET_PREPARED = "prepared"
DATASET_FAILED = "failed"


# ---------------------------------------------------------------------------
# 1. Deterministic, leakage-free 80/10/10 split allocation
# ---------------------------------------------------------------------------

def split_targets(total: int) -> dict:
    """Exact cumulative split sizes for a snapshot of ``total`` images."""
    if total < MIN_SPLITTABLE_SIZE:
        return {"train": total, "val": 0, "test": 0}
    holdout = max(1, (total + 5) // 10)  # round half up of 10 %
    return {"train": total - 2 * holdout, "val": holdout, "test": holdout}


def _split_order_key(image_id: str) -> str:
    return hashlib.sha256(f"{SPLIT_SEED}:{image_id}".encode()).hexdigest()


def primary_class(class_ids) -> int:
    """Most frequent class of an image's label (ties -> lowest index); -1 if none."""
    if not class_ids:
        return -1
    counts = Counter(class_ids)
    best = max(counts.values())
    return min(c for c, n in counts.items() if n == best)


def _largest_remainder(quota: int, group_sizes: dict) -> dict:
    total = sum(group_sizes.values())
    if quota <= 0 or total == 0:
        return {g: 0 for g in group_sizes}
    raw = {g: quota * size / total for g, size in group_sizes.items()}
    alloc = {g: int(r) for g, r in raw.items()}
    for g in sorted(group_sizes, key=lambda g: (-(raw[g] - alloc[g]), g))[: quota - sum(alloc.values())]:
        alloc[g] += 1
    return alloc


def assign_splits(total_size: int, inherited: dict, new_items: list) -> dict:
    """
    Split assignment for the NEW images of a cumulative snapshot.

    inherited : {image_id: split} carried over unchanged from the previous snapshot
    new_items : [(image_id, primary_class)] for images added by this milestone
    Returns {image_id: split} for the new images only.
    """
    targets = split_targets(total_size)
    have = Counter(inherited.values())
    need_val = min(max(0, targets["val"] - have["val"]), len(new_items))
    need_test = min(max(0, targets["test"] - have["test"]), len(new_items) - need_val)

    groups = defaultdict(list)
    for image_id, cls in new_items:
        groups[cls].append(image_id)
    for cls in groups:
        groups[cls].sort(key=_split_order_key)

    result = {}
    for split, quota in (("val", need_val), ("test", need_test)):
        alloc = _largest_remainder(quota, {g: len(ids) for g, ids in groups.items() if ids})
        for g, k in alloc.items():
            for image_id in groups[g][:k]:
                result[image_id] = split
            groups[g] = groups[g][k:]
    for ids in groups.values():
        for image_id in ids:
            result[image_id] = "train"
    return result


def assign_splits_for_new_snapshot(db: Session, rows: list) -> dict:
    """
    Splits for a snapshot about to be locked. ``rows`` are (image_id,
    training_sequence, yolo_txt_path) in snapshot order. Previous snapshot
    assignments are inherited verbatim.
    """
    from app.services.training_dataset_service import read_yolo_class_ids

    previous = db.query(TrainingSnapshot).order_by(TrainingSnapshot.version.desc()).first()
    inherited = {}
    if previous is not None:
        inherited = {
            image_id: split
            for image_id, split in db.query(TrainingSnapshotImage.image_id, TrainingSnapshotImage.split_type)
            .filter(TrainingSnapshotImage.snapshot_id == previous.snapshot_id)
            .all()
            if split in SPLITS
        }
    current_ids = {r.image_id for r in rows}
    inherited = {k: v for k, v in inherited.items() if k in current_ids}
    new_items = [
        (r.image_id, primary_class(read_yolo_class_ids(r.yolo_txt_path) or []))
        for r in rows
        if r.image_id not in inherited
    ]
    return {**inherited, **assign_splits(len(rows), inherited, new_items)}


# ---------------------------------------------------------------------------
# 2. Automatic job creation (called inside the snapshot transaction)
# ---------------------------------------------------------------------------

def auto_training_enabled(db: Session) -> bool:
    row = db.query(SystemSetting.auto_train_toggle).filter(SystemSetting.id == 1).first()
    if row is None:
        # No settings row yet: SystemSetting.auto_train_toggle defaults to True.
        return bool(SystemSetting.__table__.c.auto_train_toggle.default.arg)
    return bool(row[0])


def _new_snapshot_job(snapshot: TrainingSnapshot, trigger: str) -> TrainingJob:
    return TrainingJob(
        version=f"snap-v{snapshot.version}",
        snapshot_id=snapshot.snapshot_id,
        trigger=trigger,
        status="queued",
        dataset_status=DATASET_PENDING,
        dispatch_attempts=0,
        class_counts=None,
    )


def create_auto_job_for_snapshot(db: Session, snapshot: TrainingSnapshot) -> Optional[TrainingJob]:
    """Add (not commit) the automatic job for a snapshot being locked, if enabled."""
    if not auto_training_enabled(db):
        logger.info("AUTO_TRAINING_DISABLED | snapshot=V%s | no job created", snapshot.version)
        return None
    job = _new_snapshot_job(snapshot, JOB_TRIGGER_AUTO)
    db.add(job)
    return job


class SnapshotJobExistsError(Exception):
    pass


def create_snapshot_training_job(db: Session, snapshot_id: int) -> TrainingJob:
    """Explicit admin action: train an existing snapshot that has no job (e.g. locked while auto-training was off)."""
    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == snapshot_id).first()
    if snapshot is None:
        raise LookupError("snapshot_not_found")
    if db.query(TrainingJob).filter(TrainingJob.snapshot_id == snapshot_id).first() is not None:
        raise SnapshotJobExistsError(snapshot_id)
    job = _new_snapshot_job(snapshot, JOB_TRIGGER_ADMIN_SNAPSHOT)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise SnapshotJobExistsError(snapshot_id)
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# 3. Immutable dataset preparation
# ---------------------------------------------------------------------------

class DatasetPreparationError(Exception):
    def __init__(self, errors: list):
        self.errors = errors
        super().__init__(self.report())

    def report(self, limit: int = 50) -> str:
        shown = "; ".join(self.errors[:limit])
        more = f" (+{len(self.errors) - limit} more)" if len(self.errors) > limit else ""
        return f"Dataset preparation failed with {len(self.errors)} problem(s): {shown}{more}"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _label_errors(txt_path: str, valid_classes: set) -> list:
    try:
        with open(txt_path, "r") as fh:
            lines = [line.strip() for line in fh if line.strip()]
    except OSError as exc:
        return [f"label unreadable ({exc})"]
    if not lines:
        return ["label is empty"]
    errors = []
    for n, line in enumerate(lines, 1):
        parts = line.split()
        if len(parts) != 5:
            errors.append(f"label line {n}: expected 5 values, got {len(parts)}")
            continue
        try:
            cls = int(parts[0])
            x, y, w, h = (float(p) for p in parts[1:])
        except ValueError:
            errors.append(f"label line {n}: non-numeric value")
            continue
        if cls not in valid_classes:
            errors.append(f"label line {n}: class {cls} not in frozen class map")
        if not all(0.0 <= v <= 1.0 for v in (x, y, w, h)) or w <= 0 or h <= 0:
            errors.append(f"label line {n}: coordinates out of normalized range")
    return errors


def _image_error(path: str) -> Optional[str]:
    try:
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            im.verify()
        return None
    except Exception as exc:
        return f"image unreadable ({exc.__class__.__name__})"


def validate_snapshot_membership(db: Session, snapshot: TrainingSnapshot) -> tuple:
    """Return (members, images_by_id, class_names, errors) without writing anything."""
    errors = []
    members = (
        db.query(TrainingSnapshotImage)
        .filter(TrainingSnapshotImage.snapshot_id == snapshot.snapshot_id)
        .order_by(TrainingSnapshotImage.position)
        .all()
    )
    if len(members) != snapshot.dataset_size:
        errors.append(f"membership has {len(members)} rows, snapshot dataset_size is {snapshot.dataset_size}")
    if [m.position for m in members] != list(range(len(members))):
        errors.append("membership positions are not contiguous")
    dup = [i for i, n in Counter(m.image_id for m in members).items() if n > 1]
    if dup:
        errors.append(f"duplicate image ids: {dup[:5]}")

    class_map = sorted(snapshot.class_map or [], key=lambda c: c["yolo_index"])
    indices = [c["yolo_index"] for c in class_map]
    if not class_map or indices != list(range(len(indices))):
        errors.append(f"frozen class map is missing or not contiguous: {indices}")
    class_names = [c["class_name"] for c in class_map]

    counts = Counter(m.split_type for m in members)
    if any(m.split_type not in SPLITS for m in members):
        errors.append("some images have no train/val/test assignment")
    elif any(counts[s] == 0 for s in SPLITS):
        errors.append(
            f"snapshot of {len(members)} images cannot form train/val/test "
            f"(minimum {MIN_SPLITTABLE_SIZE}); counts={dict(counts)}"
        )

    images = {
        i.image_id: i
        for i in db.query(Image).filter(Image.image_id.in_([m.image_id for m in members])).all()
    } if members else {}
    valid_classes = set(indices)
    for m in members:
        img = images.get(m.image_id)
        tag = f"image {m.image_id}"
        if img is None:
            errors.append(f"{tag}: image record missing")
            continue
        if not img.permanent_s3_path or not os.path.isfile(img.permanent_s3_path):
            errors.append(f"{tag}: source image file missing")
        else:
            problem = _image_error(img.permanent_s3_path)
            if problem:
                errors.append(f"{tag}: {problem}")
        if not img.yolo_txt_path or not os.path.isfile(img.yolo_txt_path):
            errors.append(f"{tag}: YOLO label file missing")
        else:
            errors.extend(f"{tag}: {e}" for e in _label_errors(img.yolo_txt_path, valid_classes))
    return members, images, class_names, errors


def dataset_dir_for(snapshot: TrainingSnapshot, job: TrainingJob) -> Path:
    return Path(settings.TRAINING_DATASETS_DIR) / f"snapshot_v{snapshot.version}_{job.job_id[:8]}"


def verify_prepared_dataset(final_dir: Path, snapshot: TrainingSnapshot, members: list, job_id: str) -> list:
    """Problems with an existing prepared dataset (empty list = intact and matching)."""
    manifest_path = final_dir / "manifest.json"
    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        return [f"manifest unreadable ({exc.__class__.__name__})"]
    errors = []
    if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("snapshot_id") != snapshot.snapshot_id \
            or manifest.get("job_id") != job_id:
        errors.append("manifest does not belong to this snapshot/job")
    expected = [(m.image_id, m.split_type) for m in members]
    found = [(e.get("image_id"), e.get("split")) for e in manifest.get("images", [])]
    if found != expected:
        errors.append("manifest membership/splits differ from the locked snapshot")
        return errors
    if not (final_dir / manifest.get("data_yaml", "data.yaml")).is_file():
        errors.append("data.yaml missing")
    for e in manifest["images"]:
        for rel, digest in ((e["image_file"], e["image_sha256"]), (e["label_file"], e["label_sha256"])):
            path = final_dir / rel
            if not path.is_file() or _sha256(path) != digest:
                errors.append(f"{rel}: missing or modified")
    for split in SPLITS:
        on_disk = {p.name for p in (final_dir / "images" / split).glob("*")} if (final_dir / "images" / split).is_dir() else set()
        listed = {Path(e["image_file"]).name for e in manifest["images"] if e["split"] == split}
        if on_disk != listed:
            errors.append(f"images/{split} contains unexpected or missing files")
    return errors


def prepare_snapshot_dataset(db: Session, job: TrainingJob) -> Path:
    """
    Build (or verify and reuse) the job-specific YOLO dataset for ``job.snapshot_id``
    and return its manifest path. Read-only on the DB and on source files.

    Concurrency: the directory is assembled in a private temp dir and published
    with an atomic rename. If another worker published first, its result is
    verified (membership, splits, SHA-256 of every file) and reused. A corrupt
    existing directory is moved aside (never deleted) and rebuilt.
    Raises DatasetPreparationError with every problem found.
    """
    import yaml

    snapshot = db.query(TrainingSnapshot).filter(TrainingSnapshot.snapshot_id == job.snapshot_id).one()
    final_dir = dataset_dir_for(snapshot, job)
    members, images, class_names, errors = validate_snapshot_membership(db, snapshot)
    if errors:
        raise DatasetPreparationError(errors)

    if final_dir.exists():
        if not verify_prepared_dataset(final_dir, snapshot, members, job.job_id):
            return final_dir / "manifest.json"
        quarantine = final_dir.with_name(f"{final_dir.name}.corrupt-{uuid.uuid4().hex[:8]}")
        os.rename(final_dir, quarantine)
        logger.error("SNAPSHOT_DATASET_QUARANTINED | job_id=%s | moved to %s", job.job_id, quarantine)

    final_dir.parent.mkdir(parents=True, exist_ok=True)
    work_dir = final_dir.with_name(f"{final_dir.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        for kind in ("images", "labels"):
            for split in SPLITS:
                (work_dir / kind / split).mkdir(parents=True, exist_ok=True)
        entries = []
        for m in members:
            img = images[m.image_id]
            src_img, src_lbl = Path(img.permanent_s3_path), Path(img.yolo_txt_path)
            rel_img = Path("images") / m.split_type / f"{m.image_id}{src_img.suffix.lower()}"
            rel_lbl = Path("labels") / m.split_type / f"{m.image_id}.txt"
            shutil.copy2(src_img, work_dir / rel_img)
            shutil.copy2(src_lbl, work_dir / rel_lbl)
            entries.append({
                "image_id": m.image_id,
                "position": m.position,
                "training_sequence": m.training_sequence,
                "split": m.split_type,
                "image_file": rel_img.as_posix(),
                "label_file": rel_lbl.as_posix(),
                "source_image": str(src_img),
                "source_label": str(src_lbl),
                "image_sha256": _sha256(work_dir / rel_img),
                "label_sha256": _sha256(work_dir / rel_lbl),
            })
        # Sources must not have changed while copying.
        for e in entries:
            if _sha256(Path(e["source_image"])) != e["image_sha256"] or _sha256(Path(e["source_label"])) != e["label_sha256"]:
                raise DatasetPreparationError([f"image {e['image_id']}: source changed during preparation"])

        split_counts = dict(Counter(e["split"] for e in entries))
        data_yaml = {
            "path": str(final_dir),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": len(class_names),
            "names": class_names,
        }
        with open(work_dir / "data.yaml", "w", encoding="utf-8") as fh:
            yaml.safe_dump(data_yaml, fh, sort_keys=False, allow_unicode=True)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_version": snapshot.version,
            "milestone_count": snapshot.milestone_count,
            "threshold": snapshot.threshold,
            "dataset_size": len(entries),
            "job_id": job.job_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "split_seed": SPLIT_SEED,
            "split_counts": split_counts,
            "class_map": snapshot.class_map,
            "data_yaml": "data.yaml",
            "images": entries,
        }
        with open(work_dir / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        problems = verify_prepared_dataset(work_dir, snapshot, members, job.job_id)
        if problems:
            raise DatasetPreparationError(problems)
        try:
            os.rename(work_dir, final_dir)  # atomic publish; fails if another worker won
        except OSError:
            shutil.rmtree(work_dir, ignore_errors=True)
            problems = verify_prepared_dataset(final_dir, snapshot, members, job.job_id)
            if problems:
                raise DatasetPreparationError([f"concurrently published dataset invalid: {p}" for p in problems])
            return final_dir / "manifest.json"
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    logger.info(
        "SNAPSHOT_DATASET_PREPARED | job_id=%s | snapshot=V%s | splits=%s | dir=%s",
        job.job_id, snapshot.version, split_counts, final_dir,
    )
    return final_dir / "manifest.json"


# ---------------------------------------------------------------------------
# 4. Outbox dispatch (enqueue only) + abandoned-job recovery
# ---------------------------------------------------------------------------

def _send_to_queue(job_id: str) -> str:
    """Hand the job to the existing Celery task. Returns the Celery task id."""
    from app.tasks.training_tasks import train_model

    result = train_model.apply_async(
        args=[job_id],
        retry=True,
        retry_policy={"max_retries": 2, "interval_start": 0, "interval_step": 0.5, "interval_max": 1},
    )
    return result.id


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    return ts if ts is None or ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _abandoned_before(now: datetime) -> datetime:
    return now - timedelta(seconds=settings.TRAINING_LEASE_GRACE_SECONDS)


def requeue_abandoned_jobs(db: Session, now: Optional[datetime] = None) -> list:
    """
    Running snapshot jobs whose lease expired more than LEASE_GRACE ago lost their
    worker (heartbeats stopped). Re-queue them, or fail them once attempts are used up.
    A job with a live lease is never touched, so no second attempt can start while
    the original worker is still heartbeating.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = _abandoned_before(now)
    ids = [
        job_id for (job_id,) in db.query(TrainingJob.job_id).filter(
            TrainingJob.snapshot_id.isnot(None),
            TrainingJob.status == "running",
            TrainingJob.lease_expires_at < cutoff,
        ).all()
    ]
    db.rollback()
    results = []
    for job_id in ids:
        job = (
            db.query(TrainingJob).filter(TrainingJob.job_id == job_id)
            .with_for_update(skip_locked=True).populate_existing().first()
        )
        lease = _aware(job.lease_expires_at) if job else None
        if job is None or job.status != "running" or lease is None or lease >= cutoff:
            db.rollback()
            continue
        note = f"attempt {job.attempt_count} abandoned by {job.worker_id} (lease expired {lease.isoformat()})"
        if job.attempt_count >= settings.TRAINING_MAX_ATTEMPTS:
            job.status = "failed"
            job.completed_at = now
            job.error_message = f"{note}; retry limit {settings.TRAINING_MAX_ATTEMPTS} reached"
            results.append({"job_id": job_id, "result": "failed_retries_exhausted"})
        else:
            job.status = "queued"
            job.dispatched_at = None
            job.error_message = note
            results.append({"job_id": job_id, "result": "requeued"})
        job.worker_id = None
        job.lease_expires_at = None
        db.commit()
        logger.warning("TRAINING_JOB_ABANDONED | job_id=%s | %s", job_id, results[-1]["result"])
    return results


def dispatch_pending_training_jobs(db: Session, limit: int = 20) -> list:
    """
    Outbox sweep (scheduler / admin endpoints — never the finalize request):
    recover abandoned jobs, then enqueue snapshot jobs that are not yet (or no
    longer) in the queue. Only enqueues; preparation and training run in the
    Celery worker under a lease. Safe to run concurrently and repeatedly.
    """
    now = datetime.now(timezone.utc)
    results = requeue_abandoned_jobs(db, now)
    stale_before = now - timedelta(minutes=settings.TRAINING_DISPATCH_STALE_MINUTES)
    candidate_ids = [
        job_id for (job_id,) in db.query(TrainingJob.job_id)
        .filter(
            TrainingJob.snapshot_id.isnot(None),
            TrainingJob.status == "queued",
            or_(TrainingJob.dispatched_at.is_(None), TrainingJob.dispatched_at < stale_before),
        )
        .order_by(TrainingJob.created_at.asc())
        .limit(limit)
        .all()
    ]
    db.rollback()

    for job_id in candidate_ids:
        job = (
            db.query(TrainingJob).filter(TrainingJob.job_id == job_id)
            .with_for_update(skip_locked=True).populate_existing().first()
        )
        dispatched = _aware(job.dispatched_at) if job else None
        if job is None or job.status != "queued" or (dispatched is not None and dispatched >= stale_before):
            db.rollback()
            continue
        job.dispatch_attempts = (job.dispatch_attempts or 0) + 1
        try:
            job.celery_task_id = _send_to_queue(job_id)
            job.dispatched_at = now
            results.append({"job_id": job_id, "result": "dispatched"})
            logger.info("TRAINING_JOB_DISPATCHED | job_id=%s | dispatch=%s", job_id, job.dispatch_attempts)
        except Exception as exc:
            job.error_message = f"queue dispatch failed (attempt {job.dispatch_attempts}): {exc}"
            results.append({"job_id": job_id, "result": "dispatch_failed", "error": str(exc)})
            logger.error("TRAINING_JOB_DISPATCH_FAILED | job_id=%s | %s", job_id, exc)
        db.commit()
    return results


# ---------------------------------------------------------------------------
# 5. Worker runtime: claim, lease heartbeat, fenced completion
# ---------------------------------------------------------------------------

def new_worker_id() -> str:
    import socket
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def claim_snapshot_job(db: Session, job_id: str, worker_id: str, now: Optional[datetime] = None) -> Optional[int]:
    """
    Atomically take ownership of a snapshot job. Returns the attempt number
    (fencing token) or None. Claimable: 'queued', or 'running' whose lease
    expired more than LEASE_GRACE ago. Enforces the retry limit.
    """
    now = now or datetime.now(timezone.utc)
    job = (
        db.query(TrainingJob).filter(TrainingJob.job_id == job_id)
        .with_for_update(skip_locked=True).populate_existing().first()
    )
    if job is None or job.snapshot_id is None:
        db.rollback()
        return None
    lease = _aware(job.lease_expires_at)
    abandoned = job.status == "running" and lease is not None and lease < _abandoned_before(now)
    if job.status != "queued" and not abandoned:
        db.rollback()
        return None
    if job.attempt_count >= settings.TRAINING_MAX_ATTEMPTS:
        job.status = "failed"
        job.completed_at = now
        job.error_message = f"retry limit {settings.TRAINING_MAX_ATTEMPTS} reached"
        job.worker_id = None
        job.lease_expires_at = None
        db.commit()
        return None
    job.attempt_count += 1
    job.status = "running"
    job.worker_id = worker_id
    job.started_at = job.started_at or now
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=settings.TRAINING_LEASE_SECONDS)
    attempt = job.attempt_count
    db.commit()
    logger.info("TRAINING_JOB_CLAIMED | job_id=%s | worker=%s | attempt=%s", job_id, worker_id, attempt)
    return attempt


def _owned(db: Session, job_id: str, worker_id: str, attempt: int, model=TrainingJob):
    """Lock the row (TrainingJob or another leased model); return it only if this worker attempt owns it."""
    pk = model.__mapper__.primary_key[0]
    job = (
        db.query(model).filter(pk == job_id)
        .with_for_update().populate_existing().first()
    )
    if job is None or job.status != "running" or job.worker_id != worker_id or job.attempt_count != attempt:
        return None
    return job


def renew_lease(session_factory, job_id: str, worker_id: str, attempt: int, model=TrainingJob) -> bool:
    db = session_factory()
    try:
        job = _owned(db, job_id, worker_id, attempt, model)
        if job is None:
            db.rollback()
            return False
        now = datetime.now(timezone.utc)
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=settings.TRAINING_LEASE_SECONDS)
        db.commit()
        return True
    finally:
        db.close()


class LeaseHeartbeat:
    """Background lease renewal for one worker attempt; ``lost`` is set if ownership is gone."""

    def __init__(self, session_factory, job_id: str, worker_id: str, attempt: int, interval: Optional[float] = None,
                 model=TrainingJob):
        import threading
        self._args = (session_factory, job_id, worker_id, attempt, model)
        self._interval = interval if interval is not None else settings.TRAINING_HEARTBEAT_SECONDS
        self._stop = threading.Event()
        self.lost = False
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"lease-{job_id[:8]}")

    def _run(self):
        while not self._stop.wait(self._interval):
            try:
                if not renew_lease(*self._args):
                    self.lost = True
                    logger.error("TRAINING_LEASE_LOST | job_id=%s | attempt=%s", self._args[1], self._args[3])
                    return
            except Exception as exc:  # DB hiccup: keep trying until the lease runs out
                logger.warning("TRAINING_LEASE_RENEW_FAILED | job_id=%s | %s", self._args[1], exc)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)


def _fenced_update(session_factory, job_id: str, owner_id: str, owner_attempt: int, model=TrainingJob, **fields) -> bool:
    """Apply ``fields`` only if (owner_id, owner_attempt) still owns the running row."""
    db = session_factory()
    try:
        job = _owned(db, job_id, owner_id, owner_attempt, model)
        if job is None:
            db.rollback()
            return False
        for k, v in fields.items():
            setattr(job, k, v)
        db.commit()
        return True
    finally:
        db.close()


def _release_or_fail(session_factory, job_id, worker_id, attempt, error: str) -> str:
    """Retryable failure: re-queue unless the retry limit is reached."""
    now = datetime.now(timezone.utc)
    if attempt >= settings.TRAINING_MAX_ATTEMPTS:
        _fenced_update(session_factory, job_id, worker_id, attempt, status="failed", completed_at=now,
                       error_message=f"{error}; retry limit {settings.TRAINING_MAX_ATTEMPTS} reached",
                       worker_id=None, lease_expires_at=None)
        return f"Job {job_id} failed: {error} (retries exhausted)"
    _fenced_update(session_factory, job_id, worker_id, attempt, status="queued", dispatched_at=None,
                   error_message=f"attempt {attempt}: {error}", worker_id=None, lease_expires_at=None)
    return f"Job {job_id} attempt {attempt} failed and was re-queued: {error}"


def run_snapshot_job(job_id: str, *, session_factory, train_fn, worker_id: Optional[str] = None,
                     heartbeat_interval: Optional[float] = None) -> str:
    """
    Execute one snapshot training job inside a Celery worker.

    claim (lease) -> prepare/verify immutable dataset -> train -> store candidate.
    Every state change is fenced on (worker_id, attempt): a worker that lost its
    lease can never overwrite the job or register a model. The result is a
    candidate only (ModelVersion.is_current=False); nothing is activated.
    """
    from app.models.training import ModelVersion

    worker_id = worker_id or new_worker_id()
    db = session_factory()
    try:
        attempt = claim_snapshot_job(db, job_id, worker_id)
    finally:
        db.close()
    if attempt is None:
        return f"Job {job_id} skipped (not claimable: running elsewhere, finished or retry limit reached)"

    with LeaseHeartbeat(session_factory, job_id, worker_id, attempt, heartbeat_interval) as hb:
        db = session_factory()
        try:
            job = db.query(TrainingJob).filter(TrainingJob.job_id == job_id).one()
            try:
                manifest_path = prepare_snapshot_dataset(db, job)
            except DatasetPreparationError as exc:
                _fenced_update(session_factory, job_id, worker_id, attempt, status="failed",
                               dataset_status=DATASET_FAILED, error_message=exc.report(),
                               completed_at=datetime.now(timezone.utc), worker_id=None, lease_expires_at=None)
                return f"Job {job_id} failed: invalid dataset"
            except Exception as exc:
                return _release_or_fail(session_factory, job_id, worker_id, attempt, f"dataset preparation error: {exc}")
            finally:
                db.rollback()
        finally:
            db.close()

        if not _fenced_update(session_factory, job_id, worker_id, attempt,
                              dataset_status=DATASET_PREPARED, dataset_manifest_path=str(manifest_path)):
            return f"Job {job_id} attempt {attempt} lost its lease before training"

        with open(manifest_path, "r", encoding="utf-8") as fh:
            data_yaml = manifest_path.parent / json.load(fh).get("data_yaml", "data.yaml")
        version = f"snap-{job_id[:8]}"
        try:
            best_pt, metrics = train_fn(data_yaml, f"train_{version}_a{attempt}")
        except Exception as exc:
            if hb.lost:
                return f"Job {job_id} attempt {attempt} lost its lease; result discarded"
            return _release_or_fail(session_factory, job_id, worker_id, attempt, f"training crashed: {exc}")
        if hb.lost:
            return f"Job {job_id} attempt {attempt} lost its lease; result discarded"
        if not best_pt or not Path(best_pt).exists():
            return _release_or_fail(session_factory, job_id, worker_id, attempt, "training produced no best.pt")

        candidates = Path(settings.CANDIDATE_MODELS_DIR)
        candidates.mkdir(parents=True, exist_ok=True)
        stem = f"{job_id[:8]}_a{attempt}"
        dest = candidates / f"{stem}_best.pt"
        shutil.copy2(best_pt, dest)
        meta = candidates / f"{stem}_metadata.json"
        with open(meta, "w") as mh:
            json.dump({"job_id": job_id, "attempt": attempt, "worker_id": worker_id,
                       "dataset_manifest": str(manifest_path), "metrics": metrics,
                       "candidate": True, "completed_at": datetime.now(timezone.utc).isoformat()}, mh)

        db = session_factory()
        try:
            job = _owned(db, job_id, worker_id, attempt)
            if job is None:
                db.rollback()
                return f"Job {job_id} attempt {attempt} lost its lease; candidate not registered"
            db.add(ModelVersion(job_id=job_id, version=job.version, is_current=False,
                                map_score=(metrics.get("map50") if isinstance(metrics, dict) else None)))
            job.best_model_path = str(dest)
            job.metadata_path = str(meta)
            job.status = "completed"
            job.error_message = None
            job.completed_at = datetime.now(timezone.utc)
            job.worker_id = None
            job.lease_expires_at = None
            db.commit()
        finally:
            db.close()
    logger.info("SNAPSHOT_JOB_COMPLETED | job_id=%s | attempt=%s | candidate=%s (not activated)", job_id, attempt, dest)
    return f"Job {job_id} completed (candidate model, not activated)"


def job_to_dict(job: TrainingJob) -> dict:
    return {
        "job_id": job.job_id,
        "version": job.version,
        "status": job.status,
        "trigger": job.trigger,
        "snapshot_id": job.snapshot_id,
        "dataset_status": job.dataset_status,
        "dataset_manifest_path": job.dataset_manifest_path,
        "error_message": job.error_message,
        "dispatch_attempts": job.dispatch_attempts,
        "attempt_count": job.attempt_count,
        "worker_id": job.worker_id,
        "lease_expires_at": str(job.lease_expires_at) if job.lease_expires_at else None,
        "dispatched_at": str(job.dispatched_at) if job.dispatched_at else None,
        "created_at": str(job.created_at) if job.created_at else None,
    }
