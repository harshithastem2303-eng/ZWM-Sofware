"""
ZWM v1.1.0 Block A2 — automatic training trigger + immutable 80/10/10 dataset preparation.

Contract (as of A2.1):
  finalize  -> snapshot + durable job committed (nothing else in the request)
  sweep     -> dispatch_pending_training_jobs(): enqueue only
  worker    -> train_model -> run_snapshot_job(): lease, prepare/verify dataset, train, candidate

Isolation: same as test_training_foundation (own engine; files under tmp_path).
Celery delivery is stubbed; YOLO training is faked through the task module and
blocked at the ultralytics level by conftest (fail-closed).
"""
import hashlib
import json
import os
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from app.config import settings
from app.models.image import Image
from app.models.setting import SystemSetting
from app.models.training import (
    ModelVersion,
    SnapshotImmutableError,
    TrainingJob,
    TrainingSnapshotImage,
)
from app.services import training_dataset_service as tds
from app.services import training_pipeline_service as tps
from test_training_foundation import (  # noqa: F401  (fixtures)
    Session, api, db, engine, queued, three_cats, user,
    _complete_image, _complete_many, _set_threshold, _snapshot_ids, _snapshots,
)


@pytest.fixture(autouse=True)
def no_real_training(monkeypatch, tmp_path):
    """Project wrappers fail loudly too; the deployed model path is a tmp file we can check."""
    from app.tasks import training_tasks
    from worker import training_worker

    def boom(*a, **k):
        raise AssertionError("real YOLO training must never run in Block A2 tests")

    monkeypatch.setattr(training_tasks, "run_ultralytics_training", boom)
    monkeypatch.setattr(training_worker, "run_ultralytics_training", boom)
    active = tmp_path / "active_model" / "best.pt"
    active.parent.mkdir()
    active.write_bytes(b"ACTIVE-MODEL")
    monkeypatch.setattr(settings, "YOLO_MODEL_PATH", str(active))
    monkeypatch.setattr(training_tasks, "MODELS_DIR", tmp_path / "legacy_models")
    (tmp_path / "legacy_models").mkdir()
    return active


@pytest.fixture()
def worker(monkeypatch, Session, tmp_path):
    """Run the real Celery task body synchronously with a fake trainer."""
    from app.tasks import training_tasks
    calls = []

    def fake_train(data_yaml, run_name, **kw):
        calls.append(Path(data_yaml))
        best = tmp_path / f"fake_best_{len(calls)}.pt"
        best.write_bytes(b"FAKE-WEIGHTS")
        return best, {"map50": 0.42}

    monkeypatch.setattr(training_tasks, "run_ultralytics_training", fake_train)
    monkeypatch.setattr(training_tasks, "SessionLocal", Session)

    def run(job_id):
        return training_tasks.train_model(job_id)

    run.calls = calls
    return run


def _jobs(db):
    db.expire_all()
    return db.query(TrainingJob).order_by(TrainingJob.created_at).all()


def _set_toggle(db, enabled):
    s = db.query(SystemSetting).filter(SystemSetting.id == 1).one()
    s.auto_train_toggle = enabled
    db.commit()


def _manifest(path):
    with open(path) as fh:
        return json.load(fh)


def _members(db, snapshot):
    db.expire_all()
    return (
        db.query(TrainingSnapshotImage)
        .filter(TrainingSnapshotImage.snapshot_id == snapshot.snapshot_id)
        .order_by(TrainingSnapshotImage.position)
        .all()
    )


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Trigger: exactly one durable job per locked snapshot
# ---------------------------------------------------------------------------

class TestAutomaticTrigger:
    def test_no_snapshot_no_job(self, db, user, tmp_path, three_cats, queued):
        a, b, c = three_cats
        _complete_many(db, user, [(a, 50), (b, 30), (c, 19)], tmp_path)
        assert _snapshots(db) == []
        tps.dispatch_pending_training_jobs(db)
        assert _jobs(db) == [] and queued == []

    def test_v1_creates_exactly_one_job_then_sweep_queues_it(self, db, user, tmp_path, three_cats, queued):
        a, b, c = three_cats
        _complete_many(db, user, [(a, 50), (b, 30), (c, 20)], tmp_path)
        v1 = _snapshots(db)[0]
        [job] = _jobs(db)
        assert (job.snapshot_id, job.trigger, job.status) == (v1.snapshot_id, "auto", "queued")
        assert job.dispatched_at is None and job.dataset_status == "pending" and queued == []

        tps.dispatch_pending_training_jobs(db)
        [job] = _jobs(db)
        assert job.dispatched_at is not None and job.dispatch_attempts == 1
        assert queued == [job.job_id]

    def test_repeated_reconcile_and_dispatch_never_duplicate(self, db, user, tmp_path, three_cats, queued, api):
        a, _, _ = three_cats
        _complete_many(db, user, [(a, 100)], tmp_path)
        for _ in range(3):
            tds.reconcile_training_snapshots(db)
            tps.dispatch_pending_training_jobs(db)
            assert api.post("/api/dataset/snapshots/reconcile").status_code == 200
            assert api.post("/api/ml/training/dispatch").status_code == 200
        assert len(_jobs(db)) == 1 and len(queued) == 1

    def test_concurrent_snapshot_creation_one_job(self, db, Session, user, tmp_path, three_cats, monkeypatch):
        a, _, _ = three_cats
        real = tds.create_next_snapshot_if_ready
        monkeypatch.setattr(tds, "create_next_snapshot_if_ready", lambda db: None)
        _complete_many(db, user, [(a, 110)], tmp_path)
        monkeypatch.setattr(tds, "create_next_snapshot_if_ready", real)

        barrier = threading.Barrier(4)
        errors = []

        def run():
            s = Session()
            try:
                barrier.wait()
                real(s)
            except Exception as exc:
                errors.append(exc)
            finally:
                s.close()

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert len(_snapshots(db)) == 1 and len(_jobs(db)) == 1

    def test_toggle_off_creates_no_job(self, db, user, tmp_path, three_cats, queued):
        a, _, _ = three_cats
        _set_toggle(db, False)
        _complete_many(db, user, [(a, 100)], tmp_path)
        tps.dispatch_pending_training_jobs(db)
        assert len(_snapshots(db)) == 1
        assert _jobs(db) == [] and queued == []

    def test_enabling_toggle_only_affects_future_snapshots(self, db, user, tmp_path, three_cats, queued, api):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _set_toggle(db, False)
        _complete_many(db, user, [(a, 5)], tmp_path)
        _set_toggle(db, True)
        tds.reconcile_training_snapshots(db)
        tps.dispatch_pending_training_jobs(db)
        assert _jobs(db) == []                                    # V1 is not trained silently

        _complete_many(db, user, [(a, 5)], tmp_path)              # V2 locked while enabled
        v1, v2 = _snapshots(db)
        assert [j.snapshot_id for j in _jobs(db)] == [v2.snapshot_id]

        r = api.post(f"/api/ml/snapshots/{v1.snapshot_id}/train")  # explicit admin action
        assert r.status_code == 201 and r.json()["job"]["trigger"] == "admin_snapshot"
        assert api.post(f"/api/ml/snapshots/{v1.snapshot_id}/train").status_code == 409
        assert api.post(f"/api/ml/snapshots/{v2.snapshot_id}/train").status_code == 409
        assert sorted(j.snapshot_id for j in _jobs(db)) == sorted([v1.snapshot_id, v2.snapshot_id])

    def test_threshold_change_affects_future_milestones_only(self, db, user, tmp_path, three_cats):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)
        _set_threshold(db, 10)
        _complete_many(db, user, [(a, 9)], tmp_path)
        assert len(_snapshots(db)) == 1 and len(_jobs(db)) == 1
        _complete_many(db, user, [(a, 1)], tmp_path)
        assert [s.dataset_size for s in _snapshots(db)] == [5, 15]
        assert len(_jobs(db)) == 2


class TestDurableDispatch:
    def test_failed_delivery_is_retried_without_duplicates(self, db, user, tmp_path, three_cats, monkeypatch):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)

        def broker_down(job_id):
            raise ConnectionError("redis unavailable")

        monkeypatch.setattr(tps, "_send_to_queue", broker_down)
        tps.dispatch_pending_training_jobs(db)
        [job] = _jobs(db)
        assert job.status == "queued" and job.dispatched_at is None
        assert job.dispatch_attempts == 1 and "redis unavailable" in job.error_message

        sent = []
        monkeypatch.setattr(tps, "_send_to_queue", lambda job_id: sent.append(job_id) or "task-ok")
        tps.dispatch_pending_training_jobs(db)
        tps.dispatch_pending_training_jobs(db)
        [job] = _jobs(db)
        assert sent == [job.job_id]
        assert job.dispatched_at is not None and job.dispatch_attempts == 2

    def test_crash_between_commit_and_queue_is_recovered_by_sweep(self, db, user, tmp_path, three_cats, queued, monkeypatch):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)              # committed, never queued
        [job] = _jobs(db)
        assert job.dispatched_at is None and queued == []

        from app.services.cleanup_worker import _training_dispatch_job
        bind = db.get_bind()
        monkeypatch.setattr("app.services.cleanup_worker.SessionLocal", lambda: db.__class__(bind=bind))
        _training_dispatch_job()                                   # periodic sweep
        [job] = _jobs(db)
        assert queued == [job.job_id] and job.dispatched_at is not None

    def test_stale_dispatch_resent_but_executed_once(self, db, user, tmp_path, three_cats, queued, worker):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)
        tps.dispatch_pending_training_jobs(db)
        [job] = _jobs(db)
        job.dispatched_at = datetime.now(timezone.utc) - timedelta(hours=2)  # message lost
        db.commit()
        tps.dispatch_pending_training_jobs(db)
        assert queued == [job.job_id, job.job_id]                  # re-delivered

        worker(job.job_id)
        second = worker(job.job_id)                                # duplicate delivery / restart
        assert "skipped" in second and len(worker.calls) == 1


# ---------------------------------------------------------------------------
# Dataset: 80/10/10, leakage-free, frozen class map, validated, immutable
# ---------------------------------------------------------------------------

class TestSnapshotDataset:
    def test_100_and_200_split_counts_and_inheritance(self, db, user, tmp_path, three_cats, worker):
        a, b, c = three_cats
        _complete_many(db, user, [(a, 50), (b, 30), (c, 20)], tmp_path)
        _complete_many(db, user, [(a, 40), (b, 40), (c, 20)], tmp_path)
        v1, v2 = _snapshots(db)
        m1, m2 = _members(db, v1), _members(db, v2)

        assert Counter(m.split_type for m in m1) == {"train": 80, "val": 10, "test": 10}
        assert Counter(m.split_type for m in m2) == {"train": 160, "val": 20, "test": 20}
        v1_split = {m.image_id: m.split_type for m in m1}
        assert all(m.split_type == v1_split[m.image_id] for m in m2 if m.image_id in v1_split)

        for job in _jobs(db):
            assert "completed" in worker(job.job_id)
        j1, j2 = _jobs(db)
        for job, members, counts in ((j1, m1, (80, 10, 10)), (j2, m2, (160, 20, 20))):
            man = _manifest(job.dataset_manifest_path)
            assert man["split_counts"] == dict(zip(("train", "val", "test"), counts))
            by_split = {s: {e["image_id"] for e in man["images"] if e["split"] == s} for s in tps.SPLITS}
            assert not (by_split["train"] & by_split["val"]) and not (by_split["train"] & by_split["test"])
            assert not (by_split["val"] & by_split["test"])
            assert set().union(*by_split.values()) == {m.image_id for m in members}  # only snapshot images
            root = Path(job.dataset_manifest_path).parent
            for s in tps.SPLITS:
                assert {p.stem for p in (root / "images" / s).iterdir()} == by_split[s]
                assert {p.stem for p in (root / "labels" / s).iterdir()} == by_split[s]

    def test_stratified_by_class(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        imgs = _complete_many(db, user, [(a, 50), (b, 30), (c, 20)], tmp_path)
        cat_of = {i.image_id: i.selected_category_id for i in imgs}
        members = _members(db, _snapshots(db)[0])
        val = Counter(cat_of[m.image_id] for m in members if m.split_type == "val")
        test = Counter(cat_of[m.image_id] for m in members if m.split_type == "test")
        expected = {a.category_id: 5, b.category_id: 3, c.category_id: 2}
        assert val == expected and test == expected

    def test_split_assignment_is_deterministic(self):
        items = [(f"img-{i:03d}", i % 3) for i in range(100)]
        first = tps.assign_splits(100, {}, items)
        assert first == tps.assign_splits(100, {}, list(reversed(items)))
        added = tps.assign_splits(200, dict(first), [(f"new-{i:03d}", i % 3) for i in range(100)])
        assert Counter(added.values()) == {"train": 80, "val": 10, "test": 10}
        assert tps.split_targets(5) == {"train": 3, "val": 1, "test": 1}
        assert tps.split_targets(2) == {"train": 2, "val": 0, "test": 0}

    def test_data_yaml_uses_frozen_class_map(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        _set_threshold(db, 6)
        _complete_many(db, user, [(a, 2), (b, 2), (c, 2)], tmp_path)
        manifest_path = tps.prepare_snapshot_dataset(db, _jobs(db)[0])
        data = yaml.safe_load((manifest_path.parent / "data.yaml").read_text())
        assert data["nc"] == 3
        assert data["names"] == ["Cat A", "Cat B", "Cat C"]               # index order, not codes
        assert (data["train"], data["val"], data["test"]) == ("images/train", "images/val", "images/test")
        ids = {int(l.split()[0]) for p in (manifest_path.parent / "labels").rglob("*.txt")
               for l in p.read_text().splitlines() if l}
        assert ids == {0, 1, 2}
        assert _manifest(manifest_path)["class_map"] == _snapshots(db)[0].class_map

    def test_missing_image_file_fails_job(self, db, user, tmp_path, three_cats, worker):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        imgs = _complete_many(db, user, [(a, 5)], tmp_path)
        os.remove(imgs[1].permanent_s3_path)
        result = worker(_jobs(db)[0].job_id)
        [job] = _jobs(db)
        assert "invalid dataset" in result and worker.calls == []
        assert job.status == "failed" and job.dataset_status == "failed"
        assert "source image file missing" in job.error_message and imgs[1].image_id in job.error_message
        assert not list(Path(settings.TRAINING_DATASETS_DIR).glob("snapshot_v1_*"))  # nothing half-built

    @pytest.mark.parametrize("bad", ["0 1.5 0.5 0.2 0.2\n", "7 0.5 0.5 0.2 0.2\n", "0 0.5 0.5\n", ""])
    def test_invalid_label_fails_job(self, db, user, tmp_path, three_cats, worker, bad):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        imgs = _complete_many(db, user, [(a, 5)], tmp_path)
        Path(imgs[3].yolo_txt_path).write_text(bad)
        worker(_jobs(db)[0].job_id)
        [job] = _jobs(db)
        assert job.status == "failed" and imgs[3].image_id in job.error_message
        assert worker.calls == []

    def test_sources_unchanged_and_membership_immutable(self, db, user, tmp_path, three_cats):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        imgs = _complete_many(db, user, [(a, 5)], tmp_path)
        before = {i.image_id: (_sha(i.permanent_s3_path), _sha(i.yolo_txt_path)) for i in imgs}
        v1 = _snapshots(db)[0]
        ids_before = _snapshot_ids(db, v1)
        manifest_path = tps.prepare_snapshot_dataset(db, _jobs(db)[0])

        db.expire_all()
        for i in db.query(Image).filter(Image.image_id.in_(before)).all():
            assert (_sha(i.permanent_s3_path), _sha(i.yolo_txt_path)) == before[i.image_id]
        assert _snapshot_ids(db, _snapshots(db)[0]) == ids_before
        man = _manifest(manifest_path)
        assert {e["image_id"]: (e["image_sha256"], e["label_sha256"]) for e in man["images"]} == before

        member = _members(db, v1)[0]
        member.split_type = "test" if member.split_type != "test" else "train"
        with pytest.raises(SnapshotImmutableError):
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# Worker behaviour: candidate only, legacy manual path preserved
# ---------------------------------------------------------------------------

class TestTrainingExecutionSafety:
    def test_snapshot_job_trains_on_prepared_dataset_and_never_activates(
        self, db, user, tmp_path, three_cats, monkeypatch, worker, no_real_training
    ):
        from app.tasks import training_tasks
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)
        monkeypatch.setattr(training_tasks, "build_dataset_from_permanent",
                            lambda *a: pytest.fail("snapshot jobs must not scan upload folders"))
        [job] = _jobs(db)
        result = worker(job.job_id)
        assert "candidate" in result

        [job] = _jobs(db)
        assert worker.calls == [Path(job.dataset_manifest_path).parent / "data.yaml"]
        assert job.status == "completed" and job.dataset_status == "prepared"
        assert Path(job.best_model_path).parent == Path(settings.CANDIDATE_MODELS_DIR)
        mv = db.query(ModelVersion).filter(ModelVersion.job_id == job.job_id).one()
        assert mv.is_current is False
        assert no_real_training.read_bytes() == b"ACTIVE-MODEL"           # deployed model untouched

    def test_legacy_manual_training_path_preserved(self, db, Session, user, tmp_path, three_cats, monkeypatch):
        from app.services.training_service import trigger_training_job
        from app.tasks import training_tasks
        from worker import training_worker

        manual = trigger_training_job(db, version="v1", class_counts={})
        assert manual.snapshot_id is None and manual.trigger == "manual"
        called = []
        monkeypatch.setattr(training_tasks, "build_dataset_from_permanent",
                            lambda d: called.append(d) or (_ for _ in ()).throw(RuntimeError("no data")))
        monkeypatch.setattr(training_tasks, "SessionLocal", Session)
        monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
        result = training_tasks.train_model(manual.job_id)
        assert called and "dataset preparation" in result               # legacy branch used

        # Legacy polling worker never claims snapshot jobs
        a, _, _ = three_cats
        _set_threshold(db, 5)
        _complete_many(db, user, [(a, 5)], tmp_path)
        assert [j for j in _jobs(db) if j.snapshot_id is not None][0].status == "queued"
        s = Session()
        try:
            assert training_worker.claim_queued_job(s) is None
        finally:
            s.close()
