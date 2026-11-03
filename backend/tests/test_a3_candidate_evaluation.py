"""
ZWM v1.1.0 Block A3 — candidate model evaluation & quality gates.

Candidates are produced through the real pipeline (finalize -> snapshot ->
leased worker with a FAKE trainer). Evaluation uses mocked evaluator/inspector
functions only; conftest blocks ultralytics train/val/downloads (fail-closed).
"""
import json
import os
import threading
from pathlib import Path

import pytest

from app.config import settings
from app.models.training import ModelEvaluation, ModelVersion, TrainingSnapshotImage
from app.services import model_evaluation_service as mes
from test_a2_training_pipeline import _jobs, no_real_training, worker  # noqa: F401
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user,
    _complete_many, _set_threshold,
)

NAMES = {0: "Cat A", 1: "Cat B", 2: "Cat C"}
GOOD = {
    "map50": 0.81, "map50_95": 0.62, "precision": 0.84, "recall": 0.77,
    "per_class": [  # deliberately out of order
        {"class_index": 2, "ap50": 0.70, "ap50_95": 0.50, "precision": 0.80, "recall": 0.66},
        {"class_index": 0, "ap50": 0.90, "ap50_95": 0.71, "precision": 0.88, "recall": 0.90},
        {"class_index": 1, "ap50": 0.83, "ap50_95": 0.65, "precision": 0.84, "recall": 0.75},
    ],
}
POLICY = {"min_test_images": 3, "min_objects_per_class": 1, "min_map50": 0.5, "min_precision": 0.5, "min_recall": 0.5}


@pytest.fixture(autouse=True)
def eval_dirs(monkeypatch, tmp_path, queued):
    monkeypatch.setattr(settings, "EVALUATION_DIR", str(tmp_path / "evaluations"))
    sent = []
    monkeypatch.setattr(mes, "_send_eval_to_queue", lambda eid: sent.append(eid) or f"eval-{eid}")
    return sent


def _make_candidate(db, user, tmp_path, cats, worker, per_class=10):
    a, b, c = cats
    _complete_many(db, user, [(a, per_class), (b, per_class), (c, per_class)], tmp_path)
    job = [j for j in _jobs(db) if j.status == "queued"][-1]
    assert "completed" in worker(job.job_id)
    db.expire_all()
    return db.query(ModelVersion).filter(ModelVersion.job_id == job.job_id).one()


@pytest.fixture()
def candidate(db, user, tmp_path, three_cats, worker):
    _set_threshold(db, 30)                                   # 30 images -> 24/3/3, one test image per class
    return _make_candidate(db, user, tmp_path, three_cats, worker)


def _evaluator(result=GOOD, calls=None):
    calls = [] if calls is None else calls

    def evaluate(weights, data_yaml, split, imgsz, conf, iou):
        calls.append({"weights": weights, "data_yaml": Path(data_yaml), "split": split})
        return json.loads(json.dumps(result)) if isinstance(result, dict) else result

    evaluate.calls = calls
    return evaluate


def _run(Session, evaluation_id, evaluate=None, names=NAMES):
    return mes.run_evaluation(evaluation_id, session_factory=Session,
                              evaluate_fn=evaluate or _evaluator(), inspect_fn=lambda w: names)


def _request(db, candidate):
    ev, _ = mes.request_evaluation(db, candidate.model_id)
    return ev.evaluation_id


def _ev(db, evaluation_id):
    db.expire_all()
    return db.query(ModelEvaluation).filter(ModelEvaluation.evaluation_id == evaluation_id).one()


def _test_split_ids(db, snapshot_id):
    return {m.image_id for m in db.query(TrainingSnapshotImage).filter(
        TrainingSnapshotImage.snapshot_id == snapshot_id, TrainingSnapshotImage.split_type == "test").all()}


# ---------------------------------------------------------------------------
# Happy path, metrics, isolation
# ---------------------------------------------------------------------------

class TestEvaluation:
    def test_valid_candidate_passes_and_stays_inactive(self, db, Session, candidate, no_real_training):
        mes.update_policy(db, POLICY, None)
        eid = _request(db, candidate)
        assert "eligible_for_review" in _run(Session, eid)
        ev = _ev(db, eid)
        assert (ev.status, ev.gate_decision) == ("passed", "eligible_for_review")
        assert ev.model_id == candidate.model_id and ev.snapshot_id is not None
        assert ev.dataset_manifest_path and ev.config["split"] == "test" and ev.weights_sha256
        db.expire_all()
        assert db.query(ModelVersion).filter(ModelVersion.model_id == candidate.model_id).one().is_current is False
        assert no_real_training.read_bytes() == b"ACTIVE-MODEL"          # active weights untouched

    def test_evaluates_test_split_only_in_isolation(self, db, Session, candidate):
        mes.update_policy(db, POLICY, None)
        eid = _request(db, candidate)
        evaluate = _evaluator()
        _run(Session, eid, evaluate)
        [call] = evaluate.calls
        assert call["split"] == "test"
        root = call["data_yaml"].parent
        ev = _ev(db, eid)
        expected = _test_split_ids(db, ev.snapshot_id)
        on_disk = {p.stem for p in root.rglob("*") if p.is_file() and p.suffix in (".png", ".jpg", ".jpeg")}
        assert on_disk == expected and len(expected) == 3              # nothing but held-out test images
        assert not Path(ev.dataset_manifest_path).parent in root.parents

    def test_metrics_and_per_class_association(self, db, Session, candidate):
        mes.update_policy(db, POLICY, None)
        eid = _request(db, candidate)
        _run(Session, eid)
        ev = _ev(db, eid)
        m = ev.metrics
        assert (m["map50"], m["map50_95"], m["precision"], m["recall"]) == (0.81, 0.62, 0.84, 0.77)
        assert m["test_images"] == 3 and m["gt_objects_total"] == 3
        by_idx = {r["class_index"]: r for r in m["per_class"]}
        assert by_idx[2]["class_name"] == "Cat C" and by_idx[2]["recall"] == 0.66 and by_idx[2]["ap50"] == 0.70
        assert by_idx[0]["class_code"] == 101 and by_idx[0]["precision"] == 0.88
        assert all(r["gt_objects"] == 1 for r in m["per_class"])
        assert ev.duration_seconds is not None and ev.evaluated_at is not None
        assert ev.model_version == candidate.version

    def test_sources_and_splits_unchanged(self, db, Session, candidate):
        mes.update_policy(db, POLICY, None)
        ev = mes.request_evaluation(db, candidate.model_id)[0]
        manifest = json.loads(Path(ev.dataset_manifest_path).read_text())
        splits_before = {m.image_id: m.split_type for m in db.query(TrainingSnapshotImage).all()}
        _run(Session, ev.evaluation_id)
        from app.services.training_pipeline_service import _sha256
        for e in manifest["images"]:
            assert _sha256(Path(e["source_image"])) == e["image_sha256"]
            assert _sha256(Path(e["source_label"])) == e["label_sha256"]
        db.expire_all()
        assert {m.image_id: m.split_type for m in db.query(TrainingSnapshotImage).all()} == splits_before


# ---------------------------------------------------------------------------
# Rejections / validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_missing_weights_rejected(self, db, Session, candidate, api):
        ev = mes.request_evaluation(db, candidate.model_id)[0]
        os.remove(ev.weights_path)
        _run(Session, ev.evaluation_id)
        assert _ev(db, ev.evaluation_id).status == "error"
        assert "weights" in _ev(db, ev.evaluation_id).error_message
        r = api.post(f"/api/ml/candidates/{candidate.model_id}/evaluations")  # rejected up front
        assert r.status_code == 422 and "weights" in r.text

    def test_invalid_manifest_rejected(self, db, Session, candidate):
        ev = mes.request_evaluation(db, candidate.model_id)[0]
        path = Path(ev.dataset_manifest_path)
        data = json.loads(path.read_text())
        data["snapshot_id"] = 999
        path.write_text(json.dumps(data))
        _run(Session, ev.evaluation_id)
        ev = _ev(db, ev.evaluation_id)
        assert ev.status == "error" and "manifest does not belong" in ev.error_message

    def test_wrong_snapshot_membership_rejected(self, db, Session, candidate):
        ev = mes.request_evaluation(db, candidate.model_id)[0]
        path = Path(ev.dataset_manifest_path)
        data = json.loads(path.read_text())
        moved = next(e for e in data["images"] if e["split"] == "test")
        moved["split"] = "train"                                              # leak a test image
        path.write_text(json.dumps(data))
        evaluate = _evaluator()
        _run(Session, ev.evaluation_id, evaluate)
        ev = _ev(db, ev.evaluation_id)
        assert ev.status == "error" and "differ from the locked snapshot" in ev.error_message
        assert evaluate.calls == []

    def test_tampered_test_file_rejected(self, db, Session, candidate):
        ev = mes.request_evaluation(db, candidate.model_id)[0]
        data = json.loads(Path(ev.dataset_manifest_path).read_text())
        test_label = next(e for e in data["images"] if e["split"] == "test")["label_file"]
        (Path(ev.dataset_manifest_path).parent / test_label).write_text("0 0.5 0.5 0.1 0.1\n")
        _run(Session, ev.evaluation_id)
        assert "does not match manifest hash" in _ev(db, ev.evaluation_id).error_message

    def test_frozen_class_mapping_enforced(self, db, Session, candidate):
        ev = mes.request_evaluation(db, candidate.model_id)[0]
        evaluate = _evaluator()
        _run(Session, ev.evaluation_id, evaluate, names={0: "Cat A", 1: "Cat C", 2: "Cat B"})
        ev = _ev(db, ev.evaluation_id)
        assert ev.status == "error" and "do not match frozen class map" in ev.error_message
        assert evaluate.calls == []


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------

class TestQualityGates:
    def test_default_policy_requires_admin_configuration(self, db, Session, candidate):
        eid = _request(db, candidate)
        _run(Session, eid)
        ev = _ev(db, eid)
        assert (ev.status, ev.gate_decision) == ("failed", "policy_not_configured")
        assert ev.metrics["map50"] == 0.81                                   # still measured & recorded

    def test_gate_fail_rejects(self, db, Session, candidate):
        mes.update_policy(db, {**POLICY, "min_map50": 0.9}, None)
        eid = _request(db, candidate)
        _run(Session, eid)
        ev = _ev(db, eid)
        assert (ev.status, ev.gate_decision) == ("failed", "rejected")
        assert {"gate": "min_map50", "threshold": 0.9, "value": 0.81, "outcome": "fail"} in ev.gate_results

    def test_per_class_recall_gate(self, db, Session, candidate):
        mes.update_policy(db, {**POLICY, "min_class_recall": 0.7}, None)
        eid = _request(db, candidate)
        _run(Session, eid)
        ev = _ev(db, eid)
        failed = [g for g in ev.gate_results if g["outcome"] == "fail"]
        assert ev.gate_decision == "rejected" and [g["class_index"] for g in failed] == [2]

    def test_missing_metric_never_passes(self, db, Session, candidate):
        mes.update_policy(db, POLICY, None)
        eid = _request(db, candidate)
        partial = {**GOOD, "precision": float("nan"), "recall": None}
        _run(Session, eid, _evaluator(partial))
        ev = _ev(db, eid)
        assert ev.metrics["precision"] is None and ev.metrics["recall"] is None
        assert (ev.status, ev.gate_decision) == ("failed", "insufficient_evidence")
        assert {g["gate"] for g in ev.gate_results if g["outcome"] == "not_computable"} == {"min_precision", "min_recall"}

    def test_insufficient_samples_block_review(self, db, Session, candidate):
        mes.update_policy(db, {**POLICY, "min_test_images": 50}, None)
        eid = _request(db, candidate)
        evaluate = _evaluator()
        _run(Session, eid, evaluate)
        ev = _ev(db, eid)
        assert (ev.status, ev.gate_decision) == ("failed", "insufficient_evidence")
        assert evaluate.calls == [] and ev.metrics["model_evaluated"] is False

    def test_class_coverage_requires_test_objects(self, db, Session, candidate):
        mes.update_policy(db, {**POLICY, "min_objects_per_class": 2}, None)
        eid = _request(db, candidate)
        _run(Session, eid)
        assert _ev(db, eid).gate_decision == "insufficient_evidence"


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------

class TestBaseline:
    def test_no_baseline(self, db, Session, candidate):
        mes.update_policy(db, {**POLICY, "max_map50_regression": 0.05}, None)
        eid = _request(db, candidate)
        _run(Session, eid)
        ev = _ev(db, eid)
        assert ev.baseline["status"] == "no_baseline"
        assert ev.gate_decision == "eligible_for_review"                    # regression gate skipped, documented
        assert any(g["gate"] == "max_map50_regression" and g["outcome"] == "skipped" for g in ev.gate_results)

    def test_incompatible_legacy_baseline_not_compared(self, db, Session, candidate):
        from app.services.training_service import trigger_training_job
        legacy_job = trigger_training_job(db, version="v-legacy", class_counts={})
        legacy_job.status = "completed"
        db.add(ModelVersion(job_id=legacy_job.job_id, version="v-legacy", is_current=True))
        db.commit()
        mes.update_policy(db, POLICY, None)
        eid = _request(db, candidate)
        evaluate = _evaluator()
        _run(Session, eid, evaluate)
        ev = _ev(db, eid)
        assert ev.baseline["status"] == "incompatible" and "class mapping" in ev.baseline["reason"]
        assert len(evaluate.calls) == 1                                      # baseline never scored

    def test_compatible_baseline_compared_and_regression_detected(
        self, db, Session, user, tmp_path, three_cats, worker
    ):
        _set_threshold(db, 30)
        v1 = _make_candidate(db, user, tmp_path, three_cats, worker)
        from app.services.model_deployment_service import allow_current_change
        with allow_current_change(db):                                       # stand-in for an A4 activation
            v1.is_current = True                                             # (direct flag writes are blocked)
            db.commit()
        v2 = _make_candidate(db, user, tmp_path, three_cats, worker)
        mes.update_policy(db, {**POLICY, "max_map50_regression": 0.05}, None)
        eid = _request(db, v2)

        def evaluate(weights, data_yaml, split, imgsz, conf, iou):
            return {**GOOD, "map50": 0.90 if "a1_best" in weights and v1.job_id[:8] in weights else 0.81}

        _run(Session, eid, evaluate)
        ev = _ev(db, eid)
        assert ev.baseline["status"] == "compared" and ev.baseline["model_id"] == v1.model_id
        assert ev.baseline["deltas"]["map50"] == pytest.approx(-0.09)
        assert ev.gate_decision == "rejected"
        db.expire_all()
        assert db.query(ModelVersion).filter(ModelVersion.model_id == v1.model_id).one().is_current is True


# ---------------------------------------------------------------------------
# Idempotency, concurrency, API, activation guard
# ---------------------------------------------------------------------------

class TestLifecycleAndApi:
    def test_duplicate_requests_are_idempotent(self, db, Session, candidate, api, eval_dirs):
        r1 = api.post(f"/api/ml/candidates/{candidate.model_id}/evaluations")
        r2 = api.post(f"/api/ml/candidates/{candidate.model_id}/evaluations")
        assert r1.json()["created"] is True and r2.json()["created"] is False
        assert r1.json()["evaluation"]["evaluation_id"] == r2.json()["evaluation"]["evaluation_id"]
        eid = r1.json()["evaluation"]["evaluation_id"]
        assert eval_dirs == [eid]                                            # queued once
        evaluate = _evaluator()
        _run(Session, eid, evaluate)
        assert "skipped" in _run(Session, eid, evaluate) and len(evaluate.calls) == 1

    def test_concurrent_runs_execute_once(self, db, Session, candidate):
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("row locking requires PostgreSQL")
        eid = _request(db, candidate)
        evaluate = _evaluator()
        barrier = threading.Barrier(3)
        out = []

        def go():
            barrier.wait()
            out.append(_run(Session, eid, evaluate))

        threads = [threading.Thread(target=go) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(evaluate.calls) == 1 and sum("skipped" in o for o in out) == 2

    def test_admin_endpoints_and_policy_validation(self, db, Session, candidate, api):
        assert api.get("/api/ml/evaluation-policy").json()["configured"] is False
        for bad in ({"min_map50": 1.5}, {"min_test_images": 0}, {"min_recall": -0.1}, {"unknown_gate": 1}):
            assert api.put("/api/ml/evaluation-policy", json=bad).status_code == 422
        assert api.put("/api/ml/evaluation-policy", json=POLICY).json()["configured"] is True
        eid = api.post(f"/api/ml/candidates/{candidate.model_id}/evaluations").json()["evaluation"]["evaluation_id"]
        _run(Session, eid)
        [cand] = api.get("/api/ml/candidates").json()["candidates"]
        assert cand["latest_evaluation"]["status"] == "passed" and cand["is_current"] is False
        detail = api.get(f"/api/ml/evaluations/{eid}").json()
        assert detail["metrics"]["map50"] == 0.81 and detail["gate_results"] and detail["baseline"]
        assert api.get(f"/api/ml/evaluations?model_id={candidate.model_id}").json()["evaluations"][0]["evaluation_id"] == eid

    def test_passed_candidate_cannot_be_activated_directly(self, db, Session, candidate, api, no_real_training):
        mes.update_policy(db, POLICY, None)
        _run(Session, _request(db, candidate))
        r = api.post(f"/api/ml/models/{candidate.model_id}/activate")
        assert r.status_code == 409
        db.expire_all()
        assert db.query(ModelVersion).filter(ModelVersion.model_id == candidate.model_id).one().is_current is False
        assert no_real_training.read_bytes() == b"ACTIVE-MODEL"


class TestFailClosed:
    def test_real_yolo_validation_is_blocked(self):
        from conftest import RealTrainingBlocked
        from ultralytics import YOLO
        with pytest.raises(RealTrainingBlocked):
            YOLO.val(object(), data="x.yaml")


_A3_ENDPOINTS = [
    ("get", "/api/ml/candidates", None),
    ("post", "/api/ml/candidates/some-model/evaluations", None),
    ("get", "/api/ml/evaluations", None),
    ("get", "/api/ml/evaluations/some-eval", None),
    ("get", "/api/ml/evaluation-policy", None),
    ("put", "/api/ml/evaluation-policy", {"min_map50": 0.1}),
]


@pytest.mark.skipif(
    "test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
    reason="real-JWT access test only runs against an isolated *test* database",
)
class TestAccessControl:
    @pytest.mark.parametrize("method,url,body", _A3_ENDPOINTS)
    def test_unauthenticated_and_normal_users_rejected(self, client, user_auth, method, url, body):
        kwargs = {"json": body} if body is not None else {}
        assert getattr(client, method)(url, **kwargs).status_code == 401
        assert getattr(client, method)(url, headers=user_auth["headers"], **kwargs).status_code == 403

    def test_rejected_policy_update_changes_nothing(self, client, user_auth, admin_auth):
        before = client.get("/api/ml/evaluation-policy", headers=admin_auth["headers"]).json()
        client.put("/api/ml/evaluation-policy", json={"min_map50": 0.99}, headers=user_auth["headers"])
        client.put("/api/ml/evaluation-policy", json={"min_map50": 0.99})
        assert client.get("/api/ml/evaluation-policy", headers=admin_auth["headers"]).json() == before
