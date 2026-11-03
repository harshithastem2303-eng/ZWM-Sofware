"""
ZWM v1.1.0 Block A4.1 — deployment reliability & safety hardening.

Same isolation as Block A4: own database (SQLite per test, or the throwaway
PostgreSQL database from ZWM_A1_TEST_DATABASE_URL), synthetic weights under
tmp_path, fake trainers/loaders, ultralytics.YOLO replaced by fakes or a raising stub.
"""
import os
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.config import settings
from app.models.training import ActivationGuardError, ModelDeployment, ModelVersion, TrainingJob
from app.services import model_cache as mc
from app.services import model_deployment_service as mds
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import eval_dirs  # noqa: F401
from test_a4_model_deployment import (  # noqa: F401
    ADMIN, SimulatedCrash, _approve, _current, _dep, _deps, _events, _legacy_current, _new_candidate,
    cand, deploy_env,
)
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user,
)


def _pg(db):
    return db.get_bind().dialect.name == "postgresql"


def _later():
    return mds._now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS + 1)


def _inflight(db, model_id="someone-else"):
    """A live deployment held by another process."""
    dep = ModelDeployment(kind="activation", status="activating", model_id=model_id, weights_sha256="0" * 64,
                          requested_at=mds._now(), lease_token="other",
                          lease_expires_at=mds._now() + timedelta(minutes=10), inflight="global")
    db.add(dep)
    db.commit()
    return dep


# ---------------------------------------------------------------------------
# Task 1 — legacy training goes through the deployment engine
# ---------------------------------------------------------------------------

@pytest.fixture()
def legacy_training(monkeypatch, tmp_path, worker, Session):
    """Legacy (non-snapshot) training paths with fake dataset/trainer, isolated dirs and DB."""
    from app.tasks import training_tasks
    from worker import training_worker

    data_yaml = tmp_path / "legacy_data.yaml"
    data_yaml.write_text("names: [x]\n")
    fake_build = lambda dest: (data_yaml, 1, ["x"])                       # noqa: E731
    monkeypatch.setattr(training_tasks, "build_dataset_from_permanent", fake_build)
    monkeypatch.setattr(training_worker, "build_dataset_from_permanent", fake_build)

    def fake_train(data_yaml, run_name, **kw):
        best = tmp_path / f"legacy_best_{run_name}.pt"
        best.write_bytes(f"LEGACY-{run_name}".encode())
        return best, {"map50": 0.3}

    monkeypatch.setattr(training_worker, "run_ultralytics_training", fake_train)
    monkeypatch.setattr(training_tasks, "run_ultralytics_training", fake_train)
    monkeypatch.setattr(training_worker, "SessionLocal", Session)
    monkeypatch.setattr(training_worker, "MODELS_DIR", tmp_path / "legacy_models")
    monkeypatch.setattr(training_worker, "DATASETS_ROOT", tmp_path / "worker_datasets")
    monkeypatch.setattr(training_worker, "RUNS_ROOT", tmp_path / "runs")

    def queue(db, version="v1"):
        job = TrainingJob(version=version, status="queued")
        db.add(job)
        db.commit()
        return job.job_id

    return queue


def _model_of(db, job_id):
    db.expire_all()
    return db.query(ModelVersion).filter(ModelVersion.job_id == job_id).one()


class TestLegacyTrainingActivation:
    def test_celery_legacy_job_activates_through_engine(self, db, legacy_training, worker, deploy_env):
        job_id = legacy_training(db)
        result = worker(job_id)
        assert "completed successfully (activation: activated)" in result
        mv = _model_of(db, job_id)
        assert _current(db) == [mv.model_id]
        dep = _dep(db, mv.model_id, "legacy_activation")
        assert dep.status == "active" and dep.requested_by == mds.LEGACY_TRAINING_ACTOR
        assert deploy_env.serving.read_bytes().startswith(b"LEGACY-")
        assert (Path(settings.DEPLOYED_MODELS_DIR) / dep.previous_artifact_file).read_bytes() == b"ACTIVE-MODEL"
        assert {"activation_requested", "activation_succeeded"} <= set(_events(db, model_id=mv.model_id))

    def test_polling_worker_activates_through_engine(self, db, legacy_training, deploy_env):
        from worker import training_worker
        job_id = legacy_training(db)
        assert training_worker.process_job_once() is True
        mv = _model_of(db, job_id)
        assert _current(db) == [mv.model_id]
        assert _dep(db, mv.model_id, "legacy_activation").status == "active"

    @pytest.mark.parametrize("path", ["celery", "polling"])
    def test_legacy_training_cannot_race_an_inflight_deployment(self, db, legacy_training, worker, deploy_env,
                                                                tmp_path, path):
        from worker import training_worker
        old = _legacy_current(db, tmp_path)
        running = _inflight(db)
        job_id = legacy_training(db)
        if path == "celery":
            assert "not activated" in worker(job_id)
        else:
            training_worker.process_job_once()
        mv = _model_of(db, job_id)
        db.expire_all()
        job = db.query(TrainingJob).filter(TrainingJob.job_id == job_id).one()
        assert job.status == "completed" and mv.is_current is False          # registered, not activated
        assert _current(db) == [old.model_id] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert [d.deployment_id for d in _deps(db)] == [running.deployment_id]
        assert "activation_failed" in _events(db, model_id=mv.model_id)

    def test_auto_activation_can_be_disabled(self, db, legacy_training, worker, deploy_env, monkeypatch):
        monkeypatch.setattr(settings, "LEGACY_AUTO_ACTIVATE_TRAINED_MODELS", False)
        job_id = legacy_training(db)
        assert "automatic activation disabled" in worker(job_id)
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert _events(db, model_id=_model_of(db, job_id).model_id) == ["activation_skipped"]

    def test_failed_legacy_activation_preserves_previous_model(self, db, legacy_training, worker, deploy_env,
                                                               tmp_path, monkeypatch):
        old = _legacy_current(db, tmp_path)
        real = mds.replace_with_retry

        def serving_locked(src, dst, *a, **k):
            if Path(dst) == Path(settings.YOLO_MODEL_PATH):
                raise PermissionError(13, "The process cannot access the file")
            return real(src, dst, *a, **k)

        monkeypatch.setattr(mds, "replace_with_retry", serving_locked)
        job_id = legacy_training(db)
        assert "not activated" in worker(job_id)
        assert _current(db) == [old.model_id] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert _deps(db)[0].status == "failed"


# ---------------------------------------------------------------------------
# Task 2 — approval boundary and single current model enforced by the database
# ---------------------------------------------------------------------------

class TestDatabaseGuards:
    def test_bulk_orm_update_cannot_mark_a_model_current(self, db, cand):
        mv, _ = cand
        with pytest.raises(ActivationGuardError):
            db.query(ModelVersion).filter(ModelVersion.model_id == mv.model_id).update({"is_current": True})
        db.rollback()
        assert _current(db) == []

    def test_raw_sql_cannot_activate_snapshot_candidate(self, db, cand):
        if not _pg(db):
            pytest.skip("the activation trigger is PostgreSQL-only (SQLite relies on the ORM guards)")
        mv, _ = cand
        with pytest.raises(DBAPIError, match="approval workflow"):
            db.execute(text("UPDATE model_versions SET is_current = true WHERE model_id = :m"), {"m": mv.model_id})
        db.rollback()
        with pytest.raises(DBAPIError, match="approval workflow"):
            db.execute(text("INSERT INTO model_versions (model_id, job_id, version, is_current) "
                            "VALUES ('raw-x', :j, 'raw', true)"), {"j": mv.job_id})
        db.rollback()
        assert _current(db) == []

    def test_database_rejects_a_second_current_model(self, db, tmp_path):
        first = _legacy_current(db, tmp_path)
        job = TrainingJob(version="v2", status="completed")
        db.add(job)
        db.commit()
        db.add(ModelVersion(job_id=job.job_id, version="v2", is_current=False))
        db.commit()
        with mds.allow_current_change(db):                                   # even past every application guard
            with pytest.raises(IntegrityError):
                db.query(ModelVersion).update({"is_current": True}, synchronize_session=False)
                db.flush()
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE model_versions SET is_current = true"))
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO model_versions (model_id, job_id, version, is_current) "
                            "VALUES ('raw-2', :j, 'v3', true)"), {"j": job.job_id})
        db.rollback()
        assert _current(db) == [first.model_id]

    def test_engine_switch_satisfies_the_constraint(self, db, Session, cand, tmp_path):
        legacy = _legacy_current(db, tmp_path)
        mv, _ = cand
        _approve(db, Session, mv)
        mds.activate_model_version(db, mv.model_id, ADMIN)
        assert _current(db) == [mv.model_id]
        assert mds.rollback(db, ADMIN, "back")["result"] == "rolled_back"
        assert _current(db) == [legacy.model_id]


# ---------------------------------------------------------------------------
# Task 3 — automatic recovery (scheduler), live leases, idempotency
# ---------------------------------------------------------------------------

def _crash_after_switch(db, Session, mv, deploy_env):
    _approve(db, Session, mv)

    def crash(data):
        raise SimulatedCrash()

    deploy_env.warm_hook = crash
    with pytest.raises(SimulatedCrash):
        mds.activate_model_version(db, mv.model_id, ADMIN)
    deploy_env.warm_hook = None
    db.rollback()


class TestAutomaticRecovery:
    def test_scheduler_job_recovers_expired_deployment(self, db, Session, cand, deploy_env, monkeypatch):
        from app.services import cleanup_worker
        mv, data = cand
        monkeypatch.setattr(settings, "DEPLOYMENT_LEASE_SECONDS", 1)
        _crash_after_switch(db, Session, mv, deploy_env)
        assert deploy_env.serving.read_bytes() == data and _deps(db)[0].status == "activating"
        monkeypatch.setattr(cleanup_worker, "SessionLocal", Session)
        time.sleep(1.3)                                                      # lease expires (live leases: next test)
        cleanup_worker._deployment_recovery_job()
        [dep] = _deps(db)
        assert dep.status == "failed" and dep.inflight is None
        assert deploy_env.serving.read_bytes() == b"ACTIVE-MODEL" and _current(db) == []
        assert "deployment_recovered" in _events(db, deployment_id=dep.deployment_id)
        cleanup_worker._deployment_recovery_job()                            # idempotent
        assert _events(db, deployment_id=dep.deployment_id).count("deployment_recovered") == 1

    def test_live_deployment_is_not_recovered(self, db, Session, cand, deploy_env, monkeypatch):
        mv, data = cand
        _approve(db, Session, mv)
        monkeypatch.setattr(settings, "DEPLOYMENT_LEASE_SECONDS", 1)
        monkeypatch.setattr(settings, "DEPLOYMENT_HEARTBEAT_SECONDS", 0.2)
        seen = []

        def slow_readiness(serving_bytes):
            time.sleep(1.6)                                                  # longer than the lease
            s = Session()
            try:
                seen.append(mds.run_deployment_maintenance(s)["recovered"])
            finally:
                s.close()

        deploy_env.warm_hook = slow_readiness
        assert mds.activate_model_version(db, mv.model_id, ADMIN)["result"] == "activated"
        assert seen == [[]]                                                  # heartbeat kept the lease alive
        assert _current(db) == [mv.model_id] and deploy_env.serving.read_bytes() == data

    def test_concurrent_recoverers_act_once(self, db, Session, cand, deploy_env):
        mv, _ = cand
        _crash_after_switch(db, Session, mv, deploy_env)
        barrier, out = threading.Barrier(3), []

        def go():
            s = Session()
            try:
                barrier.wait()
                out.extend(mds.recover_interrupted_deployments(s, now=_later()))
            except Exception as exc:                                         # sqlite: busy writer
                out.append({"error": type(exc).__name__})
            finally:
                s.close()

        threads = [threading.Thread(target=go) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert len([o for o in out if "outcome" in o]) == 1
        [dep] = _deps(db)
        assert dep.status == "failed" and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert mds.recover_interrupted_deployments(db, now=_later()) == []

    def test_lease_lost_deployment_never_touches_serving_file(self, db, Session, cand, deploy_env, monkeypatch):
        mv, data = cand
        _approve(db, Session, mv)

        def stolen(serving_bytes):
            s = Session()
            try:                                                             # recovery took the deployment over
                dep = s.query(ModelDeployment).one()
                dep.lease_token = "recovery"
                s.commit()
            finally:
                s.close()

        deploy_env.warm_hook = stolen
        with pytest.raises(mds.DeploymentFailed, match="recovery"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert deploy_env.serving.read_bytes() == data                       # left for recovery to reconcile
        assert _current(db) == []


# ---------------------------------------------------------------------------
# Task 4 — Windows replacement, ONNX single-flight export, cache invalidation
# ---------------------------------------------------------------------------

class TestFileReplacement:
    def test_transient_sharing_violation_is_retried(self, tmp_path, monkeypatch):
        src, dst = tmp_path / "a", tmp_path / "b"
        src.write_bytes(b"new")
        dst.write_bytes(b"old")
        real, calls = os.replace, []

        def flaky(a, b):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(32, "being used by another process")
            return real(a, b)

        with monkeypatch.context() as m:
            m.setattr(mc.os, "replace", flaky)
            mc.replace_with_retry(src, dst, attempts=5, delay=0.01)
        assert dst.read_bytes() == b"new" and len(calls) == 3

    def test_persistent_lock_on_serving_file_fails_safely(self, db, Session, cand, deploy_env, monkeypatch):
        mv, _ = cand
        _approve(db, Session, mv)
        real = mds.replace_with_retry

        def serving_locked(src, dst, *a, **k):
            if Path(dst) == Path(settings.YOLO_MODEL_PATH):
                raise PermissionError(13, "The process cannot access the file")
            return real(src, dst, *a, **k)

        monkeypatch.setattr(mds, "replace_with_retry", serving_locked)
        with pytest.raises(mds.DeploymentFailed, match="preserved"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert deploy_env.serving.read_bytes() == b"ACTIVE-MODEL" and _current(db) == []
        assert _deps(db)[0].status == "failed"
        assert not list(deploy_env.serving.parent.glob(".*.tmp"))            # no temp files left behind


class FakeYOLO:
    """Stand-in for ultralytics.YOLO: records loads; export writes a .onnx next to the weights."""
    loads, exports = [], []
    export_delay, export_fails = 0.0, False

    def __init__(self, path, task=None):
        FakeYOLO.loads.append(str(path))
        self.path, self.names = Path(path), {0: "Cat A"}

    def export(self, format, imgsz, dynamic):
        FakeYOLO.exports.append(str(self.path))
        out = self.path.with_suffix(".onnx")
        with open(out, "wb") as fh:
            fh.write(b"ONNX-PART")
            fh.flush()
            time.sleep(FakeYOLO.export_delay)
            if FakeYOLO.export_fails:
                raise RuntimeError("export crashed half-way")
            fh.write(b"-COMPLETE")

    def __call__(self, *a, **k):
        raise AssertionError("no inference in tests")


@pytest.fixture()
def fake_yolo(monkeypatch, deploy_env):
    import ultralytics
    FakeYOLO.loads, FakeYOLO.exports = [], []
    FakeYOLO.export_delay, FakeYOLO.export_fails = 0.0, False
    monkeypatch.setattr(ultralytics, "YOLO", FakeYOLO)
    monkeypatch.setattr(mc.YOLOModelCache, "_validate_onnx_outputs", lambda self, a, b: True)
    monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check", None)
    cache = mc.YOLOModelCache()
    cache.reload()
    yield cache
    cache.reload()


def _cache_dir():
    return Path(settings.YOLO_MODEL_PATH).resolve().parent / ".model_cache"


class TestOnnxExport:
    def _local(self, tmp_path):
        pt = tmp_path / "weights.pt"
        pt.write_bytes(b"SYNTHETIC-PT")
        sha = mc.file_sha256(pt)
        return mc.YOLOModelCache()._load_copy(str(pt), sha), sha

    def test_concurrent_exports_run_once_and_publish_complete_file(self, fake_yolo, tmp_path):
        local, sha = self._local(tmp_path)
        FakeYOLO.export_delay = 0.5
        barrier, out = threading.Barrier(3), []

        def go():
            barrier.wait()
            out.append(fake_yolo._ensure_onnx(local, sha))

        threads = [threading.Thread(target=go) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert len(FakeYOLO.exports) == 1
        assert len(set(out)) == 1 and out[0] == local.with_suffix(".onnx")
        assert out[0].read_bytes() == b"ONNX-PART-COMPLETE"
        assert not list(_cache_dir().glob(".export-*")) and not list(_cache_dir().glob("*.lock"))

    def test_interrupted_export_publishes_nothing(self, fake_yolo, tmp_path):
        local, sha = self._local(tmp_path)
        FakeYOLO.export_fails = True
        assert fake_yolo._ensure_onnx(local, sha) is None
        assert not local.with_suffix(".onnx").exists()
        assert not list(_cache_dir().glob(".export-*")) and not list(_cache_dir().glob("*.lock"))
        FakeYOLO.export_fails = False
        assert fake_yolo._ensure_onnx(local, sha).read_bytes() == b"ONNX-PART-COMPLETE"

    def test_abandoned_export_lock_is_taken_over(self, fake_yolo, tmp_path, monkeypatch):
        local, sha = self._local(tmp_path)
        lock = local.with_suffix(".onnx").with_name(local.with_suffix(".onnx").name + ".lock")
        lock.write_text("dead-pid")
        old = time.time() - settings.ONNX_EXPORT_LOCK_STALE_SECONDS - 10
        os.utime(lock, (old, old))
        assert fake_yolo._ensure_onnx(local, sha) is not None and len(FakeYOLO.exports) == 1

    def test_live_export_lock_makes_others_fall_back_to_pytorch(self, fake_yolo, tmp_path, monkeypatch):
        local, sha = self._local(tmp_path)
        lock = local.with_suffix(".onnx").with_name(local.with_suffix(".onnx").name + ".lock")
        lock.write_text("live-pid")
        monkeypatch.setattr(settings, "ONNX_EXPORT_WAIT_SECONDS", 0.5)
        assert fake_yolo._ensure_onnx(local, sha) is None and FakeYOLO.exports == []
        lock.unlink()


class TestModelCache:
    def test_cache_loads_immutable_copy_and_reloads_on_switch(self, fake_yolo, deploy_env, monkeypatch):
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")
        first = fake_yolo.get_model()
        assert fake_yolo.get_model() is first and len(FakeYOLO.loads) == 1   # cached
        sha1 = mc.file_sha256(deploy_env.serving)
        assert FakeYOLO.loads[0] == str(_cache_dir() / f"{sha1}.pt")         # never the serving path itself
        tmp = deploy_env.serving.with_name("next.tmp")
        tmp.write_bytes(b"NEXT-MODEL")
        os.replace(tmp, deploy_env.serving)                                  # what another process's switch does
        second = fake_yolo.get_model()
        assert second is not first and len(FakeYOLO.loads) == 2
        assert fake_yolo.loaded_sha256 == mc.file_sha256(deploy_env.serving)

    def test_onnx_backend_uses_published_export(self, fake_yolo, deploy_env, monkeypatch):
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "onnx")
        fake_yolo.get_model()
        sha = mc.file_sha256(deploy_env.serving)
        assert FakeYOLO.loads[-1] == str(_cache_dir() / f"{sha}.onnx")

    def test_hook_registered_like_the_app_does(self, fake_yolo, deploy_env, monkeypatch, Session):
        """Regression: the hook must be callable when registered through set_integrity_check (app.main)."""
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")
        mc.YOLOModelCache.set_integrity_check(mds.serving_expectation(Session))      # unmanaged -> None
        assert fake_yolo.get_model() is not None and len(FakeYOLO.loads) == 1
        mc.YOLOModelCache.set_integrity_check(lambda: "0" * 64)
        fake_yolo.reload()
        with pytest.raises(mc.ModelIntegrityError):
            fake_yolo.get_model()

    def test_app_registers_a_callable_hook(self, deploy_env):
        import app.main  # noqa: F401  (registers the hook at import)
        assert callable(mc.YOLOModelCache()._integrity_check)

    def test_integrity_mismatch_fails_closed(self, fake_yolo, deploy_env, monkeypatch):
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")
        expected = mc.file_sha256(deploy_env.serving)
        monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check", staticmethod(lambda: expected))
        good = fake_yolo.get_model()
        deploy_env.serving.write_bytes(b"UNEXPECTED")
        assert fake_yolo.get_model() is good                                 # keeps serving the verified model
        fake_yolo.reload()
        with pytest.raises(mc.ModelIntegrityError):
            fake_yolo.get_model()
        assert fake_yolo.get_model(expected_sha=mc.file_sha256(deploy_env.serving)) is not None


# ---------------------------------------------------------------------------
# Task 5 — consistency report, reconciliation, fail-closed activation
# ---------------------------------------------------------------------------

class TestConsistency:
    def test_serving_drift_is_detected_and_reconciled(self, db, Session, user, tmp_path, three_cats, worker,
                                                      deploy_env, api):
        v1, d1 = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        assert mds.deployment_consistency(db)["state"] == "consistent"
        deploy_env.serving.write_bytes(b"DRIFTED")                           # e.g. a manual copy
        report = api.get("/api/ml/deployments").json()["consistency"]
        assert report["state"] == "inconsistent" and str(tmp_path) not in str(report)
        v2, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        with pytest.raises(mds.PreconditionFailed, match="inconsistent"):    # fail closed
            mds.activate_model_version(db, v2.model_id, ADMIN)
        result = api.post("/api/ml/deployments/recover").json()
        assert "restored" in result["consistency"]["action"]
        assert deploy_env.serving.read_bytes() == d1 and _current(db) == [v1.model_id]
        assert mds.deployment_consistency(db)["state"] == "consistent"
        assert _dep(db, v1.model_id, "reconcile").status == "reconciled"
        assert "serving_reconciled" in _events(db)
        assert mds.activate_model_version(db, v2.model_id, ADMIN)["result"] == "activated"

    def test_unrepairable_state_is_alerted_once_and_left_alone(self, db, Session, cand, deploy_env):
        mv, data = cand
        _approve(db, Session, mv)
        mds.activate_model_version(db, mv.model_id, ADMIN)
        dep = _dep(db, mv.model_id)
        (Path(settings.DEPLOYED_MODELS_DIR) / dep.artifact_file).unlink()
        deploy_env.serving.write_bytes(b"DRIFTED")
        for _ in range(2):
            assert mds.run_deployment_maintenance(db)["consistency"]["action"] == "alerted"
        assert _events(db).count("consistency_alert") == 1
        assert deploy_env.serving.read_bytes() == b"DRIFTED"                 # nothing guessed
        assert _deps(db, kind="reconcile") == []

    def test_mid_deployment_expectation_is_the_previous_model(self, db, Session, cand, deploy_env, tmp_path):
        legacy = _legacy_current(db, tmp_path)
        mv, data = cand
        _approve(db, Session, mv)
        seen = []

        def during(serving_bytes):
            s = Session()
            try:
                seen.append((mds._expected_sha(s), mds.deployment_consistency(s)["state"]))
            finally:
                s.close()

        deploy_env.warm_hook = during
        mds.activate_model_version(db, mv.model_id, ADMIN)
        assert seen == [(mc.file_sha256(Path(db.query(TrainingJob).filter(
            TrainingJob.job_id == legacy.job_id).one().best_model_path)), "in_progress")]
        assert mds._expected_sha(db) == _dep(db, mv.model_id).weights_sha256


# ---------------------------------------------------------------------------
# Final verification additions: fail-closed integrity, ONNX tamper, rollback
# recovery, end-to-end API workflow
# ---------------------------------------------------------------------------

class TestFailClosedIntegrity:
    def test_database_outage_never_loads_an_unverified_file(self, fake_yolo, deploy_env, monkeypatch):
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")

        def broken_factory():
            raise OSError("connection refused")

        monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check",
                            staticmethod(mds.serving_expectation(broken_factory)))
        with pytest.raises(mc.ModelIntegrityError, match="cannot verify"):
            fake_yolo.get_model()
        assert FakeYOLO.loads == []

    def test_database_outage_keeps_serving_the_verified_model(self, fake_yolo, deploy_env, monkeypatch):
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")
        good = fake_yolo.get_model()                                         # verified while the DB was fine

        def broken_factory():
            raise OSError("connection refused")

        monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check",
                            staticmethod(mds.serving_expectation(broken_factory)))
        deploy_env.serving.write_bytes(b"SWAPPED-DURING-OUTAGE")
        assert fake_yolo.get_model() is good                                 # no new, unverified load
        assert len(FakeYOLO.loads) == 1

    def test_inconsistent_state_fails_closed(self, db, Session, cand, deploy_env, fake_yolo, monkeypatch):
        mv, data = cand
        _approve(db, Session, mv)
        mds.activate_model_version(db, mv.model_id, ADMIN)
        assert mds._expected_sha(db) == _dep(db, mv.model_id).weights_sha256
        with mds.allow_current_change(db):                                   # out-of-band change of the DB state
            db.query(ModelVersion).update({"is_current": False}, synchronize_session=False)
            db.commit()
        with pytest.raises(mc.IntegrityStateUnknown):
            mds._expected_sha(db)
        monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")
        monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check", staticmethod(mds.serving_expectation(Session)))
        fake_yolo.reload()
        with pytest.raises(mc.ModelIntegrityError):
            fake_yolo.get_model()
        assert FakeYOLO.loads == []
        assert mds.deployment_consistency(db)["state"] == "inconsistent"
        assert mds.run_deployment_maintenance(db)["consistency"]["action"] == "alerted"
        with pytest.raises(mds.PreconditionFailed, match="inconsistent"):
            mds.activate_model_version(db, mv.model_id, ADMIN)

    def test_image_validation_degrades_safely_when_integrity_fails(self, fake_yolo, deploy_env, monkeypatch):
        from app.services.image_validator import validate_ai_category_match
        monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check", staticmethod(lambda: "0" * 64))
        result = validate_ai_category_match(str(deploy_env.serving), "plastic")
        assert result["validation_result"] == "MODEL_CLASS_NOT_SUPPORTED"
        assert result["status"] == "pending_admin_review" and FakeYOLO.loads == []

    def test_tampered_onnx_export_is_redone(self, fake_yolo, tmp_path):
        pt = tmp_path / "weights.pt"
        pt.write_bytes(b"SYNTHETIC-PT")
        sha = mc.file_sha256(pt)
        local = fake_yolo._load_copy(str(pt), sha)
        onnx = fake_yolo._ensure_onnx(local, sha)
        onnx.write_bytes(b"TAMPERED")                                        # bit rot / partial overwrite
        again = fake_yolo._ensure_onnx(local, sha)
        assert again == onnx and onnx.read_bytes() == b"ONNX-PART-COMPLETE" and len(FakeYOLO.exports) == 2


class TestInterruptedRollbackRecovery:
    def test_crash_during_rollback_restores_the_model_that_was_active(self, db, Session, user, tmp_path, three_cats,
                                                                    worker, deploy_env):
        v1, d1 = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        v2, d2 = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        mds.activate_model_version(db, v2.model_id, ADMIN)

        def crash(data):
            raise SimulatedCrash()

        deploy_env.warm_hook = crash
        with pytest.raises(SimulatedCrash):
            mds.rollback(db, ADMIN, "regression")
        deploy_env.warm_hook = None
        db.rollback()
        rb = _dep(db, v1.model_id, "rollback")
        assert rb.status == "activating" and deploy_env.serving.read_bytes() == d1      # switched, not committed
        [res] = mds.recover_interrupted_deployments(db, now=_later())
        assert "previous model restored" in res["outcome"]
        assert deploy_env.serving.read_bytes() == d2 and _current(db) == [v2.model_id]
        assert _dep(db, v1.model_id, "rollback").status == "failed"
        assert "rollback_failed" in _events(db, deployment_id=rb.deployment_id)
        assert mds.deployment_consistency(db)["state"] == "consistent"
        assert mds.rollback(db, ADMIN, "retry")["result"] == "rolled_back"
        assert _current(db) == [v1.model_id] and deploy_env.serving.read_bytes() == d1


class TestEndToEndApiWorkflow:
    def test_candidate_to_rollback_through_the_api(self, db, Session, user, tmp_path, three_cats, worker,
                                                   deploy_env, api):
        from test_a3_candidate_evaluation import POLICY, _run
        assert api.put("/api/ml/evaluation-policy", json=POLICY).status_code == 200
        ids = {}
        for tag in ("V1", "V2"):
            mv, data = _new_candidate(db, user, tmp_path, three_cats, worker, tag)
            r = api.post(f"/api/ml/candidates/{mv.model_id}/evaluations")
            assert r.status_code == 202
            eid = r.json()["evaluation"]["evaluation_id"]
            _run(Session, eid)
            assert api.get(f"/api/ml/evaluations/{eid}").json()["gate_decision"] == "eligible_for_review"
            ids[tag] = (mv.model_id, eid, data)

        (m1, e1, d1), (m2, e2, d2) = ids["V1"], ids["V2"]
        pending = {c["model_id"] for c in api.get("/api/ml/approvals/pending").json()["candidates"]}
        assert pending == {m1, m2}
        for model, ev in ((m1, e1), (m2, e2)):
            first = api.post(f"/api/ml/candidates/{model}/approve", json={"evaluation_id": ev})
            again = api.post(f"/api/ml/candidates/{model}/approve", json={"evaluation_id": ev})
            assert (first.json()["created"], again.json()["created"]) == (True, False)   # duplicate-safe
        r = api.post(f"/api/ml/models/{m1}/activate", json={"reason": "first release"})
        assert r.status_code == 200 and r.json()["result"] == "activated"
        assert api.post(f"/api/ml/models/{m1}/activate").json()["result"] == "already_active"
        assert api.post(f"/api/ml/models/{m2}/activate").json()["result"] == "activated"
        assert deploy_env.serving.read_bytes() == d2
        assert api.get("/api/ml/models/current").json()["model_id"] == m2

        overview = api.get("/api/ml/deployments").json()
        assert overview["consistency"]["state"] == "consistent"
        assert overview["active_model"]["model_id"] == m2 and overview["rollback_target"]["model_id"] == m1
        assert {h["model_id"] for h in overview["history"]} == {m1, m2}

        r = api.post("/api/ml/deployments/rollback", json={"reason": "glass regression"})
        assert r.status_code == 200 and r.json()["result"] == "rolled_back"
        assert api.get("/api/ml/models/current").json()["model_id"] == m1 and deploy_env.serving.read_bytes() == d1
        rollbacks = api.get("/api/ml/deployments?kind=rollback").json()["history"]
        assert len(rollbacks) == 1 and rollbacks[0]["status"] == "active"
        types = {e["event_type"] for e in api.get("/api/ml/deployments/events").json()["events"]}
        assert {"approval_granted", "activation_succeeded", "rollback_requested", "rollback_succeeded"} <= types
        assert api.get("/api/ml/deployments").json()["consistency"]["state"] == "consistent"
