"""
ZWM v1.1.0 Block A2.1 — training pipeline reliability and recovery.

Covers: finalize returns without preparing/dispatching; lease ownership with
heartbeat; recovery of abandoned running jobs only after lease expiry + grace;
bounded retries; fencing of stale workers; concurrent dispatch/preparation;
fail-closed protection against real YOLO training.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.config import settings
from app.models.training import ModelVersion, TrainingJob
from app.services import training_pipeline_service as tps
from conftest import RealTrainingBlocked
from test_a2_training_pipeline import _jobs, no_real_training, worker  # noqa: F401
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user,
    _complete_many, _set_threshold, _uploaded_image,
)
# Imported BEFORE any test patching: the original, unwrapped training function.
from worker.training_worker import run_ultralytics_training as direct_run_ultralytics_training


def _expire_lease(db, job_id, beyond_grace=True):
    job = db.query(TrainingJob).filter(TrainingJob.job_id == job_id).one()
    extra = settings.TRAINING_LEASE_GRACE_SECONDS + 1 if beyond_grace else 0
    job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=extra + 1)
    db.commit()


@pytest.fixture()
def snapshot_job(db, user, tmp_path, three_cats):
    a, _, _ = three_cats
    _set_threshold(db, 5)
    _complete_many(db, user, [(a, 5)], tmp_path)
    [job] = _jobs(db)
    return job.job_id


def _job(db, job_id):
    db.expire_all()
    return db.query(TrainingJob).filter(TrainingJob.job_id == job_id).one()


# ---------------------------------------------------------------------------
# 1. Finalization request does not prepare or dispatch
# ---------------------------------------------------------------------------

class TestFinalizeBoundary:
    def test_http_finalize_commits_job_and_returns(self, db, user, tmp_path, three_cats, api, queued, monkeypatch):
        a, _, _ = three_cats
        _set_threshold(db, 1)

        def forbidden(*args, **kwargs):
            raise AssertionError("dataset preparation / dispatch must not run inside the finalize request")

        monkeypatch.setattr(tps, "prepare_snapshot_dataset", forbidden)
        monkeypatch.setattr(tps, "dispatch_pending_training_jobs", forbidden)
        monkeypatch.setattr(tps, "_send_to_queue", forbidden)

        img = _uploaded_image(db, user, a, tmp_path)
        assert api.post("/api/annotations/", json={
            "image_id": img.image_id, "annotation_type": "rectangle",
            "label_data": {"points": [{"x": 10, "y": 20}, {"x": 110, "y": 120}]},
            "category_id": a.category_id, "image_width": 200, "image_height": 200,
        }).status_code == 201
        r = api.post(f"/api/annotations/image/{img.image_id}/finalize")
        assert r.status_code == 200 and r.json()["snapshots_created"] == [1]

        [job] = _jobs(db)
        assert job.status == "queued" and job.dispatched_at is None and job.dataset_status == "pending"
        assert queued == [] and not Path(settings.TRAINING_DATASETS_DIR).exists()


# ---------------------------------------------------------------------------
# 2. Leases, recovery, retries, fencing
# ---------------------------------------------------------------------------

class TestLeaseRecovery:
    def test_abandoned_job_is_recovered_after_lease_expiry(self, db, Session, snapshot_job, queued, worker):
        s = Session()
        assert tps.claim_snapshot_job(s, snapshot_job, "worker-A") == 1      # A claims ... and dies
        s.close()
        tps.dispatch_pending_training_jobs(db)
        assert _job(db, snapshot_job).status == "running"                    # live lease: untouched

        _expire_lease(db, snapshot_job)
        tps.dispatch_pending_training_jobs(db)                               # sweep: requeue + enqueue
        job = _job(db, snapshot_job)
        assert job.status == "queued" and "abandoned by worker-A" in job.error_message
        assert queued == [snapshot_job]

        assert "completed" in worker(snapshot_job)                           # worker B
        job = _job(db, snapshot_job)
        assert job.status == "completed" and job.attempt_count == 2 and len(worker.calls) == 1

        # The original worker can never write again (fenced on worker_id + attempt).
        assert tps._fenced_update(Session, snapshot_job, "worker-A", 1, status="failed") is False
        assert _job(db, snapshot_job).status == "completed"
        assert db.query(ModelVersion).filter(ModelVersion.job_id == snapshot_job).count() == 1

    def test_live_lease_is_never_taken_over(self, db, Session, snapshot_job, worker):
        s = Session()
        tps.claim_snapshot_job(s, snapshot_job, "worker-A")
        s.close()
        assert "skipped" in worker(snapshot_job)                             # redelivered message
        _expire_lease(db, snapshot_job, beyond_grace=False)                  # expired, within grace
        tps.dispatch_pending_training_jobs(db)
        assert "skipped" in worker(snapshot_job)
        job = _job(db, snapshot_job)
        assert job.status == "running" and job.worker_id == "worker-A" and worker.calls == []

    def test_heartbeat_renews_lease_and_detects_takeover(self, db, Session, snapshot_job):
        s = Session()
        tps.claim_snapshot_job(s, snapshot_job, "worker-A")
        s.close()
        _expire_lease(db, snapshot_job, beyond_grace=False)
        with tps.LeaseHeartbeat(Session, snapshot_job, "worker-A", 1, interval=0.1) as hb:
            time.sleep(0.5)
            job = _job(db, snapshot_job)
            lease = job.lease_expires_at if job.lease_expires_at.tzinfo else job.lease_expires_at.replace(tzinfo=timezone.utc)
            assert lease > datetime.now(timezone.utc) and not hb.lost
            job.worker_id = "worker-B"                                       # ownership moved
            db.commit()
            time.sleep(0.5)
            assert hb.lost is True

    def test_retry_limit_for_training_crashes(self, db, Session, snapshot_job, monkeypatch, tmp_path):
        from app.tasks import training_tasks
        calls = []

        def crash(data_yaml, run_name, **kw):
            calls.append(run_name)
            raise RuntimeError("CUDA out of memory")

        monkeypatch.setattr(training_tasks, "run_ultralytics_training", crash)
        monkeypatch.setattr(training_tasks, "SessionLocal", Session)
        for attempt in (1, 2):
            assert "re-queued" in training_tasks.train_model(snapshot_job)
            job = _job(db, snapshot_job)
            assert job.status == "queued" and f"attempt {attempt}" in job.error_message
        assert "retries exhausted" in training_tasks.train_model(snapshot_job)
        job = _job(db, snapshot_job)
        assert job.status == "failed" and job.attempt_count == settings.TRAINING_MAX_ATTEMPTS
        assert "skipped" in training_tasks.train_model(snapshot_job)
        assert len(calls) == settings.TRAINING_MAX_ATTEMPTS

    def test_abandoned_job_at_retry_limit_fails(self, db, Session, snapshot_job):
        job = _job(db, snapshot_job)
        job.status, job.worker_id = "running", "worker-Z"
        job.attempt_count = settings.TRAINING_MAX_ATTEMPTS
        db.commit()
        _expire_lease(db, snapshot_job)
        results = tps.dispatch_pending_training_jobs(db)
        assert {"job_id": snapshot_job, "result": "failed_retries_exhausted"} in results
        assert _job(db, snapshot_job).status == "failed"

    def test_worker_that_loses_lease_mid_training_cannot_register(self, db, Session, snapshot_job, monkeypatch, tmp_path):
        from app.tasks import training_tasks

        def train_then_get_preempted(data_yaml, run_name, **kw):
            s = Session()
            j = s.query(TrainingJob).filter(TrainingJob.job_id == snapshot_job).one()
            j.worker_id, j.attempt_count = "worker-B", j.attempt_count + 1   # another attempt took over
            s.commit()
            s.close()
            best = tmp_path / "late.pt"
            best.write_bytes(b"LATE")
            return best, {}

        monkeypatch.setattr(training_tasks, "run_ultralytics_training", train_then_get_preempted)
        monkeypatch.setattr(training_tasks, "SessionLocal", Session)
        result = training_tasks.train_model(snapshot_job)
        assert "lost its lease" in result
        job = _job(db, snapshot_job)
        assert job.status == "running" and job.worker_id == "worker-B"
        assert db.query(ModelVersion).count() == 0

    def test_concurrent_deliveries_execute_once(self, db, Session, snapshot_job, worker):
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("row locking (FOR UPDATE SKIP LOCKED) requires PostgreSQL")
        barrier = threading.Barrier(3)
        results, errors = [], []

        def deliver():
            try:
                barrier.wait()
                results.append(worker(snapshot_job))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=deliver) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert sum("completed" in r for r in results) == 1
        assert sum("skipped" in r for r in results) == 2
        assert len(worker.calls) == 1
        assert db.query(ModelVersion).filter(ModelVersion.job_id == snapshot_job).count() == 1


# ---------------------------------------------------------------------------
# 3. Dataset preparation under concurrency
# ---------------------------------------------------------------------------

class TestConcurrentPreparation:
    def test_parallel_preparation_publishes_one_verified_dataset(self, db, Session, snapshot_job):
        barrier = threading.Barrier(4)
        paths, errors = [], []

        def prepare():
            s = Session()
            try:
                job = s.query(TrainingJob).filter(TrainingJob.job_id == snapshot_job).one()
                barrier.wait()
                paths.append(tps.prepare_snapshot_dataset(s, job))
            except Exception as exc:
                errors.append(exc)
            finally:
                s.close()

        threads = [threading.Thread(target=prepare) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == [] and len(set(paths)) == 1
        root = paths[0].parent
        job = _job(db, snapshot_job)
        from app.models.training import TrainingSnapshot, TrainingSnapshotImage
        snap = db.query(TrainingSnapshot).one()
        members = db.query(TrainingSnapshotImage).order_by(TrainingSnapshotImage.position).all()
        assert tps.verify_prepared_dataset(root, snap, members, job.job_id) == []
        assert [p.name for p in root.parent.iterdir() if ".tmp-" in p.name] == []

    def test_intact_dataset_is_reused_and_corrupt_one_quarantined(self, db, snapshot_job):
        job = _job(db, snapshot_job)
        manifest = tps.prepare_snapshot_dataset(db, job)
        mtime = os.path.getmtime(manifest)
        assert tps.prepare_snapshot_dataset(db, job) == manifest and os.path.getmtime(manifest) == mtime

        victim = next((manifest.parent / "labels" / "train").iterdir())
        victim.write_text("0 0.1 0.1 0.1 0.1\n")                          # tamper with a copy
        rebuilt = tps.prepare_snapshot_dataset(db, job)
        quarantined = [p for p in manifest.parent.parent.iterdir() if ".corrupt-" in p.name]
        assert rebuilt == manifest and len(quarantined) == 1               # set aside, never deleted
        assert (quarantined[0] / "labels" / "train" / victim.name).read_text() == "0 0.1 0.1 0.1 0.1\n"
        assert victim.read_text() != "0 0.1 0.1 0.1 0.1\n"


# ---------------------------------------------------------------------------
# 4. Fail-closed protection against real YOLO training
# ---------------------------------------------------------------------------

class TestFailClosedTrainingGuard:
    def test_directly_imported_training_function_is_blocked(self, tmp_path):
        with pytest.raises(RealTrainingBlocked):
            direct_run_ultralytics_training(tmp_path / "data.yaml", "guard-check")

    def test_ultralytics_train_and_downloads_are_blocked(self):
        from ultralytics import YOLO
        from ultralytics.utils.downloads import attempt_download_asset
        with pytest.raises(RealTrainingBlocked):
            YOLO.train(object(), data="x.yaml")
        with pytest.raises(RealTrainingBlocked):
            attempt_download_asset("definitely_missing_weights_zwm.pt")
