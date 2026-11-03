"""
ZWM v1.1.0 Block A6.2 — prediction feedback collection and administrator review.

Isolation as in A1-A6.1: own database (SQLite per test or the throwaway PostgreSQL
database from ZWM_A1_TEST_DATABASE_URL), synthetic weights/images under tmp_path,
ultralytics.YOLO replaced by the A6.1 in-process fake (no real load, inference or
download), segmentation assistant monkeypatched.
"""
import threading
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.config import settings
from app.models.annotation import Annotation
from app.models.category import Category
from app.models.feedback import FeedbackDecision, FeedbackImmutableError, PredictionFeedback
from app.models.image import Image
from app.models.prediction import PredictionRecord
from app.models.training import DeploymentEvent, ModelDeployment, TrainingSnapshot
from app.models.user import Admin
from app.services import feedback_service as fs
from app.services import model_deployment_service as mds
from app.services import training_dataset_service as tds
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import eval_dirs  # noqa: F401
from test_a4_model_deployment import ADMIN, _approve, cand, deploy_env  # noqa: F401
from test_a60_label_review import _labelled, _snapshot_digest
from test_a61_prediction_provenance import (  # noqa: F401
    FakeDetector, _as, _frozen, _jpeg, _other_user, _predict, _record, fake_detector,
)
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user, _complete_many, _set_threshold,
)


def _as_admin(admin):
    from app.dependencies.auth import get_current_user, require_admin
    from app.main import app as fastapi_app
    fastapi_app.dependency_overrides[get_current_user] = lambda: admin
    fastapi_app.dependency_overrides[require_admin] = lambda: admin


def _submit(api, pid, **body):
    return api.post(f"/api/ml/predictions/{pid}/feedback", json=body)


def _image_prediction(db, api, user, tmp_path, cat):
    """An ml_predict prediction linked to the user's own 200x200 image (2 detections)."""
    img = _labelled(db, user, cat, tmp_path, ai=False, finalize=False)
    r = _predict(api, image_id=img.image_id)
    assert r.status_code == 200, r.text
    return img, r.json()["prediction_id"]


def _image_state(db, image_id):
    db.expire_all()
    img = db.query(Image).filter(Image.image_id == image_id).one()
    anns = sorted(repr([(c.name, getattr(a, c.name)) for c in Annotation.__table__.columns])
                  for a in db.query(Annotation).filter(Annotation.image_id == image_id).all())
    label = open(img.yolo_txt_path, "rb").read() if img.yolo_txt_path else None
    return ({c.name: getattr(img, c.name) for c in Image.__table__.columns}, anns, label)


def _decision_rows(db, feedback_id):
    db.expire_all()
    return db.query(FeedbackDecision).filter(FeedbackDecision.feedback_id == feedback_id).all()


@pytest.fixture()
def admin(db):
    return _other_user(db, role="admin")


@pytest.fixture()
def seg(monkeypatch):
    from app.routes import ai_segmentation
    det = ai_segmentation.ai_detector_instance
    monkeypatch.setattr(det, "model_identity", lambda: {"loaded": True, "artifact": "seg.pt", "sha256": "a" * 64})
    monkeypatch.setattr(det, "segment_from_click", lambda **kw: {
        "points": [{"x": 1, "y": 1}, {"x": 9, "y": 1}, {"x": 9, "y": 9}], "bbox": [1, 1, 9, 9],
        "class_name": "Waste Object", "confidence": 0.95, "engine": "opencv_grabcut"})
    monkeypatch.setattr(det, "segment_image", lambda **kw: [])
    return det


# ---------------------------------------------------------------------------
# 1-2, 5. Submission and validation
# ---------------------------------------------------------------------------

class TestSubmission:
    def test_valid_feedback_is_recorded_with_its_prediction_reference(self, db, user, tmp_path, three_cats, api):
        img, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        frozen = _frozen(_record(db, pid))
        r = _submit(api, pid, feedback_type="incorrect_class", detection_index=0,
                    suggested_category_id=three_cats[1].category_id, explanation="  It is a Cat B item. ")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "pending" and body["decision"] is None and body["decision_history"] == []
        assert (body["prediction_id"], body["feedback_type"], body["target"], body["detection_index"]) == (
            pid, "incorrect_class", "detection:0", 0)
        assert body["explanation"] == "It is a Cat B item."
        assert body["suggested_correction"] == {"category_id": three_cats[1].category_id, "class_name": "Cat B",
                                                "yolo_class_index": three_cats[1].yolo_class_index,
                                                "geometry": None}
        rec = _record(db, pid)
        ref = body["prediction_reference"]
        assert ref["original_detection"] == rec.detections[0] and ref["image_id"] == img.image_id
        assert (ref["source"], ref["model_sha256"], ref["attribution"]) == (rec.source, rec.model_sha256,
                                                                            rec.attribution)
        assert ref["confidence_is_model_score"] is True
        assert "submitted_by" not in body and "prediction" not in body          # admin-only fields
        fb = db.query(PredictionFeedback).one()
        assert fb.submitted_by == user.user_id and fb.submitter_role == "user" and fb.environment == "test"
        assert fb.submitted_at is not None
        assert _frozen(_record(db, pid)) == frozen                              # prediction untouched
        assert api.get(f"/api/ml/feedback/{body['feedback_id']}").json()["status"] == "pending"

    @pytest.mark.parametrize("body", [
        dict(feedback_type="incorrect_geometry", detection_index=1,
             suggested_geometry={"type": "bbox", "bbox": [4, 4, 12, 15.5]}),
        dict(feedback_type="incorrect_geometry", detection_index=0, suggested_category_id="C",
             suggested_geometry={"type": "polygon", "points": [{"x": 1, "y": 1}, {"x": 40, "y": 2}, {"x": 20, "y": 30}]}),
        dict(feedback_type="missed_object", suggested_category_id="B",
             suggested_geometry={"type": "bbox", "bbox": [100, 100, 199, 200]}),
        dict(feedback_type="false_detection", detection_index=1, explanation="Background only."),
        dict(feedback_type="other", explanation="The prediction ran on a rotated image."),
    ])
    def test_every_feedback_type(self, db, user, tmp_path, three_cats, api, body):
        cats = {"A": three_cats[0], "B": three_cats[1], "C": three_cats[2]}
        if isinstance(body.get("suggested_category_id"), str):
            body = {**body, "suggested_category_id": cats[body["suggested_category_id"]].category_id}
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        r = _submit(api, pid, **body)
        assert r.status_code == 201, r.text
        assert r.json()["feedback_type"] == body["feedback_type"]

    def test_invalid_submissions_are_rejected(self, db, user, tmp_path, three_cats, api):
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        inactive = Category(class_name="Old", class_code=777, is_active=False)
        db.add(inactive)
        db.commit()
        b = three_cats[1].category_id
        bbox = {"type": "bbox", "bbox": [1, 1, 5, 5]}
        bad = [
            dict(feedback_type="wrong_everything"),
            dict(feedback_type="incorrect_class", suggested_category_id=b),                     # no detection
            dict(feedback_type="incorrect_class", detection_index=2, suggested_category_id=b),  # out of range
            dict(feedback_type="incorrect_class", detection_index=0),                           # no class
            dict(feedback_type="incorrect_class", detection_index=0, suggested_category_id=99999),
            dict(feedback_type="incorrect_class", detection_index=0, suggested_category_id=inactive.category_id),
            dict(feedback_type="incorrect_class", detection_index=0,
                 suggested_category_id=three_cats[0].category_id),                               # same as predicted
            dict(feedback_type="incorrect_geometry", detection_index=0),                        # no geometry
            dict(feedback_type="missed_object", detection_index=0, suggested_category_id=b, suggested_geometry=bbox),
            dict(feedback_type="missed_object", suggested_geometry=bbox),                       # no class
            dict(feedback_type="false_detection", detection_index=0, suggested_category_id=b),
            dict(feedback_type="false_detection", detection_index=0, suggested_geometry=bbox),
            dict(feedback_type="other"),                                                        # no explanation
            dict(feedback_type="other", explanation="  x "),
            dict(feedback_type="other", explanation="bad\x00text here"),
            dict(feedback_type="other", explanation="y" * 2001),
            dict(feedback_type="other", explanation="fine text", unexpected="field"),
            dict(feedback_type="false_detection", detection_index=-1),
        ]
        for body in bad:
            r = _submit(api, pid, **body)
            assert r.status_code == 422, (body, r.status_code, r.text)
        assert db.query(PredictionFeedback).count() == 0

    def test_failed_and_unknown_predictions_cannot_receive_feedback(self, db, api):
        def boom():
            raise RuntimeError("inference failed")
        FakeDetector.hook = boom
        assert _predict(api).status_code == 500
        [failed] = db.query(PredictionRecord).all()
        r = _submit(api, failed.prediction_id, feedback_type="other", explanation="It did not work.")
        assert r.status_code == 409 and "failed prediction" in r.text
        assert _submit(api, "no-such-prediction", feedback_type="other", explanation="Hello there").status_code == 404
        assert db.query(PredictionFeedback).count() == 0

    def test_segmentation_feedback_keeps_the_non_model_confidence(self, db, user, tmp_path, three_cats, api, seg):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        pid = api.post("/api/ai/polygon-click", json={"image_id": img.image_id, "x": 5, "y": 5}).json()["prediction_id"]
        body = _submit(api, pid, feedback_type="incorrect_geometry", detection_index=0,
                       suggested_geometry={"type": "polygon", "points": [{"x": 0, "y": 0}, {"x": 20, "y": 0},
                                                                         {"x": 20, "y": 20}, {"x": 0, "y": 20}]}).json()
        ref = body["prediction_reference"]
        assert ref["confidence_is_model_score"] is False and ref["model_kind"] == "segmentation_assistant"
        assert ref["original_detection"]["confidence"] is None
        assert ref["original_detection"]["reported_confidence"] == 0.95      # kept, labelled as reported only


class TestGeometry:
    @pytest.mark.parametrize("geometry", [
        "not-an-object",
        {"type": "circle", "cx": 1, "cy": 1, "r": 3},
        {"type": "bbox", "bbox": [1, 2, 3]},
        {"type": "bbox", "bbox": [5, 5, 5, 9]},                      # zero width
        {"type": "bbox", "bbox": [9, 5, 2, 9]},                      # x2 < x1
        {"type": "bbox", "bbox": [-1, 0, 5, 5]},
        {"type": "bbox", "bbox": ["1", 0, 5, 5]},
        {"type": "bbox", "bbox": [True, 0, 5, 5]},
        {"type": "bbox", "bbox": [0, 0, 201, 50]},                   # outside the 200x200 image
        {"type": "polygon", "points": [{"x": 1, "y": 1}, {"x": 5, "y": 5}]},
        {"type": "polygon", "points": [{"x": 1, "y": 1}, {"x": 5, "y": 5}, {"x": 9, "y": 9}]},   # zero area
        {"type": "polygon", "points": [{"x": 1, "y": 1}, {"x": 5}, {"x": 9, "y": 9}]},
        {"type": "polygon", "points": [{"x": 1, "y": 1}, {"x": 50, "y": 1}, {"x": 50, "y": 250}]},
        {"type": "polygon", "points": [{"x": i % 100, "y": (i * 7) % 100} for i in range(501)]},
        {"type": "polygon", "points": "1,1 2,2 3,3"},
    ])
    def test_invalid_geometry_is_rejected(self, db, user, tmp_path, three_cats, api, geometry):
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        r = _submit(api, pid, feedback_type="incorrect_geometry", detection_index=0, suggested_geometry=geometry)
        assert r.status_code == 422, r.text
        assert db.query(PredictionFeedback).count() == 0

    def test_non_finite_coordinates_are_rejected(self):
        for v in (float("nan"), float("inf")):
            with pytest.raises(Exception) as e:
                fs.validate_geometry({"type": "bbox", "bbox": [0, 0, v, 5]}, (200, 200))
            assert getattr(e.value, "status_code", None) == 422

    def test_valid_geometry_is_normalised(self):
        assert fs.validate_geometry({"type": "bbox", "bbox": [0, 0, 200, 200]}, (200, 200)) == {
            "type": "bbox", "bbox": [0.0, 0.0, 200.0, 200.0]}
        poly = fs.validate_geometry({"type": "polygon", "points": [{"x": 0, "y": 0}, {"x": 3, "y": 0},
                                                                   {"x": 0, "y": 3}], "extra": 1})
        assert poly == {"type": "polygon", "points": [{"x": 0.0, "y": 0.0}, {"x": 3.0, "y": 0.0},
                                                       {"x": 0.0, "y": 3.0}]}

    def test_unknown_image_size_uses_the_sanity_bound(self, db, api):
        pid = _predict(api).json()["prediction_id"]                         # no image linked
        ok = _submit(api, pid, feedback_type="missed_object", suggested_category_id=None,
                     suggested_geometry={"type": "bbox", "bbox": [0, 0, 5000, 4000]})
        assert ok.status_code == 422                                        # class still required
        cat = Category(class_name="Solo", class_code=55, is_active=True)
        db.add(cat)
        db.commit()
        assert _submit(api, pid, feedback_type="missed_object", suggested_category_id=cat.category_id,
                       suggested_geometry={"type": "bbox", "bbox": [0, 0, 5000, 4000]}).status_code == 201
        assert _submit(api, pid, feedback_type="missed_object", suggested_category_id=cat.category_id,
                       suggested_geometry={"type": "bbox", "bbox": [0, 0, 100001, 4]}).status_code == 422


# ---------------------------------------------------------------------------
# 3-4. Access control and duplicates
# ---------------------------------------------------------------------------

class TestAccessAndDuplicates:
    def test_users_cannot_reach_other_users_predictions_or_feedback(self, db, user, tmp_path, three_cats, api):
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        mine = _submit(api, pid, feedback_type="other", explanation="Looks wrong to me.").json()["feedback_id"]
        other = _other_user(db)
        _as(api, other)
        assert _submit(api, pid, feedback_type="other", explanation="Not my prediction").status_code == 404
        assert api.get(f"/api/ml/feedback/{mine}").status_code == 404                   # existence not leaked
        assert api.get("/api/ml/feedback").json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
        _as(api, user)
        listed = api.get("/api/ml/feedback").json()
        assert [i["feedback_id"] for i in listed["items"]] == [mine]
        assert api.get(f"/api/ml/feedback?status=pending&prediction_id={pid}").json()["total"] == 1
        assert api.get("/api/ml/feedback?status=approved").json()["total"] == 0
        for bad in ("status=done", "feedback_type=nope", "limit=0", "limit=201", "offset=-1"):
            assert api.get(f"/api/ml/feedback?{bad}").status_code == 422

    def test_review_endpoints_require_a_real_administrator(self, db, user, api):
        from app.dependencies.auth import create_access_token, require_admin
        from app.main import app as fastapi_app
        fastapi_app.dependency_overrides.pop(require_admin, None)          # real admin check
        hdr = {"Authorization": f"Bearer {create_access_token(user.user_id, 'user')}"}
        for method, url in (("get", "/api/ml/feedback-review"), ("get", "/api/ml/feedback-review/x"),
                            ("post", "/api/ml/feedback-review/x/approve"),
                            ("post", "/api/ml/feedback-review/x/reject")):
            assert getattr(api, method)(url, headers=hdr).status_code == 403, url
            assert getattr(api, method)(url).status_code == 401, url

    def test_duplicate_rules(self, db, user, tmp_path, three_cats, api, admin):
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        first = _submit(api, pid, feedback_type="false_detection", detection_index=1).json()["feedback_id"]
        dup = _submit(api, pid, feedback_type="false_detection", detection_index=1)
        assert dup.status_code == 409 and first in dup.text
        assert _submit(api, pid, feedback_type="false_detection", detection_index=0).status_code == 201
        assert _submit(api, pid, feedback_type="other", detection_index=1,
                       explanation="Also the box is odd").status_code == 201
        _as_admin(admin)
        assert api.post(f"/api/ml/feedback-review/{first}/reject", json={"reason": "Not a false detection"}).status_code == 200
        _as(api, user)
        again = _submit(api, pid, feedback_type="false_detection", detection_index=1)   # rejected -> may resubmit
        assert again.status_code == 201
        _as_admin(admin)
        api.post(f"/api/ml/feedback-review/{again.json()['feedback_id']}/approve", json={})
        _as(api, user)
        assert _submit(api, pid, feedback_type="false_detection", detection_index=1).status_code == 409
        assert db.query(PredictionFeedback).count() == 4

    def test_unique_index_backstops_racing_submissions(self, db, user, tmp_path, three_cats, api):
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        base = dict(prediction_id=pid, submitted_by=user.user_id, submitter_role="user", environment="test",
                    feedback_type="other", target="prediction", prediction_source="ml_predict",
                    model_kind="deployed_detector", model_attribution="unmanaged_artifact", status="pending")
        db.add(PredictionFeedback(**base))
        db.commit()
        db.add(PredictionFeedback(**base))
        with pytest.raises(Exception):
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# 6-12. Administrator review, lifecycle, safety
# ---------------------------------------------------------------------------

class TestReview:
    def _feedback(self, db, api, user, tmp_path, cats, **body):
        img, pid = _image_prediction(db, api, user, tmp_path, cats[0])
        body = body or dict(feedback_type="incorrect_class", detection_index=0,
                            suggested_category_id=cats[1].category_id, explanation="Should be Cat B")
        r = _submit(api, pid, **body)
        assert r.status_code == 201, r.text
        return img, pid, r.json()["feedback_id"]

    def test_approval_records_the_decision_and_changes_nothing_else(self, db, user, tmp_path, three_cats, api, admin):
        img, pid, fid = self._feedback(db, api, user, tmp_path, three_cats)
        before_img, frozen = _image_state(db, img.image_id), _frozen(_record(db, pid))
        problem_before = tds.user_confirmation_problem(db, db.query(Image).get(img.image_id))
        _as_admin(admin)
        r = api.post(f"/api/ml/feedback-review/{fid}/approve", json={"reason": "Correct, it is Cat B"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "approved" and body["idempotent_replay"] is False
        d = body["decision"]
        assert (d["decision"], d["reason"], d["previous_status"], d["reviewer_id"], d["reviewer_email"]) == (
            "approved", "Correct, it is Cat B", "pending", admin.user_id, admin.email)
        assert d["decided_at"] and body["decision_history"] == [d]
        assert body["prediction"]["prediction_id"] == pid and body["submitted_by"] == user.user_id
        assert _frozen(_record(db, pid)) == frozen                                   # prediction untouched
        assert _image_state(db, img.image_id) == before_img                          # labels/eligibility untouched
        fresh = db.query(Image).get(img.image_id)
        assert fresh.training_sequence is None
        assert tds.user_confirmation_problem(db, fresh) == problem_before
        _as(api, user)
        mine = api.get(f"/api/ml/feedback/{fid}").json()
        assert mine["status"] == "approved" and mine["decision"]["reason"] == "Correct, it is Cat B"
        assert "reviewer_id" not in mine["decision"] and "reviewer_email" not in mine["decision"]

    def test_rejection_requires_a_reason(self, db, user, tmp_path, three_cats, api, admin):
        img, pid, fid = self._feedback(db, api, user, tmp_path, three_cats)
        before_img = _image_state(db, img.image_id)
        _as_admin(admin)
        for body in ({}, {"reason": ""}, {"reason": "  no"}, {"reason": "ok", "extra": 1}):
            assert api.post(f"/api/ml/feedback-review/{fid}/reject", json=body).status_code == 422, body
        assert api.post(f"/api/ml/feedback-review/{fid}/reject").status_code == 422          # no body
        assert _decision_rows(db, fid) == []
        r = api.post(f"/api/ml/feedback-review/{fid}/reject", json={"reason": "The prediction was right"})
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        assert _image_state(db, img.image_id) == before_img
        assert db.query(Image).get(img.image_id).training_sequence is None           # never enters training

    def test_approval_without_body_and_unknown_feedback(self, db, user, tmp_path, three_cats, api, admin):
        _, _, fid = self._feedback(db, api, user, tmp_path, three_cats)
        _as_admin(admin)
        assert api.post("/api/ml/feedback-review/missing/approve").status_code == 404
        r = api.post(f"/api/ml/feedback-review/{fid}/approve")
        assert r.status_code == 200 and r.json()["decision"]["reason"] is None

    def test_submitter_cannot_review_own_feedback(self, db, user, tmp_path, three_cats, api, admin):
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        _as_admin(admin)                                    # administrators may report any visible prediction
        fid = _submit(api, pid, feedback_type="other", explanation="Admin report").json()["feedback_id"]
        r = api.post(f"/api/ml/feedback-review/{fid}/approve", json={})
        assert r.status_code == 403 and "other than its submitter" in r.text
        # the same person through an admins-table account (same e-mail) is not independent either
        twin = Admin(admin_name="Twin", admin_email=admin.email.upper(), hash_password="x")
        db.add(twin)
        db.commit()
        _as_admin(twin)
        assert api.post(f"/api/ml/feedback-review/{fid}/approve", json={}).status_code == 403
        independent = Admin(admin_name="Other", admin_email=f"rev_{uuid.uuid4().hex[:6]}@test.com", hash_password="x")
        db.add(independent)
        db.commit()
        _as_admin(independent)
        r = api.post(f"/api/ml/feedback-review/{fid}/approve", json={})
        assert r.status_code == 200 and r.json()["decision"]["reviewer_id"] == independent.admin_id
        assert r.json()["submitter_role"] == "admin"

    def test_decisions_are_idempotent_and_final(self, db, user, tmp_path, three_cats, api, admin):
        _, _, fid = self._feedback(db, api, user, tmp_path, three_cats)
        _as_admin(admin)
        first = api.post(f"/api/ml/feedback-review/{fid}/approve", json={"reason": "Yes"})
        replay = api.post(f"/api/ml/feedback-review/{fid}/approve", json={"reason": "Different words"})
        assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
        assert replay.json()["decision"] == first.json()["decision"]                  # original kept verbatim
        other = _other_user(db, role="admin")
        _as_admin(other)
        assert api.post(f"/api/ml/feedback-review/{fid}/approve", json={}).json()["idempotent_replay"] is True
        conflict = api.post(f"/api/ml/feedback-review/{fid}/reject", json={"reason": "Changed my mind"})
        assert conflict.status_code == 409 and "already been approved" in conflict.text
        rows = _decision_rows(db, fid)
        assert len(rows) == 1 and rows[0].reviewer_id == admin.user_id and rows[0].reason == "Yes"
        assert db.query(PredictionFeedback).get(fid).status == "approved"

    def test_concurrent_decisions_record_exactly_one(self, db, Session, user, tmp_path, three_cats, api, admin):
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("row-lock concurrency is verified on PostgreSQL")
        for outcomes in (("approved", "rejected"), ("approved", "approved"), ("rejected", "approved")):
            _as(api, user)
            _, _, fid = self._feedback(db, api, user, tmp_path, three_cats)
            reviewers = [SimpleNamespace(user_id=str(uuid.uuid4()), email=f"r{i}@test.com", role="admin")
                         for i in range(2)]
            gate, results = threading.Barrier(2), [None, None]

            def run(i):
                s = Session()
                try:
                    gate.wait()
                    row, replay = fs.decide(s, reviewers[i], fid, outcomes[i], "Concurrent review")
                    results[i] = ("ok", row.decision, replay)
                except Exception as exc:                      # HTTPException from the service
                    results[i] = ("err", getattr(exc, "status_code", type(exc).__name__), None)
                finally:
                    s.close()

            threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
            [t.start() for t in threads]
            [t.join(30) for t in threads]
            rows = _decision_rows(db, fid)
            assert len(rows) == 1, results
            winner = rows[0].decision
            assert db.query(PredictionFeedback).get(fid).status == winner
            fresh = [r for r in results if r[0] == "ok" and r[2] is False]
            assert len(fresh) == 1 and fresh[0][1] == winner, results
            loser = [r for r in results if r not in fresh][0]
            if outcomes[0] == outcomes[1]:
                assert loser == ("ok", winner, True), results          # idempotent replay
            else:
                assert loser == ("err", 409, None), results            # conflicting decision refused

    def test_queue_filters_detail_and_pagination(self, db, user, tmp_path, three_cats, api, admin):
        ids = [self._feedback(db, api, user, tmp_path, three_cats)[2] for _ in range(3)]
        _, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
        other_type = _submit(api, pid, feedback_type="other", explanation="Something else").json()["feedback_id"]
        _as_admin(admin)
        api.post(f"/api/ml/feedback-review/{ids[0]}/reject", json={"reason": "Not convincing"})
        q = lambda s: api.get(f"/api/ml/feedback-review?{s}").json()      # noqa: E731
        assert q("")["total"] == 4
        assert {i["feedback_id"] for i in q("status=pending")["items"]} == {ids[1], ids[2], other_type}
        assert [i["feedback_id"] for i in q("status=rejected")["items"]] == [ids[0]]
        assert [i["feedback_id"] for i in q("feedback_type=other")["items"]] == [other_type]
        assert q(f"user_id={user.user_id}")["total"] == 4 and q("user_id=nobody")["total"] == 0
        assert q("submitted_from=2000-01-01T00:00:00Z&submitted_to=2999-01-01T00:00:00Z")["total"] == 4
        assert q("submitted_from=2999-01-01T00:00:00Z")["total"] == 0
        assert q("submitted_to=2000-01-01T00:00:00")["total"] == 0
        page = q("limit=2&offset=2&order=oldest")
        assert len(page["items"]) == 2 and page["total"] == 4
        assert all("submitted_by" in i for i in q("")["items"])
        for bad in ("status=done", "feedback_type=x", "submitted_from=yesterday", "order=random", "limit=0"):
            assert api.get(f"/api/ml/feedback-review?{bad}").status_code == 422, bad
        detail = api.get(f"/api/ml/feedback-review/{ids[0]}").json()
        assert detail["prediction"]["model"]["kind"] == "deployed_detector"
        assert detail["decision_history"][0]["decision"] == "rejected"
        assert api.get("/api/ml/feedback-review/unknown").status_code == 404

    def test_responses_never_contain_paths(self, db, user, tmp_path, three_cats, api, admin):
        _, _, fid = self._feedback(db, api, user, tmp_path, three_cats)
        _as_admin(admin)
        for payload in (api.get(f"/api/ml/feedback-review/{fid}").text, api.get("/api/ml/feedback-review").text):
            assert str(tmp_path) not in payload and str(tmp_path).replace("\\", "\\\\") not in payload
            assert ":\\\\" not in payload and "/tmp/" not in payload


# ---------------------------------------------------------------------------
# 11. Immutability (ORM + PostgreSQL)
# ---------------------------------------------------------------------------

class TestImmutability:
    def _decided(self, db, api, user, tmp_path, cats, admin):
        _, pid = _image_prediction(db, api, user, tmp_path, cats[0])
        fid = _submit(api, pid, feedback_type="other", explanation="Check this one").json()["feedback_id"]
        _as_admin(admin)
        api.post(f"/api/ml/feedback-review/{fid}/approve", json={})
        _as(api, user)
        return pid, fid

    def test_orm_refuses_changes(self, db, user, tmp_path, three_cats, api, admin):
        pid, fid = self._decided(db, api, user, tmp_path, three_cats, admin)
        for mutate in (lambda f: setattr(f, "explanation", "rewritten"),
                       lambda f: setattr(f, "status", "rejected"),
                       lambda f: setattr(f, "status", "pending")):
            db.expire_all()
            mutate(db.query(PredictionFeedback).get(fid))
            with pytest.raises(FeedbackImmutableError):
                db.commit()
            db.rollback()
        for obj in (lambda: db.query(PredictionFeedback).get(fid), lambda: _decision_rows(db, fid)[0]):
            db.delete(obj())
            with pytest.raises(FeedbackImmutableError):
                db.commit()
            db.rollback()
        d = _decision_rows(db, fid)[0]
        d.reason = "edited"
        with pytest.raises(FeedbackImmutableError):
            db.commit()
        db.rollback()
        assert db.query(PredictionFeedback).get(fid).explanation == "Check this one"

    def test_database_enforces_the_lifecycle(self, db, user, tmp_path, three_cats, api, admin):
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL triggers")
        pid, decided = self._decided(db, api, user, tmp_path, three_cats, admin)
        pending = _submit(api, pid, feedback_type="other", detection_index=0,
                          explanation="Second report").json()["feedback_id"]
        refused = [
            ("UPDATE prediction_feedback SET status = 'approved' WHERE feedback_id = :p", pending,
             "requires a recorded decision"),
            ("UPDATE prediction_feedback SET explanation = 'forged' WHERE feedback_id = :p", pending, "immutable"),
            ("UPDATE prediction_feedback SET status = 'rejected' WHERE feedback_id = :p", decided,
             "only move from pending"),
            ("DELETE FROM prediction_feedback WHERE feedback_id = :p", pending, "cannot be deleted"),
            ("UPDATE prediction_feedback_decisions SET decision = 'rejected' WHERE feedback_id = :p", decided,
             "append-only"),
            ("DELETE FROM prediction_feedback_decisions WHERE feedback_id = :p", decided, "append-only"),
            ("INSERT INTO prediction_feedback_decisions (decision_id, feedback_id, decision, reviewer_id, "
             "previous_status, decided_at) VALUES ('d-self', :p, 'approved', :u, 'pending', now())", pending,
             "independent reviewer"),
            ("INSERT INTO prediction_feedback_decisions (decision_id, feedback_id, decision, reviewer_id, "
             "previous_status, decided_at) VALUES ('d-two', :p, 'rejected', 'someone', 'pending', now())", decided,
             "already been decided"),
            ("INSERT INTO prediction_feedback_decisions (decision_id, feedback_id, decision, reviewer_id, "
             "previous_status, decided_at) VALUES ('d-bad', :p, 'maybe', 'someone', 'pending', now())", pending,
             "invalid feedback decision"),
            ("INSERT INTO prediction_feedback (feedback_id, prediction_id, submitted_by, submitter_role, "
             "submitted_at, environment, feedback_type, target, prediction_source, model_kind, model_attribution, "
             "status) SELECT 'f-new', prediction_id, :u, 'user', now(), 'test', 'other', 'x', 'ml_predict', "
             "'deployed_detector', 'unverified', 'approved' FROM prediction_feedback WHERE feedback_id = :p",
             pending, "submitted as pending"),
            ("DELETE FROM prediction_records WHERE prediction_id = (SELECT prediction_id FROM prediction_feedback "
             "WHERE feedback_id = :p)", pending, "append-only"),
        ]
        for sql, target, message in refused:
            with pytest.raises(Exception, match=message):
                db.execute(text(sql), {"p": target, "u": user.user_id})
            db.rollback()
        assert db.query(PredictionFeedback).get(pending).status == "pending"
        assert len(_decision_rows(db, decided)) == 1


# ---------------------------------------------------------------------------
# 7, 13. Frozen snapshots, deployments and A6.1 contracts untouched
# ---------------------------------------------------------------------------

def test_feedback_never_alters_snapshots_or_eligibility(db, user, tmp_path, three_cats, api, admin):
    a, b, c = three_cats
    _set_threshold(db, 3)
    _complete_many(db, user, [(a, 1), (b, 1), (c, 1)], tmp_path)
    assert db.query(TrainingSnapshot).count() == 1
    images = db.query(Image).all()
    states = {i.image_id: _image_state(db, i.image_id) for i in images}
    before = (_snapshot_digest(db), db.query(TrainingSnapshot).count())
    fids = []
    for img in images:
        pid = _predict(api, image_id=img.image_id).json()["prediction_id"]
        fids.append(_submit(api, pid, feedback_type="incorrect_class", detection_index=1,
                            suggested_category_id=a.category_id).json()["feedback_id"])
    _as_admin(admin)
    api.post(f"/api/ml/feedback-review/{fids[0]}/approve", json={})
    api.post(f"/api/ml/feedback-review/{fids[1]}/reject", json={"reason": "Prediction was right"})
    assert (_snapshot_digest(db), db.query(TrainingSnapshot).count()) == before
    for img in images:
        after = _image_state(db, img.image_id)
        assert after[1:] == states[img.image_id][1:]                    # annotations + label bytes
        changed = {k for k in after[0] if after[0][k] != states[img.image_id][0][k]}
        assert changed <= {"ai_suggested_at"}, changed                  # A6.0 marker from /ml/predict only


def test_feedback_does_not_touch_deployment_history(db, Session, cand, deploy_env, api, user, admin):
    mv, _ = cand
    _approve(db, Session, mv)
    mds.activate_model_version(db, mv.model_id, ADMIN)
    snap = lambda: (sorted((d.deployment_id, d.status, d.model_id) for d in db.query(ModelDeployment).all()),  # noqa: E731
                    db.query(DeploymentEvent).count())
    before = snap()
    pid = _predict(api).json()["prediction_id"]
    assert _record(db, pid).attribution == "active_deployment"
    fid = _submit(api, pid, feedback_type="false_detection", detection_index=0).json()["feedback_id"]
    _as_admin(admin)
    assert api.post(f"/api/ml/feedback-review/{fid}/approve", json={}).status_code == 200
    db.expire_all()
    assert snap() == before


def test_a61_contracts_unchanged(db, api):
    r = _predict(api)
    assert set(r.json()) == {"predictions", "count", "prediction_id"}
    listed = api.get("/api/ml/predictions").json()
    assert set(listed) == {"items", "total", "limit", "offset"}
    assert "feedback" not in listed["items"][0]


@pytest.mark.skipif("test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
                    reason="real-JWT access test only runs against an isolated *test* database")
@pytest.mark.parametrize("method,url", [("get", "/api/ml/feedback"), ("get", "/api/ml/feedback/x"),
                                        ("post", "/api/ml/predictions/x/feedback"),
                                        ("get", "/api/ml/feedback-review"),
                                        ("post", "/api/ml/feedback-review/x/approve")])
def test_feedback_endpoints_require_authentication(client, method, url):
    assert getattr(client, method)(url).status_code == 401
