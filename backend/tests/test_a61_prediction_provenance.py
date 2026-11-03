"""
ZWM v1.1.0 Block A6.1 — immutable prediction provenance.

Isolation as in A1-A6.0: own database (SQLite per test or the throwaway PostgreSQL
database from ZWM_A1_TEST_DATABASE_URL), synthetic weights/images under tmp_path,
ultralytics.YOLO replaced by an in-process fake (no real load, inference or download).
"""
import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.models.image import Image
from app.models.prediction import PredictionRecord, PredictionRecordImmutableError
from app.models.training import TrainingSnapshot
from app.models.user import User
from app.services import model_cache as mc
from app.services import model_deployment_service as mds
from app.services import prediction_service as ps
from app.services import training_dataset_service as tds
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import eval_dirs  # noqa: F401
from test_a4_model_deployment import (  # noqa: F401
    ADMIN, _approve, _new_candidate, cand, deploy_env,
)
from test_a60_label_review import _labelled, _snapshot_digest
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user, _complete_many, _set_threshold,
)


class _T(list):
    def tolist(self):
        return list(self)


class FakeBox:
    def __init__(self, cls, conf, xyxy):
        self.cls, self.conf, self.xyxy = [cls], [conf], [_T(xyxy)]


class FakeDetector:
    """Stand-in for a loaded YOLO detector. Results are synthetic test data."""
    loads = []
    detections = [(0, 0.91, [1.5, 2.0, 30.25, 40.0]), (2, 0.55, [5.0, 5.0, 9.0, 9.0])]
    hook = None

    def __init__(self, path, task=None):
        FakeDetector.loads.append(str(path))
        self.names = {0: "Cat A", 1: "Cat B", 2: "Cat C"}

    def __call__(self, *a, **k):
        if FakeDetector.hook:
            FakeDetector.hook()
        return [type("R", (), {"boxes": [FakeBox(*d) for d in FakeDetector.detections]})()]

    def export(self, *a, **k):
        return None


@pytest.fixture(autouse=True)
def fake_detector(monkeypatch, deploy_env):
    import ultralytics
    FakeDetector.loads, FakeDetector.hook = [], None
    FakeDetector.detections = [(0, 0.91, [1.5, 2.0, 30.25, 40.0]), (2, 0.55, [5.0, 5.0, 9.0, 9.0])]
    monkeypatch.setattr(ultralytics, "YOLO", FakeDetector)
    monkeypatch.setattr(settings, "YOLO_INFERENCE_BACKEND", "pt")
    monkeypatch.setattr(mc.YOLOModelCache, "_integrity_check", None)   # the app hook reads another DB
    cache = mc.YOLOModelCache()
    cache.reload()
    yield FakeDetector
    cache.reload()


def _jpeg():
    from PIL import Image as PILImage
    import numpy as np
    buf = BytesIO()
    PILImage.fromarray((np.random.RandomState(7).rand(480, 640, 3) * 255).astype("uint8")).save(buf, format="JPEG")
    buf.seek(0)
    return buf


def _predict(api, **data):
    return api.post("/api/ml/predict", files={"file": ("x.jpg", _jpeg(), "image/jpeg")}, data=data or None)


def _record(db, prediction_id):
    db.expire_all()
    return db.query(PredictionRecord).filter(PredictionRecord.prediction_id == prediction_id).one()


def _frozen(rec):
    return {c.name: getattr(rec, c.name) for c in PredictionRecord.__table__.columns}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _other_user(db, role="user"):
    import uuid
    u = User(email=f"o_{uuid.uuid4().hex[:6]}@test.com", password_hash="x", role=role)
    db.add(u)
    db.commit()
    return u


def _as(api, who):
    from app.dependencies.auth import get_current_user
    from app.main import app as fastapi_app
    fastapi_app.dependency_overrides[get_current_user] = lambda: who


# ---------------------------------------------------------------------------
# 1-4. Provenance + exact attribution + result preservation
# ---------------------------------------------------------------------------

class TestAttribution:
    def test_prediction_is_attributed_to_the_exact_active_deployment(self, db, Session, cand, deploy_env, api):
        mv, data = cand
        _approve(db, Session, mv)
        dep = mds.activate_model_version(db, mv.model_id, ADMIN)["deployment"]
        r = _predict(api)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"predictions", "count", "prediction_id"}             # backward compatible + id
        assert body["predictions"] == [{"class": 0, "confidence": 0.91, "bbox": [1.5, 2.0, 30.25, 40.0]},
                                       {"class": 2, "confidence": 0.55, "bbox": [5.0, 5.0, 9.0, 9.0]}]
        rec = _record(db, body["prediction_id"])
        assert (rec.source, rec.status, rec.attribution) == ("ml_predict", "succeeded", "active_deployment")
        assert rec.model_sha256 == _sha(deploy_env.serving) == dep["weights_sha256"]
        assert (rec.deployment_id, rec.model_version_id, rec.model_version) == (
            dep["deployment_id"], mv.model_id, mv.version)
        assert rec.snapshot_id == dep["snapshot_id"] and rec.class_map_sha256
        assert rec.class_names == {"0": "Cat A", "1": "Cat B", "2": "Cat C"}
        assert rec.detections == [{"class_id": 0, "label": "Cat A", "confidence": 0.91, "bbox": [1.5, 2.0, 30.25, 40.0]},
                                  {"class_id": 2, "label": "Cat C", "confidence": 0.55, "bbox": [5.0, 5.0, 9.0, 9.0]}]
        assert rec.confidence_is_model_score is True and rec.detection_count == 2
        assert rec.environment == "test" and rec.inference_backend == "pytorch" and rec.model_artifact == "best.pt"
        assert rec.requested_by == db.query(User).filter(User.user_id == rec.requested_by).one().user_id

    def test_unmanaged_artifact_is_never_attributed_to_a_model_version(self, db, deploy_env, api):
        rec = _record(db, _predict(api).json()["prediction_id"])
        assert rec.attribution == "unmanaged_artifact" and rec.model_sha256 == _sha(deploy_env.serving)
        assert rec.model_version_id is None and rec.deployment_id is None and rec.snapshot_id is None

    def test_identity_that_cannot_be_confirmed_is_recorded_as_unverified(self, db, api, monkeypatch):
        from app.routes import ml
        monkeypatch.setattr(ml.model_cache, "get_model_with_identity", lambda: (FakeDetector("x"), None))
        rec = _record(db, _predict(api).json()["prediction_id"])
        assert rec.attribution == "unverified" and rec.model_sha256 is None and rec.model_version_id is None
        assert rec.detection_count == 2                                         # result still preserved

    def test_cache_returns_identity_of_the_loaded_object(self, deploy_env):
        cache = mc.YOLOModelCache()
        model, ident = cache.get_model_with_identity()
        assert ident == {"sha256": _sha(deploy_env.serving), "backend": "pytorch", "artifact": "best.pt"}
        deploy_env.serving.write_bytes(b"SWAPPED")                              # switch on disk
        model2, ident2 = cache.get_model_with_identity()
        assert model2 is not model and ident2["sha256"] == hashlib.sha256(b"SWAPPED").hexdigest()

    def test_failed_inference_is_recorded_without_a_trace(self, db, api):
        def boom():
            raise RuntimeError("cuda exploded at C:\\secret\\x")
        FakeDetector.hook = boom
        r = _predict(api)
        assert r.status_code == 500 and "Prediction inference failed" in r.text      # unchanged contract
        [rec] = db.query(PredictionRecord).all()
        assert rec.status == "failed" and rec.error == "RuntimeError" and rec.detections == []

    def test_no_model_creates_no_prediction(self, db, deploy_env, api):
        deploy_env.serving.unlink()
        assert _predict(api).status_code == 503
        assert db.query(PredictionRecord).count() == 0

    def test_prediction_that_cannot_be_recorded_is_not_returned(self, db, api, monkeypatch):
        real = ps.new_record
        monkeypatch.setattr(ps, "new_record", lambda **kw: real(**{**kw, "source": None}))   # NOT NULL violation
        r = _predict(api)
        assert r.status_code == 500 and "could not be recorded" in r.text and "predictions" not in r.text


# ---------------------------------------------------------------------------
# 5-7. Multiple predictions, model switching, rollback, concurrency
# ---------------------------------------------------------------------------

class TestHistoryAcrossModelChanges:
    def test_activation_and_rollback_never_rewrite_earlier_predictions(self, db, Session, user, tmp_path, three_cats,
                                                                      worker, deploy_env, api):
        v1, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "P1")
        _approve(db, Session, v1)
        d1 = mds.activate_model_version(db, v1.model_id, ADMIN)["deployment"]
        first = _record(db, _predict(api).json()["prediction_id"])
        frozen_first = _frozen(first)
        v2, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "P2")
        _approve(db, Session, v2)
        d2 = mds.activate_model_version(db, v2.model_id, ADMIN)["deployment"]
        second = _record(db, _predict(api).json()["prediction_id"])
        rb = mds.rollback(db, ADMIN, "regression")["deployment"]
        third = _record(db, _predict(api).json()["prediction_id"])
        assert _frozen(_record(db, first.prediction_id)) == frozen_first
        assert (first.model_version_id, first.deployment_id) == (v1.model_id, d1["deployment_id"])
        assert (second.model_version_id, second.deployment_id) == (v2.model_id, d2["deployment_id"])
        assert (third.model_version_id, third.deployment_id, third.attribution) == (
            v1.model_id, rb["deployment_id"], "active_deployment")
        assert first.model_sha256 == third.model_sha256 != second.model_sha256

    def test_switch_during_inference_cannot_misattribute(self, db, Session, user, tmp_path, three_cats, worker,
                                                        deploy_env, api):
        v1, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "C1")
        _approve(db, Session, v1)
        d1 = mds.activate_model_version(db, v1.model_id, ADMIN)["deployment"]
        v2, _ = _new_candidate(db, user, tmp_path, three_cats, worker, "C2")
        _approve(db, Session, v2)
        switched = {}

        def activate_v2_mid_inference():
            FakeDetector.hook = None
            s = Session()
            try:
                switched.update(mds.activate_model_version(s, v2.model_id, ADMIN)["deployment"])
            finally:
                s.close()

        FakeDetector.hook = activate_v2_mid_inference
        rec = _record(db, _predict(api).json()["prediction_id"])
        assert switched["status"] == "active" and _sha(deploy_env.serving) == switched["weights_sha256"]
        assert (rec.model_version_id, rec.deployment_id) == (v1.model_id, d1["deployment_id"])
        assert rec.model_sha256 == d1["weights_sha256"] != switched["weights_sha256"]
        after = _record(db, _predict(api).json()["prediction_id"])
        assert (after.model_version_id, after.deployment_id) == (v2.model_id, switched["deployment_id"])

    def test_multiple_predictions_for_one_image(self, db, user, tmp_path, three_cats, api):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        ids = [_predict(api, image_id=img.image_id).json()["prediction_id"] for _ in range(3)]
        listed = api.get(f"/api/ml/predictions?image_id={img.image_id}").json()
        assert listed["total"] == 3 and {i["prediction_id"] for i in listed["items"]} == set(ids)
        assert all(i["image_id"] == img.image_id for i in listed["items"])


# ---------------------------------------------------------------------------
# 8. Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_orm_refuses_updates_and_deletes(self, db, api):
        rec = _record(db, _predict(api).json()["prediction_id"])
        rec.detections = []
        with pytest.raises(PredictionRecordImmutableError):
            db.commit()
        db.rollback()
        db.delete(_record(db, rec.prediction_id))
        with pytest.raises(PredictionRecordImmutableError):
            db.commit()
        db.rollback()

    def test_database_refuses_updates_and_deletes(self, db, api):
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL trigger")
        pid = _predict(api).json()["prediction_id"]
        for sql in ("UPDATE prediction_records SET model_version_id = 'forged' WHERE prediction_id = :p",
                    "UPDATE prediction_records SET created_at = now() - interval '1 day' WHERE prediction_id = :p",
                    "DELETE FROM prediction_records WHERE prediction_id = :p"):
            with pytest.raises(Exception, match="append-only"):
                db.execute(text(sql), {"p": pid})
            db.rollback()
        assert _record(db, pid).detection_count == 2


# ---------------------------------------------------------------------------
# 10-11. API access control and compatibility
# ---------------------------------------------------------------------------

class TestPredictionApi:
    def test_users_see_only_their_own_predictions(self, db, user, api):
        mine = _predict(api).json()["prediction_id"]
        other = _other_user(db)
        _as(api, other)
        theirs = _predict(api).json()["prediction_id"]
        assert api.get(f"/api/ml/predictions/{mine}").status_code == 404            # existence not leaked
        assert [i["prediction_id"] for i in api.get("/api/ml/predictions").json()["items"]] == [theirs]
        assert api.get(f"/api/ml/predictions?user_id={user.user_id}").status_code == 403
        assert "requested_by" not in api.get(f"/api/ml/predictions/{theirs}").json()
        admin = _other_user(db, role="admin")
        _as(api, admin)
        assert api.get("/api/ml/predictions").json()["total"] == 2
        only = api.get(f"/api/ml/predictions?user_id={user.user_id}").json()
        assert [i["prediction_id"] for i in only["items"]] == [mine] and only["items"][0]["requested_by"] == user.user_id
        assert api.get(f"/api/ml/predictions/{mine}").json()["prediction_id"] == mine

    def test_filters_pagination_and_validation(self, db, api):
        for _ in range(5):
            _predict(api)
        p1 = api.get("/api/ml/predictions?limit=2&offset=0").json()
        p3 = api.get("/api/ml/predictions?limit=2&offset=4").json()
        assert p1["total"] == 5 and len(p1["items"]) == 2 and len(p3["items"]) == 1
        assert api.get("/api/ml/predictions?source=ml_predict&status=succeeded").json()["total"] == 5
        for bad in ("source=disk", "status=edited", "limit=0", "limit=500", "offset=-1"):
            assert api.get(f"/api/ml/predictions?{bad}").status_code == 422
        assert api.get("/api/ml/predictions/does-not-exist").status_code == 404

    def test_image_link_requires_ownership(self, db, user, tmp_path, three_cats, api):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        _as(api, _other_user(db))
        assert _predict(api, image_id=img.image_id).status_code == 403
        assert _predict(api, image_id="missing-image").status_code == 404
        assert db.query(PredictionRecord).count() == 0

    def test_responses_never_contain_paths(self, db, user, tmp_path, three_cats, api):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        pid = _predict(api, image_id=img.image_id).json()["prediction_id"]
        for payload in (api.get(f"/api/ml/predictions/{pid}").text, api.get("/api/ml/predictions").text):
            assert str(tmp_path) not in payload and str(tmp_path).replace("\\", "\\\\") not in payload
            assert ":\\\\" not in payload and "/tmp/" not in payload


# ---------------------------------------------------------------------------
# 12-13. AI segmentation, upload validation, A6.0 eligibility unchanged
# ---------------------------------------------------------------------------

class TestSegmentationAndUpload:
    @pytest.fixture()
    def seg(self, monkeypatch):
        from app.routes import ai_segmentation
        det = ai_segmentation.ai_detector_instance
        monkeypatch.setattr(det, "model_identity", lambda: {"loaded": True, "artifact": "seg.pt", "sha256": "a" * 64})
        monkeypatch.setattr(det, "segment_from_click", lambda **kw: {
            "points": [{"x": 1, "y": 1}, {"x": 9, "y": 1}, {"x": 9, "y": 9}], "bbox": [1, 1, 9, 9],
            "class_name": "Waste Object", "confidence": 0.95, "engine": "yolo_seg_mask"})
        monkeypatch.setattr(det, "segment_image", lambda **kw: [
            {"points": [{"x": 2, "y": 2}, {"x": 8, "y": 2}, {"x": 8, "y": 8}], "bbox": [2, 2, 8, 8],
             "class_name": "Waste Object", "confidence": 0.96, "engine": "opencv_contours"}])
        return det

    def test_polygon_click_is_recorded_without_fabricated_confidence(self, db, user, tmp_path, three_cats, api, seg):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        r = api.post("/api/ai/polygon-click", json={"image_id": img.image_id, "x": 5, "y": 5})
        assert r.status_code == 200 and r.json()["polygon"]["confidence"] == 0.95      # contract unchanged
        rec = _record(db, r.json()["prediction_id"])
        assert (rec.source, rec.model_kind, rec.attribution) == ("ai_polygon_click", "segmentation_assistant",
                                                                 "not_applicable")
        assert rec.image_id == img.image_id and rec.model_sha256 == "a" * 64 and rec.model_artifact == "seg.pt"
        assert rec.confidence_is_model_score is False and rec.inference_engine == "yolo_seg_mask"
        [d] = rec.detections
        assert d["confidence"] is None and d["reported_confidence"] == 0.95 and len(d["polygon"]) == 3
        assert rec.request_params == {"x": 5, "y": 5, "conf": 0.25, "input": "image_id"}

    def test_base64_only_request_is_recorded_without_an_image(self, db, api, seg):
        import base64
        b64 = base64.b64encode(_jpeg().getvalue()).decode()
        r = api.post("/api/ai/segment", json={"image": b64})
        assert r.status_code == 200
        rec = _record(db, r.json()["prediction_id"])
        assert rec.image_id is None and rec.request_params["input"] == "base64"
        assert rec.source == "ai_segment" and rec.detection_count == 1
        r2 = api.post("/api/ai/segment", json={"image": b64, "image_id": "not-a-real-image"})
        assert _record(db, r2.json()["prediction_id"]).image_id is None               # never a fabricated link

    def test_no_result_is_recorded(self, db, user, tmp_path, three_cats, api, seg, monkeypatch):
        monkeypatch.setattr(seg, "segment_from_click", lambda **kw: None)
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        assert api.post("/api/ai/polygon-click", json={"image_id": img.image_id, "x": 5, "y": 5}).status_code == 422
        [rec] = db.query(PredictionRecord).all()
        assert rec.status == "no_result" and rec.detections == []

    def test_a60_rules_unchanged(self, db, user, tmp_path, three_cats, api, seg):
        human = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        assert api.post(f"/api/annotations/image/{human.image_id}/finalize").json()["training_eligible"] is True
        assisted = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        api.post("/api/ai/polygon-click", json={"image_id": assisted.image_id, "x": 5, "y": 5})
        assert api.post(f"/api/annotations/image/{assisted.image_id}/finalize").json()["awaiting_review"] is True
        predicted = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        _predict(api, image_id=predicted.image_id)                           # boxes served for the image
        body = api.post(f"/api/annotations/image/{predicted.image_id}/finalize").json()
        assert body["awaiting_review"] is True
        db.expire_all()
        fresh = db.query(Image).filter(Image.image_id == predicted.image_id).one()
        assert tds.user_confirmation_problem(db, fresh) == "ai_suggestions_served"

    def test_upload_validation_records_the_category_inference(self, db, user, three_cats, api):
        a = three_cats[0]
        r = api.post("/api/images/upload", files={"file": ("u.jpg", _jpeg(), "image/jpeg")},
                     data={"selected_category_id": str(a.category_id)})
        assert r.status_code == 201, r.text
        image_id = r.json()["image_id"]
        [rec] = db.query(PredictionRecord).filter(PredictionRecord.image_id == image_id).all()
        assert rec.source == "upload_validation" and rec.status == "succeeded"
        assert rec.result["validation_result"] == r.json()["validation_result"]
        assert rec.detections[0] == {"class_id": 0, "label": "Cat A", "confidence": 0.91,
                                     "bbox": [1.5, 2.0, 30.25, 40.0]}
        assert rec.request_params["selected_category"] == a.class_name
        db.expire_all()
        assert db.query(Image).filter(Image.image_id == image_id).one().ai_suggested_at is None   # no boxes served


# ---------------------------------------------------------------------------
# 14. Snapshots untouched
# ---------------------------------------------------------------------------

def test_predictions_never_alter_snapshots(db, user, tmp_path, three_cats, api):
    a, b, c = three_cats
    _set_threshold(db, 3)
    _complete_many(db, user, [(a, 1), (b, 1), (c, 1)], tmp_path)
    before = (_snapshot_digest(db), db.query(TrainingSnapshot).count())
    for img in db.query(Image).all():
        _predict(api, image_id=img.image_id)
    assert (_snapshot_digest(db), db.query(TrainingSnapshot).count()) == before


@pytest.mark.skipif("test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
                    reason="real-JWT access test only runs against an isolated *test* database")
@pytest.mark.parametrize("method,url", [("get", "/api/ml/predictions"), ("get", "/api/ml/predictions/x"),
                                        ("post", "/api/ml/predict")])
def test_prediction_endpoints_require_authentication(client, method, url):
    assert getattr(client, method)(url).status_code == 401
