"""
ZWM v1.1.0 Block A4 — controlled approval, activation and rollback.

Candidates come from the real A1-A3 pipeline (fake trainer, fake evaluator) on an
isolated database. Every model artifact is a small synthetic file under tmp_path;
the serving path (YOLO_MODEL_PATH) and DEPLOYED_MODELS_DIR are tmp paths too.
Model loading is replaced by fakes and ultralytics.YOLO itself is made to raise,
so no real load, validation, inference or download can happen.
"""
import json
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.models.training import (
    ActivationGuardError,
    DeploymentEvent,
    DeploymentRecordImmutableError,
    ModelApproval,
    ModelDeployment,
    ModelEvaluation,
    ModelVersion,
    TrainingJob,
)
from app.services import model_deployment_service as mds
from app.services import model_evaluation_service as mes
from test_a2_training_pipeline import _jobs, no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import (  # noqa: F401
    GOOD, NAMES, POLICY, _evaluator, _make_candidate, _request, _run, eval_dirs,
)
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user, _set_threshold,
)

ADMIN = "admin-0001"


class SimulatedCrash(BaseException):
    """Escapes ``except Exception`` like a killed process would."""


@pytest.fixture(autouse=True)
def deploy_env(monkeypatch, tmp_path, no_real_training):
    """Isolated deployment dir, fake model loader/readiness, and a fail-closed ultralytics.YOLO."""
    import ultralytics

    class _NoRealYOLO:
        def __init__(self, *a, **k):
            raise AssertionError("ultralytics.YOLO must never be constructed in Block A4 tests")

    monkeypatch.setattr(ultralytics, "YOLO", _NoRealYOLO)
    monkeypatch.setattr(settings, "DEPLOYED_MODELS_DIR", str(tmp_path / "deployed"))

    class Env:
        serving = no_real_training
        inspected = []
        warmed = []
        warm_hook = None
        names = dict(NAMES)

    env = Env()
    env.inspected, env.warmed = [], []

    def fake_inspect(path):
        env.inspected.append(Path(path))
        return env.names

    def fake_warm(expected_sha=None):
        data = Path(settings.YOLO_MODEL_PATH).read_bytes()
        env.warmed.append(data)
        if env.warm_hook:
            env.warm_hook(data)

    monkeypatch.setattr(mds, "_default_inspect", fake_inspect)
    monkeypatch.setattr(mds, "_default_warm", fake_warm)
    return env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_weights(db, mv, tag: str) -> bytes:
    """Give each candidate distinct synthetic bytes (before it is evaluated)."""
    job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one()
    data = f"SYNTHETIC-WEIGHTS-{tag}".encode()
    Path(job.best_model_path).write_bytes(data)
    return data


def _new_candidate(db, user, tmp_path, three_cats, worker, tag):
    if not _jobs(db):
        _set_threshold(db, 30)
    mv = _make_candidate(db, user, tmp_path, three_cats, worker)
    return mv, _unique_weights(db, mv, tag)


def _evaluate(db, Session, mv, evaluate=None, policy=POLICY):
    mes.update_policy(db, policy, None)
    ev, _ = mes.request_evaluation(db, mv.model_id)
    _run(Session, ev.evaluation_id, evaluate)
    db.expire_all()
    return db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == ev.evaluation_id).one()


def _approve(db, Session, mv, actor=ADMIN):
    ev = _evaluate(db, Session, mv)
    approval, created = mds.approve_candidate(db, mv.model_id, ev.evaluation_id, actor, "looks good")
    assert created
    return approval


def _current(db):
    db.expire_all()
    return [m.model_id for m in db.query(ModelVersion).filter(ModelVersion.is_current.is_(True)).all()]


def _deps(db, **filters):
    db.expire_all()
    q = db.query(ModelDeployment)
    for k, v in filters.items():
        q = q.filter(getattr(ModelDeployment, k) == v)
    return q.order_by(ModelDeployment.requested_at).all()


def _dep(db, model_id, kind="activation"):
    [d] = _deps(db, model_id=model_id, kind=kind)
    return d


def _events(db, **filters):
    db.expire_all()
    q = db.query(DeploymentEvent)
    for k, v in filters.items():
        q = q.filter(getattr(DeploymentEvent, k) == v)
    return [e.event_type for e in q.order_by(DeploymentEvent.created_at).all()]


def _legacy_current(db, tmp_path, data=b"ACTIVE-MODEL"):
    """A pre-A4 legacy model marked current, whose bytes are what is being served."""
    weights = tmp_path / "legacy_v1.pt"
    weights.write_bytes(data)
    job = TrainingJob(version="v1", status="completed", best_model_path=str(weights))
    db.add(job)
    db.commit()
    mv = ModelVersion(job_id=job.job_id, version="v1", is_current=True)
    db.add(mv)
    db.commit()
    return mv


@pytest.fixture()
def cand(db, user, tmp_path, three_cats, worker):
    return _new_candidate(db, user, tmp_path, three_cats, worker, "A")


# ---------------------------------------------------------------------------
# 1. Approval lifecycle
# ---------------------------------------------------------------------------

class TestApproval:
    def test_eligible_candidate_can_be_approved_with_full_evidence(self, db, Session, cand):
        mv, data = cand
        ev = _evaluate(db, Session, mv)
        assert mds.candidate_status(db, mv)["lifecycle"] == "awaiting_review"
        ap, created = mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN, "ok")
        job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one()
        assert created and ap.decision == "approved" and ap.decided_by == ADMIN and ap.decided_at
        assert (ap.model_id, ap.model_version, ap.job_id, ap.snapshot_id, ap.evaluation_id) == (
            mv.model_id, mv.version, job.job_id, job.snapshot_id, ev.evaluation_id)
        assert ap.evaluation_config_hash == ev.config_hash and ap.gate_decision == "eligible_for_review"
        assert ap.weights_sha256 == ev.weights_sha256 and ap.class_map_sha256 and ap.manifest_sha256
        assert mds.candidate_status(db, mv)["lifecycle"] == "approved"
        assert _current(db) == []                                          # approval never activates
        again, created2 = mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)
        assert not created2 and again.approval_id == ap.approval_id         # idempotent
        assert db.query(ModelApproval).count() == 1
        assert _events(db, model_id=mv.model_id) == ["approval_granted"]

    @pytest.mark.parametrize("result,decision", [
        ({**GOOD, "map50": 0.1}, "rejected"),
        ({**GOOD, "map50": None, "precision": None, "recall": None}, "insufficient_evidence"),
    ])
    def test_failed_or_incomplete_evaluation_cannot_be_approved(self, db, Session, cand, result, decision):
        mv, _ = cand
        ev = _evaluate(db, Session, mv, _evaluator(result))
        assert ev.gate_decision == decision
        with pytest.raises(mds.ReviewError, match="not eligible"):
            mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)
        assert db.query(ModelApproval).count() == 0
        assert "approval_refused" in _events(db, model_id=mv.model_id)

    def test_insufficient_evidence_and_errors_cannot_be_approved(self, db, Session, cand):
        mv, _ = cand
        ev = _evaluate(db, Session, mv, policy={**POLICY, "min_test_images": 100})
        assert ev.gate_decision == "insufficient_evidence"
        with pytest.raises(mds.ReviewError):
            mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)

        def broken(*a, **k):
            raise RuntimeError("evaluator crashed")

        ev2 = _evaluate(db, Session, mv, broken, policy=POLICY)
        assert ev2.status == "error"
        with pytest.raises(mds.ReviewError):
            mds.approve_candidate(db, mv.model_id, ev2.evaluation_id, ADMIN)

    def test_unconfigured_policy_and_pending_evaluation_cannot_be_approved(self, db, Session, cand):
        mv, _ = cand
        ev, _ = mes.request_evaluation(db, mv.model_id)                     # still pending
        with pytest.raises(mds.ReviewError, match="not eligible"):
            mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)
        _run(Session, ev.evaluation_id)
        db.expire_all()
        assert db.query(ModelEvaluation).one().gate_decision == "policy_not_configured"
        with pytest.raises(mds.ReviewError):
            mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)

    def test_weights_changed_after_evaluation_cannot_be_approved(self, db, Session, cand):
        mv, _ = cand
        ev = _evaluate(db, Session, mv)
        Path(db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one().best_model_path).write_bytes(b"X")
        with pytest.raises(mds.ReviewError, match="weights changed"):
            mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)

    def test_rejection_is_recorded_and_keeps_weights_and_evaluation(self, db, Session, cand):
        mv, data = cand
        ev = _evaluate(db, Session, mv)
        with pytest.raises(mds.ReviewError):
            mds.reject_candidate(db, mv.model_id, ev.evaluation_id, ADMIN, "  ")
        rej, created = mds.reject_candidate(db, mv.model_id, ev.evaluation_id, ADMIN, "false positives on glass")
        assert created and rej.decision == "rejected" and rej.reason == "false positives on glass"
        job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one()
        assert Path(job.best_model_path).read_bytes() == data
        assert db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == ev.evaluation_id).one().metrics
        assert mds.candidate_status(db, mv)["lifecycle"] == "rejected"
        assert mds.reject_candidate(db, mv.model_id, ev.evaluation_id, ADMIN, "again")[1] is False

    def test_contradictory_decisions_fail_clearly(self, db, Session, cand):
        mv, _ = cand
        ev = _evaluate(db, Session, mv)
        mds.approve_candidate(db, mv.model_id, ev.evaluation_id, ADMIN)
        with pytest.raises(mds.ReviewError, match="already approved"):
            mds.reject_candidate(db, mv.model_id, ev.evaluation_id, ADMIN, "changed my mind")
        assert [a.decision for a in db.query(ModelApproval).all()] == ["approved"]

    def test_decision_history_is_immutable(self, db, Session, cand):
        mv, _ = cand
        ap = _approve(db, Session, mv)
        ap.reason = "tampered"
        with pytest.raises(DeploymentRecordImmutableError):
            db.commit()
        db.rollback()
        db.delete(db.query(ModelApproval).one())
        with pytest.raises(DeploymentRecordImmutableError):
            db.commit()
        db.rollback()
        event = db.query(DeploymentEvent).first()
        event.event_type = "x"
        with pytest.raises(DeploymentRecordImmutableError):
            db.commit()
        db.rollback()

    def test_concurrent_approve_and_reject_record_one_decision(self, db, Session, cand):
        mv, _ = cand
        ev = _evaluate(db, Session, mv)
        barrier = threading.Barrier(2)
        out = []

        def go(action):
            s = Session()
            try:
                barrier.wait()
                if action == "approve":
                    out.append(("ok", mds.approve_candidate(s, mv.model_id, ev.evaluation_id, ADMIN)[0].decision))
                else:
                    out.append(("ok", mds.reject_candidate(s, mv.model_id, ev.evaluation_id, ADMIN, "no way")[0].decision))
            except mds.ReviewError as exc:
                out.append(("refused", str(exc)))
            except Exception as exc:                                          # sqlite write lock
                out.append(("refused", type(exc).__name__))
            finally:
                s.close()

        threads = [threading.Thread(target=go, args=(a,)) for a in ("approve", "reject")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        db.expire_all()
        decisions = db.query(ModelApproval).all()
        assert len(decisions) == 1
        assert sum(1 for kind, _ in out if kind == "ok") >= 1
        assert all(v == decisions[0].decision for kind, v in out if kind == "ok")


# ---------------------------------------------------------------------------
# 2. Activation boundary
# ---------------------------------------------------------------------------

class TestActivationPreconditions:
    def test_candidate_without_approval_cannot_activate(self, db, Session, cand, deploy_env):
        mv, _ = cand
        _evaluate(db, Session, mv)
        with pytest.raises(mds.PreconditionFailed, match="not been approved"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert _deps(db) == []
        assert sorted(_events(db, model_id=mv.model_id)) == ["activation_failed", "activation_requested"]

    def test_rejected_candidate_cannot_activate(self, db, Session, cand, deploy_env):
        mv, _ = cand
        ev = _evaluate(db, Session, mv)
        mds.reject_candidate(db, mv.model_id, ev.evaluation_id, ADMIN, "bad on metal")
        with pytest.raises(mds.PreconditionFailed, match="rejected"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"

    def test_modified_weights_cannot_activate_and_invalidate_approval(self, db, Session, cand, deploy_env):
        mv, _ = cand
        _approve(db, Session, mv)
        job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one()
        Path(job.best_model_path).write_bytes(b"TAMPERED")
        with pytest.raises(mds.PreconditionFailed, match="SHA-256"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert "approval_invalidated" in _events(db, model_id=mv.model_id)
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert mds.candidate_status(db, mv, deep=True)["deployable"] is False

    def test_missing_weights_cannot_activate(self, db, Session, cand, deploy_env):
        mv, _ = cand
        _approve(db, Session, mv)
        job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one()
        Path(job.best_model_path).unlink()
        with pytest.raises(mds.PreconditionFailed, match="missing"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"

    def test_newer_evaluation_requires_re_review(self, db, Session, cand):
        mv, _ = cand
        _approve(db, Session, mv)
        _evaluate(db, Session, mv, policy={**POLICY, "min_map50": 0.6})     # new config -> new evaluation
        with pytest.raises(mds.PreconditionFailed, match="re-reviewed"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert "approval_invalidated" in _events(db, model_id=mv.model_id)

    def test_changed_snapshot_manifest_blocks_activation(self, db, Session, cand):
        mv, _ = cand
        _approve(db, Session, mv)
        job = db.query(TrainingJob).filter(TrainingJob.job_id == mv.job_id).one()
        with open(job.dataset_manifest_path, "a", encoding="utf-8") as fh:
            fh.write(" ")
        with pytest.raises(mds.PreconditionFailed, match="manifest"):
            mds.activate_model_version(db, mv.model_id, ADMIN)

    def test_incompatible_class_mapping_is_refused_before_switch(self, db, Session, cand, deploy_env):
        mv, _ = cand
        _approve(db, Session, mv)
        deploy_env.names = {0: "Cat A", 1: "Cat C", 2: "Cat B"}
        with pytest.raises(mds.DeploymentFailed, match="class mapping"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        assert deploy_env.serving.read_bytes() == b"ACTIVE-MODEL" and deploy_env.warmed == []
        assert _deps(db)[0].status == "failed" and _current(db) == []


class TestActivation:
    def test_approved_candidate_activates_through_workflow(self, db, Session, cand, deploy_env, api):
        mv, data = cand
        ap = _approve(db, Session, mv)
        r = api.post(f"/api/ml/models/{mv.model_id}/activate", json={"reason": "weekly release"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"] == "activated" and body["deployment"]["status"] == "active"
        assert _current(db) == [mv.model_id]
        assert deploy_env.serving.read_bytes() == data                       # serving switched
        assert deploy_env.warmed == [data]                                   # readiness on serving path
        staged = Path(settings.DEPLOYED_MODELS_DIR) / body["deployment"]["artifact"]
        assert deploy_env.inspected == [staged] and staged.read_bytes() == data
        [dep] = _deps(db)
        assert (dep.kind, dep.approval_id, dep.weights_sha256) == ("activation", ap.approval_id, ap.weights_sha256)
        assert dep.previous_sha256 and (Path(settings.DEPLOYED_MODELS_DIR) / dep.previous_artifact_file).read_bytes() == b"ACTIVE-MODEL"
        assert dep.inflight is None and dep.lease_token is None and dep.reason == "weekly release"
        assert mds.candidate_status(db, mv)["lifecycle"] == "active"

    def test_previous_model_stays_active_until_switch_commits(self, db, Session, cand, deploy_env, tmp_path):
        legacy = _legacy_current(db, tmp_path)
        mv, data = cand
        _approve(db, Session, mv)
        seen = []

        def during_readiness(serving_bytes):
            s = Session()
            try:
                seen.append([m.model_id for m in s.query(ModelVersion).filter(ModelVersion.is_current.is_(True))])
                seen.append(s.query(ModelDeployment).one().status)
            finally:
                s.close()

        deploy_env.warm_hook = during_readiness
        mds.activate_model_version(db, mv.model_id, ADMIN)
        assert seen == [[legacy.model_id], "activating"]
        assert _current(db) == [mv.model_id]

    def test_repeated_activation_is_idempotent(self, db, Session, cand, deploy_env):
        mv, data = cand
        _approve(db, Session, mv)
        first = mds.activate_model_version(db, mv.model_id, ADMIN)
        second = mds.activate_model_version(db, mv.model_id, ADMIN)
        assert first["result"] == "activated" and second["result"] == "already_active"
        assert second["deployment"]["deployment_id"] == first["deployment"]["deployment_id"]
        assert len(_deps(db)) == 1 and len(deploy_env.warmed) == 1
        assert deploy_env.serving.read_bytes() == data

    def test_new_activation_supersedes_previous_deployment(self, db, Session, user, tmp_path, three_cats, worker,
                                                           deploy_env):
        v1, d1 = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        v2, d2 = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        mds.activate_model_version(db, v2.model_id, ADMIN)
        first, second = _dep(db, v1.model_id), _dep(db, v2.model_id)
        assert (first.status, first.replaced_by) == ("superseded", second.deployment_id)
        assert second.status == "active" and second.previous_model_id == v1.model_id
        assert _current(db) == [v2.model_id] and deploy_env.serving.read_bytes() == d2


class TestActivationFailures:
    def _approved(self, db, Session, cand):
        mv, data = cand
        _approve(db, Session, mv)
        return mv, data

    def _assert_preserved(self, db, deploy_env, expected_current=()):
        assert deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert _current(db) == list(expected_current)
        [dep] = _deps(db)
        assert dep.status == "failed" and dep.inflight is None and dep.error_message
        return dep

    def test_staging_failure_preserves_previous_model(self, db, Session, cand, deploy_env, monkeypatch):
        mv, _ = self._approved(db, Session, cand)

        def disk_full(src, dst, *a, **k):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(mds.shutil, "copyfile", disk_full)
        with pytest.raises(mds.DeploymentFailed, match="preserved"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        dep = self._assert_preserved(db, deploy_env)
        assert dep.error_message.startswith("staging") and "No space" not in dep.error_message
        assert "activation_failed" in _events(db, deployment_id=dep.deployment_id)

    def test_readiness_failure_restores_previous_model_and_cache(self, db, Session, cand, deploy_env,
                                                                  monkeypatch, tmp_path):
        legacy = _legacy_current(db, tmp_path)
        mv, data = self._approved(db, Session, cand)
        reloads = []
        monkeypatch.setattr(mds, "_reload_cache", lambda: reloads.append(Path(settings.YOLO_MODEL_PATH).read_bytes()))

        def not_ready(serving_bytes):
            assert serving_bytes == data
            raise RuntimeError("model failed to load")

        deploy_env.warm_hook = not_ready
        with pytest.raises(mds.DeploymentFailed, match="readiness"):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        self._assert_preserved(db, deploy_env, [legacy.model_id])
        assert reloads and reloads[-1] == b"ACTIVE-MODEL"                   # cache dropped after restore

    def test_database_failure_at_commit_leaves_no_uncontrolled_deployment(self, db, Session, cand, deploy_env,
                                                                          monkeypatch):
        mv, _ = self._approved(db, Session, cand)

        def db_down(*a, **k):
            raise OperationalError("UPDATE model_versions", {}, Exception("server closed the connection"))

        monkeypatch.setattr(mds, "_finalize", db_down)
        with pytest.raises(mds.DeploymentFailed):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        dep = self._assert_preserved(db, deploy_env)
        assert "OperationalError" in dep.error_message and "server closed" not in dep.error_message

    def test_database_down_for_failure_record_is_reconciled_by_recovery(self, db, Session, cand, deploy_env,
                                                                        monkeypatch):
        mv, _ = self._approved(db, Session, cand)
        real_finalize, real_mark_failed = mds._finalize, mds._mark_failed
        monkeypatch.setattr(mds, "_finalize", lambda *a, **k: (_ for _ in ()).throw(OperationalError("x", {}, None)))
        monkeypatch.setattr(mds, "_mark_failed", lambda *a, **k: None)      # failure record cannot be written
        with pytest.raises(mds.DeploymentFailed):
            mds.activate_model_version(db, mv.model_id, ADMIN)
        [dep] = _deps(db)
        assert dep.status == "activating" and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"
        assert mds.recover_interrupted_deployments(db) == []                 # lease still live: untouched
        later = mds._now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS + 1)
        [res] = mds.recover_interrupted_deployments(db, now=later)
        assert res["deployment_id"] == dep.deployment_id
        [dep] = _deps(db)
        assert dep.status == "failed" and dep.inflight is None and _current(db) == []
        monkeypatch.setattr(mds, "_finalize", real_finalize)
        monkeypatch.setattr(mds, "_mark_failed", real_mark_failed)
        mds.activate_model_version(db, mv.model_id, ADMIN)                   # lock released: retry works
        assert _current(db) == [mv.model_id]


class TestInterruptedActivationRecovery:
    def _crash(self, db, Session, cand, deploy_env, where):
        mv, data = cand
        _approve(db, Session, mv)

        def crash(*a, **k):
            raise SimulatedCrash()

        if where == "after_switch":
            deploy_env.warm_hook = crash
        else:
            mds_inspect = mds._default_inspect
            mds._default_inspect = crash
        try:
            with pytest.raises(SimulatedCrash):
                mds.activate_model_version(db, mv.model_id, ADMIN)
        finally:
            if where != "after_switch":
                mds._default_inspect = mds_inspect
            deploy_env.warm_hook = None
        db.rollback()
        return mv, data

    def test_crash_after_file_switch_is_rolled_back_to_database_state(self, db, Session, cand, deploy_env):
        mv, data = self._crash(db, Session, cand, deploy_env, "after_switch")
        [dep] = _deps(db)
        assert dep.status == "activating" and dep.serving_switched
        assert deploy_env.serving.read_bytes() == data and _current(db) == []   # the inconsistent window
        with pytest.raises(mds.DeploymentConflict):                          # lock held until lease expiry
            mds.activate_model_version(db, mv.model_id, ADMIN)
        later = mds._now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS + 1)
        [res] = mds.recover_interrupted_deployments(db, now=later)
        assert "previous model restored" in res["outcome"]
        assert deploy_env.serving.read_bytes() == b"ACTIVE-MODEL" and _current(db) == []
        [dep] = _deps(db, deployment_id=dep.deployment_id)
        assert dep.status == "failed" and dep.inflight is None
        assert {"deployment_recovered", "activation_failed"} <= set(_events(db, deployment_id=dep.deployment_id))
        assert mds.recover_interrupted_deployments(db, now=later) == []      # idempotent
        assert mds.activate_model_version(db, mv.model_id, ADMIN)["result"] == "activated"
        assert deploy_env.serving.read_bytes() == data and _current(db) == [mv.model_id]

    def test_crash_before_switch_restores_nothing(self, db, Session, cand, deploy_env):
        self._crash(db, Session, cand, deploy_env, "before_switch")
        [dep] = _deps(db)
        assert dep.status == "activating" and not dep.serving_switched
        later = mds._now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS + 1)
        [res] = mds.recover_interrupted_deployments(db, now=later)
        assert "nothing to restore" in res["outcome"]
        assert deploy_env.serving.read_bytes() == b"ACTIVE-MODEL" and _current(db) == []

    def test_externally_changed_serving_file_is_left_untouched(self, db, Session, cand, deploy_env):
        self._crash(db, Session, cand, deploy_env, "after_switch")
        deploy_env.serving.write_bytes(b"WRITTEN-BY-SOMETHING-ELSE")
        later = mds._now() + timedelta(seconds=settings.DEPLOYMENT_LEASE_SECONDS + 1)
        [res] = mds.recover_interrupted_deployments(db, now=later)
        assert "manual check" in res["outcome"]
        assert deploy_env.serving.read_bytes() == b"WRITTEN-BY-SOMETHING-ELSE"


class TestConcurrency:
    def _race(self, Session, deploy_env, first, second):
        """Run ``first`` in a thread, held at readiness; run ``second`` while it is in flight."""
        entered, release = threading.Event(), threading.Event()
        deploy_env.warm_hook = lambda data: (entered.set(), release.wait(15))
        out = {}

        def run_first():
            s = Session()
            try:
                out["first"] = first(s)
            except Exception as exc:
                out["first"] = exc
            finally:
                s.close()

        t = threading.Thread(target=run_first)
        t.start()
        assert entered.wait(15)
        deploy_env.warm_hook = None
        s = Session()
        try:
            out["second"] = second(s)
        except Exception as exc:
            out["second"] = exc
        finally:
            s.close()
            release.set()
            t.join(15)
        return out

    def test_concurrent_activations_cannot_both_run(self, db, Session, user, tmp_path, three_cats, worker,
                                                    deploy_env):
        v1, d1 = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        v2, d2 = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        out = self._race(Session, deploy_env,
                         lambda s: mds.activate_model_version(s, v1.model_id, ADMIN),
                         lambda s: mds.activate_model_version(s, v2.model_id, ADMIN))
        assert isinstance(out["second"], mds.DeploymentConflict)
        assert out["first"]["result"] == "activated"
        assert _current(db) == [v1.model_id] and deploy_env.serving.read_bytes() == d1
        assert [d.status for d in _deps(db)] == ["active"]

    def test_concurrent_activation_and_rollback_cannot_corrupt_state(self, db, Session, user, tmp_path, three_cats,
                                                                     worker, deploy_env):
        v1, d1 = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        v2, d2 = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        out = self._race(Session, deploy_env,
                         lambda s: mds.activate_model_version(s, v2.model_id, ADMIN),
                         lambda s: mds.rollback(s, ADMIN, "panic", target_model_id=v1.model_id))
        assert isinstance(out["second"], mds.DeploymentConflict)
        assert _current(db) == [v2.model_id] and deploy_env.serving.read_bytes() == d2
        assert len(_current(db)) == 1

    def test_simultaneous_requests_race_on_the_lock(self, db, Session, user, tmp_path, three_cats, worker,
                                                    deploy_env):
        v1, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        v2, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        barrier, release = threading.Barrier(2), threading.Event()
        results = []

        def warm(data):
            release.wait(15)

        deploy_env.warm_hook = warm

        def go(model_id):
            s = Session()
            try:
                barrier.wait()
                results.append(mds.activate_model_version(s, model_id, ADMIN)["result"])
            except mds.DeploymentConflict:
                results.append("conflict")
                release.set()
            except Exception as exc:
                results.append(type(exc).__name__)
                release.set()
            finally:
                s.close()

        threads = [threading.Thread(target=go, args=(m,)) for m in (v1.model_id, v2.model_id)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        release.set()
        assert sorted(results) == ["activated", "conflict"]
        assert len(_current(db)) == 1
        assert [d.status for d in _deps(db)] == ["active"]


# ---------------------------------------------------------------------------
# 3. Rollback
# ---------------------------------------------------------------------------

class TestRollback:
    def _two_deployed(self, db, Session, user, tmp_path, three_cats, worker):
        v1, d1 = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        _approve(db, Session, v1)
        mds.activate_model_version(db, v1.model_id, ADMIN)
        v2, d2 = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        _approve(db, Session, v2)
        mds.activate_model_version(db, v2.model_id, ADMIN)
        return (v1, d1), (v2, d2)

    def test_rollback_restores_previous_deployment(self, db, Session, user, tmp_path, three_cats, worker,
                                                   deploy_env, api):
        (v1, d1), (v2, d2) = self._two_deployed(db, Session, user, tmp_path, three_cats, worker)
        overview = api.get("/api/ml/deployments").json()
        assert overview["rollback_target"]["model_id"] == v1.model_id and overview["rollback_target"]["artifact_retained"]
        r = api.post("/api/ml/deployments/rollback", json={"reason": "regression on glass"})
        assert r.status_code == 200, r.text
        assert r.json()["result"] == "rolled_back"
        assert _current(db) == [v1.model_id] and deploy_env.serving.read_bytes() == d1
        act1, act2, rb = _dep(db, v1.model_id), _dep(db, v2.model_id), _dep(db, v1.model_id, "rollback")
        assert (act1.status, act2.status, rb.status, rb.kind) == ("superseded", "rolled_back", "active", "rollback")
        assert rb.model_id == v1.model_id and rb.previous_model_id == v2.model_id
        assert rb.requested_by and rb.reason == "regression on glass"
        assert mds.candidate_status(db, v2)["lifecycle"] == "rolled_back"
        # evaluations, approvals and earlier history are all kept
        assert db.query(ModelApproval).count() == 2 and db.query(ModelEvaluation).count() == 2
        again = api.post("/api/ml/deployments/rollback", json={"reason": "double click", "target_model_id": v1.model_id})
        assert again.json()["result"] == "already_active" and len(_deps(db)) == 3

    def test_rollback_to_pre_a4_legacy_model_uses_retained_backup(self, db, Session, cand, deploy_env, tmp_path):
        legacy = _legacy_current(db, tmp_path)
        Path(db.query(TrainingJob).filter(TrainingJob.job_id == legacy.job_id).one().best_model_path).unlink()
        mv, data = cand
        _approve(db, Session, mv)
        mds.activate_model_version(db, mv.model_id, ADMIN)
        res = mds.rollback(db, ADMIN, "candidate misbehaves")
        assert res["result"] == "rolled_back"
        assert _current(db) == [legacy.model_id] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"

    def test_missing_rollback_weights_are_rejected(self, db, Session, user, tmp_path, three_cats, worker, deploy_env):
        (v1, _), (v2, d2) = self._two_deployed(db, Session, user, tmp_path, three_cats, worker)
        (Path(settings.DEPLOYED_MODELS_DIR) / _dep(db, v1.model_id).artifact_file).unlink()
        with pytest.raises(mds.PreconditionFailed, match="missing"):
            mds.rollback(db, ADMIN, "try")
        assert _current(db) == [v2.model_id] and deploy_env.serving.read_bytes() == d2
        assert {"rollback_requested", "rollback_failed"} <= set(_events(db, model_id=v1.model_id))
        assert _deps(db, kind="rollback") == []

    def test_corrupted_rollback_weights_are_rejected(self, db, Session, user, tmp_path, three_cats, worker,
                                                     deploy_env):
        (v1, _), (v2, d2) = self._two_deployed(db, Session, user, tmp_path, three_cats, worker)
        (Path(settings.DEPLOYED_MODELS_DIR) / _dep(db, v1.model_id).artifact_file).write_bytes(b"BITROT")
        with pytest.raises(mds.PreconditionFailed, match="corrupted"):
            mds.rollback(db, ADMIN, "try")
        assert _current(db) == [v2.model_id] and deploy_env.serving.read_bytes() == d2

    def test_rollback_without_history_or_to_unknown_model_is_refused(self, db, Session, cand, deploy_env):
        with pytest.raises(mds.PreconditionFailed, match="no previously deployed"):
            mds.rollback(db, ADMIN, "nothing to go back to")
        mv, _ = cand
        _approve(db, Session, mv)
        with pytest.raises(mds.PreconditionFailed, match="never deployed"):
            mds.rollback(db, ADMIN, "not deployed", target_model_id=mv.model_id)   # approved, never served
        assert _current(db) == []

    def test_failed_rollback_keeps_current_model(self, db, Session, user, tmp_path, three_cats, worker, deploy_env):
        (v1, _), (v2, d2) = self._two_deployed(db, Session, user, tmp_path, three_cats, worker)
        deploy_env.warm_hook = lambda data: (_ for _ in ()).throw(RuntimeError("cannot load"))
        with pytest.raises(mds.DeploymentFailed):
            mds.rollback(db, ADMIN, "try")
        assert _current(db) == [v2.model_id] and deploy_env.serving.read_bytes() == d2
        assert _dep(db, v1.model_id, "rollback").status == "failed" and _dep(db, v2.model_id).status == "active"


# ---------------------------------------------------------------------------
# 4. Audit, API and legacy boundary
# ---------------------------------------------------------------------------

class TestAuditAndApi:
    def test_full_lifecycle_is_audited_with_actor_and_no_paths(self, db, Session, user, tmp_path, three_cats,
                                                                worker, deploy_env, api):
        v1, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "V1")
        ev1 = _evaluate(db, Session, v1)
        assert [c["model_id"] for c in api.get("/api/ml/approvals/pending").json()["candidates"]] == [v1.model_id]
        r = api.post(f"/api/ml/candidates/{v1.model_id}/approve", json={"evaluation_id": ev1.evaluation_id})
        assert r.status_code == 200 and r.json()["approval"]["decided_by"] == user.user_id
        assert api.get("/api/ml/approvals/pending").json()["candidates"] == []
        assert api.post(f"/api/ml/models/{v1.model_id}/activate").status_code == 200
        v2, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "V2")
        ev2 = _evaluate(db, Session, v2)
        r = api.post(f"/api/ml/candidates/{v2.model_id}/reject", json={"evaluation_id": ev2.evaluation_id})
        assert r.status_code == 422                                          # reason required
        r = api.post(f"/api/ml/candidates/{v2.model_id}/reject",
                     json={"evaluation_id": ev2.evaluation_id, "reason": "misses metal cans"})
        assert r.status_code == 200
        assert api.post(f"/api/ml/models/{v2.model_id}/activate").status_code == 409

        events = api.get("/api/ml/deployments/events").json()["events"]
        types = [e["event_type"] for e in reversed(events)]
        for expected in ("approval_granted", "activation_requested", "activation_started", "activation_succeeded",
                         "approval_rejected", "activation_failed"):
            assert expected in types
        assert all(e["actor_id"] == user.user_id for e in events)
        status = api.get(f"/api/ml/candidates/{v1.model_id}/approval").json()
        assert status["lifecycle"] == "active" and status["decisions"][0]["decision"] == "approved"
        assert status["evaluation"]["metrics"]["map50"] == 0.81
        history = api.get("/api/ml/approvals").json()["approvals"]
        assert {a["decision"] for a in history} == {"approved", "rejected"}
        deployments = api.get("/api/ml/deployments?kind=activation").json()
        assert deployments["active_model"]["model_id"] == v1.model_id and len(deployments["history"]) == 1
        assert api.get("/api/ml/deployments?kind=bogus").status_code == 422
        for payload in (events, status, history, deployments):
            text = json.dumps(payload)
            assert str(tmp_path) not in text and str(tmp_path).replace("\\", "\\\\") not in text

    def test_api_validates_requests(self, db, Session, cand, api):
        mv, _ = cand
        assert api.post(f"/api/ml/candidates/{mv.model_id}/approve", json={}).status_code == 422
        assert api.post(f"/api/ml/candidates/{mv.model_id}/approve",
                        json={"evaluation_id": "x", "extra": 1}).status_code == 422
        assert api.post(f"/api/ml/candidates/{mv.model_id}/approve", json={"evaluation_id": "nope"}).status_code == 404
        assert api.post("/api/ml/candidates/nope/approve", json={"evaluation_id": "x"}).status_code == 404
        assert api.post("/api/ml/deployments/rollback", json={"reason": " "}).status_code == 422
        assert api.post("/api/ml/models/nope/activate").status_code == 404
        assert api.post("/api/ml/deployments/recover").json()["recovered"] == []


class TestLegacyBoundary:
    def test_direct_flag_write_on_snapshot_candidate_is_blocked(self, db, cand, deploy_env):
        mv, _ = cand
        mv.is_current = True
        with pytest.raises(ActivationGuardError):
            db.commit()
        db.rollback()
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"

    def test_legacy_endpoint_still_refuses_unapproved_candidate(self, db, Session, cand, api, deploy_env):
        mv, _ = cand
        _evaluate(db, Session, mv)
        r = api.post(f"/api/ml/models/{mv.model_id}/activate")
        assert r.status_code == 409 and "approved" in r.json()["error"]["message"]
        assert _current(db) == [] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"

    def test_legacy_model_activation_is_controlled_and_audited(self, db, tmp_path, api, deploy_env, monkeypatch):
        old = _legacy_current(db, tmp_path)
        new_weights = tmp_path / "legacy_v2.pt"
        new_weights.write_bytes(b"LEGACY-V2")
        job = TrainingJob(version="v2", status="completed", best_model_path=str(new_weights))
        db.add(job)
        db.commit()
        new = ModelVersion(job_id=job.job_id, version="v2", is_current=False)
        db.add(new)
        db.commit()
        r = api.post(f"/api/ml/models/{new.model_id}/activate")
        assert r.status_code == 200 and r.json()["result"] == "activated"
        assert _current(db) == [new.model_id] and deploy_env.serving.read_bytes() == b"LEGACY-V2"
        [dep] = _deps(db)
        assert dep.kind == "legacy_activation" and dep.previous_model_id == old.model_id
        assert deploy_env.warmed == [] and deploy_env.inspected == []        # v1.0 semantics: no load check
        assert mds.rollback(db, ADMIN, "back")["result"] == "rolled_back"
        assert _current(db) == [old.model_id] and deploy_env.serving.read_bytes() == b"ACTIVE-MODEL"

        monkeypatch.setattr(settings, "ALLOW_LEGACY_MODEL_ACTIVATION", False)
        r = api.post(f"/api/ml/models/{new.model_id}/activate")
        assert r.status_code == 409 and "disabled" in r.json()["error"]["message"]
        assert _current(db) == [old.model_id]

    def test_legacy_failed_job_and_missing_file_keep_v1_status_codes(self, db, tmp_path, api):
        job = TrainingJob(version="v9", status="failed")
        db.add(job)
        db.commit()
        mv = ModelVersion(job_id=job.job_id, version="v9")
        db.add(mv)
        db.commit()
        assert api.post(f"/api/ml/models/{mv.model_id}/activate").status_code == 400
        job.status, job.best_model_path = "completed", str(tmp_path / "gone.pt")
        db.commit()
        assert api.post(f"/api/ml/models/{mv.model_id}/activate").status_code == 400

    def test_invalid_state_transitions_fail(self):
        dep = ModelDeployment(deployment_id="d", status="failed")
        with pytest.raises(mds.InvalidTransition):
            mds._transition(dep, "active")
        dep.status = "superseded"
        with pytest.raises(mds.InvalidTransition):
            mds._transition(dep, "active")


class TestNoRealModelWork:
    def test_yolo_construction_and_training_are_blocked(self):
        import ultralytics
        from conftest import RealTrainingBlocked
        with pytest.raises(AssertionError):
            ultralytics.YOLO("anything.pt")
        from ultralytics.engine.model import Model
        with pytest.raises(RealTrainingBlocked):
            Model.train(object())


# ---------------------------------------------------------------------------
# 5. Real-JWT access control (runs only against an isolated *test* database)
# ---------------------------------------------------------------------------

_A4_ENDPOINTS = [
    ("get", "/api/ml/approvals/pending", None),
    ("get", "/api/ml/approvals", None),
    ("get", "/api/ml/candidates/some-model/approval", None),
    ("post", "/api/ml/candidates/some-model/approve", {"evaluation_id": "e"}),
    ("post", "/api/ml/candidates/some-model/reject", {"evaluation_id": "e", "reason": "nope"}),
    ("post", "/api/ml/models/some-model/activate", None),
    ("get", "/api/ml/deployments", None),
    ("get", "/api/ml/deployments/events", None),
    ("post", "/api/ml/deployments/rollback", {"reason": "nope"}),
    ("post", "/api/ml/deployments/recover", None),
]


@pytest.mark.skipif(
    "test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
    reason="real-JWT access test only runs against an isolated *test* database",
)
class TestAccessControl:
    @pytest.mark.parametrize("method,url,body", _A4_ENDPOINTS)
    def test_unauthenticated_and_normal_users_rejected(self, client, user_auth, method, url, body):
        kwargs = {"json": body} if body is not None else {}
        assert getattr(client, method)(url, **kwargs).status_code == 401
        assert getattr(client, method)(url, headers=user_auth["headers"], **kwargs).status_code == 403
