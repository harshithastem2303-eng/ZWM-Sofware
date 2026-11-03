"""
ZWM v1.1.0 Block A6.3 — immutable label revisions and governed feedback corrections.

Isolation as in A1-A6.2: own database (SQLite per test or the throwaway PostgreSQL
database from ZWM_A1_TEST_DATABASE_URL), synthetic images/labels under tmp_path,
ultralytics.YOLO replaced by the A6.1 in-process fake (no real load, inference or
download). Concurrency and trigger tests run on PostgreSQL only.
"""
import threading
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.config import settings
from app.models.annotation import Annotation
from app.models.category import Category
from app.models.feedback import FeedbackDecision, PredictionFeedback
from app.models.image import Image
from app.models.label_review import LabelReview
from app.models.label_revision import (
    LabelRevision,
    LabelRevisionEvent,
    LabelRevisionHead,
    LabelRevisionImmutableError,
)
from app.models.prediction import PredictionRecord
from app.models.training import TrainingSnapshot
from app.models.user import Admin
from app.services import feedback_service as fs
from app.services import label_revision_service as lrs
from app.services import training_dataset_service as tds
from app.services.annotation_converter import annotation_to_yolo_line
from test_a2_training_pipeline import no_real_training, worker  # noqa: F401
from test_a3_candidate_evaluation import eval_dirs  # noqa: F401
from test_a4_model_deployment import ADMIN, _approve, cand, deploy_env  # noqa: F401
from test_a60_label_review import _labelled, _snapshot_digest
from test_a61_prediction_provenance import (  # noqa: F401
    FakeDetector, _as, _frozen, _jpeg, _other_user, _predict, _record, fake_detector,
)
from test_a62_prediction_feedback import _as_admin, _image_prediction, _image_state, _submit
from test_training_foundation import (  # noqa: F401
    Session, api, db, engine, queued, three_cats, user, _set_threshold,
)

REASON = "Apply the approved correction"


def _pg(db):
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("verified on PostgreSQL (row locks / triggers)")


def _rows(db, cls, **flt):
    db.expire_all()
    return [_frozen_row(r) for r in db.query(cls).filter_by(**flt).all()]


def _frozen_row(row):
    return {c.name: getattr(row, c.name) for c in type(row).__table__.columns}


def _all_frozen(db):
    """Prediction, feedback, decision and revision evidence (for before/after equality)."""
    db.expire_all()
    out = {}
    for cls, key in ((PredictionRecord, "prediction_id"), (PredictionFeedback, "feedback_id"),
                     (FeedbackDecision, "decision_id"), (LabelReview, "review_id")):
        out[cls.__tablename__] = sorted((_frozen_row(r) for r in db.query(cls).all()), key=lambda r: r[key])
    return out


def _revs(db, image_id):
    db.expire_all()
    return db.query(LabelRevision).filter(LabelRevision.image_id == image_id).order_by(
        LabelRevision.revision_number).all()


def _ann(db, image_id):
    db.expire_all()
    return db.query(Annotation).filter(Annotation.image_id == image_id).one()


@pytest.fixture()
def admins(db):
    """r1 decides feedback, r2 creates/activates revisions, r3 reviews revisions."""
    return SimpleNamespace(r1=_other_user(db, role="admin"), r2=_other_user(db, role="admin"),
                           r3=_other_user(db, role="admin"))


@pytest.fixture()
def case(db, api, user, tmp_path, three_cats, admins):
    """The owner's permanent (not finalized) 200x200 image, one human annotation, an ml_predict
    prediction with two detections (Cat A @ [1.5,2,30.25,40], Cat C @ [5,5,9,9])."""
    img, pid = _image_prediction(db, api, user, tmp_path, three_cats[0])
    return SimpleNamespace(img=img, pid=pid, cats=three_cats, a=admins, owner=user,
                           ann_id=_ann(db, img.image_id).annotation_id)


def _feedback(api, db, case, decision="approved", **body):
    _as(api, case.owner)
    r = _submit(api, case.pid, **body)
    assert r.status_code == 201, r.text
    fid = r.json()["feedback_id"]
    if decision:
        fs.decide(db, case.a.r1, fid, decision, "Reviewed by an administrator")
    return fid


def _wrong_class(api, db, case, decision="approved"):
    return _feedback(api, db, case, decision, feedback_type="incorrect_class", detection_index=0,
                     suggested_category_id=case.cats[1].category_id)


def _create(api, who, fid, **body):
    _as_admin(who)
    body.setdefault("reason", REASON)
    return api.post(f"/api/label-revisions/from-feedback/{fid}", json=body)


def _post(api, who, rid, action, **body):
    _as_admin(who)
    return api.post(f"/api/label-revisions/{rid}/{action}", json=body or None)


def _approved_revision(api, db, case, fid=None, **create):
    fid = fid or _wrong_class(api, db, case)
    create.setdefault("target_object_key", case.ann_id)
    r = _create(api, case.a.r2, fid, **create)
    assert r.status_code == 201, r.text
    rid = r.json()["revision_id"]
    assert _post(api, case.a.r2, rid, "submit").status_code == 200
    r = _post(api, case.a.r3, rid, "approve", reason="Correct")
    assert r.status_code == 200, r.text
    return rid


# ---------------------------------------------------------------------------
# 1-4. Revisions, complete contents, deterministic hashes
# ---------------------------------------------------------------------------

class TestRevisions:
    def test_first_revision_records_the_complete_current_label(self, db, api, case):
        _as(api, case.owner)
        r = api.post(f"/api/label-revisions/image/{case.img.image_id}/capture", json={"reason": "Before review"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert (body["revision_number"], body["source"], body["status"], body["is_active"]) == (
            1, "human_annotation", "recorded", True)
        assert body["parent_revision_id"] is None and body["integrity_ok"] is True
        assert "created_by_email" not in body and "created_by" not in body          # admin-only
        ann = _ann(db, case.img.image_id)
        [obj] = body["contents"]["objects"]
        assert (obj["key"], obj["category_id"], obj["annotation_type"], obj["label_data"], obj["ai_generated"],
                obj["annotated_by"], obj["class_name"], obj["yolo_class_index"]) == (
            ann.annotation_id, ann.category_id, ann.annotation_type, ann.label_data_json, False,
            case.owner.user_id, "Cat A", case.cats[0].yolo_class_index)
        assert body["contents"]["image"] == {"width": 200, "height": 200}
        assert body["hashes"]["annotation_fingerprint"] == tds.annotation_fingerprint(db, case.img.image_id)
        img = db.query(Image).get(case.img.image_id)
        assert body["installed_label_text"].encode() == open(img.yolo_txt_path, "rb").read()   # byte-exact
        assert body["base"]["installed_label_sha256"] == tds.file_sha256(img.yolo_txt_path)
        assert body["class_map"] == tds.get_class_map(db)
        again = api.post(f"/api/label-revisions/image/{case.img.image_id}/capture")
        assert again.status_code == 200 and again.json()["revision_id"] == body["revision_id"]
        assert again.json()["idempotent_replay"] is True and len(_revs(db, case.img.image_id)) == 1

    def test_subsequent_revision_keeps_the_earlier_one_unchanged(self, db, api, case):
        _as(api, case.owner)
        first = api.post(f"/api/label-revisions/image/{case.img.image_id}/capture").json()
        frozen = _rows(db, LabelRevision, revision_id=first["revision_id"])
        db.add(Annotation(image_id=case.img.image_id, category_id=case.cats[2].category_id,
                          annotated_by=case.owner.user_id, annotation_type="polygon",
                          label_data_json={"points": [{"x": 1, "y": 1}, {"x": 50, "y": 1}, {"x": 25, "y": 40}]},
                          image_width=200, image_height=200))
        db.commit()
        listing = api.get(f"/api/label-revisions/image/{case.img.image_id}").json()
        assert listing["current"]["in_sync_with_annotations"] is False
        second = api.post(f"/api/label-revisions/image/{case.img.image_id}/capture").json()
        assert second["revision_number"] == 2 and second["parent_revision_id"] == first["revision_id"]
        assert second["object_count"] == 2 and len(second["comparison"]["added"]) == 1
        assert _rows(db, LabelRevision, revision_id=first["revision_id"]) == frozen
        listing = api.get(f"/api/label-revisions/image/{case.img.image_id}").json()
        assert [i["revision_number"] for i in listing["items"]] == [2, 1]
        assert [i["is_active"] for i in listing["items"]] == [True, False]
        assert listing["current"] == {**listing["current"], "revision_id": second["revision_id"],
                                      "in_sync_with_annotations": True}

    def test_hashes_are_canonical_and_deterministic(self, db, api, case):
        _as(api, case.owner)
        rid = api.post(f"/api/label-revisions/image/{case.img.image_id}/capture").json()["revision_id"]
        rev = db.query(LabelRevision).get(rid)
        assert lrs._verify_hashes(rev) is None
        shuffled = {**rev.contents, "objects": list(reversed(rev.contents["objects"]))}
        assert lrs.content_sha256(shuffled) == rev.content_sha256
        assert lrs.label_text(shuffled) == rev.label_text
        ann = _ann(db, case.img.image_id)
        expected = annotation_to_yolo_line(ann.annotation_type, ann.label_data_json, 200, 200,
                                           case.cats[0].yolo_class_index) + "\n"
        assert rev.label_text == expected and rev.label_sha256 == lrs._sha(expected)
        assert rev.class_map_sha256 == lrs.class_map_sha256(tds.get_class_map(db))
        tampered = SimpleNamespace(**{c.name: getattr(rev, c.name) for c in LabelRevision.__table__.columns})
        tampered.contents = {**rev.contents, "objects": [{**rev.contents["objects"][0], "category_id": 999}]}
        assert lrs._verify_hashes(tampered) == "content_sha256"


# ---------------------------------------------------------------------------
# 5-9. Feedback -> revision
# ---------------------------------------------------------------------------

class TestFromFeedback:
    def test_approved_feedback_becomes_a_draft_revision(self, db, api, case):
        fid = _wrong_class(api, db, case)
        before = _all_frozen(db)
        rows_before = _image_state(db, case.img.image_id)
        r = _create(api, case.a.r2, fid, target_object_key=case.ann_id)
        assert r.status_code == 201, r.text
        body = r.json()
        assert (body["source"], body["status"], body["revision_number"], body["is_active"]) == (
            "approved_feedback", "draft", 2, False)
        decision = db.query(FeedbackDecision).filter_by(feedback_id=fid).one()
        assert (body["feedback_id"], body["prediction_id"], body["feedback_decision_id"]) == (
            fid, case.pid, decision.decision_id)
        assert body["correction"]["action"] == "modify" and body["correction"]["object_key"] == case.ann_id
        [obj] = body["contents"]["objects"]
        assert (obj["category_id"], obj["class_name"], obj["annotated_by"]) == (
            case.cats[1].category_id, "Cat B", case.owner.user_id)
        assert body["comparison"]["changed"][0]["before"]["category_id"] == case.cats[0].category_id
        base = db.query(LabelRevision).get(body["parent_revision_id"])
        assert base.source == "human_annotation" and base.revision_number == 1     # captured first
        assert body["source_feedback"]["feedback_id"] == fid
        assert body["source_feedback"]["prediction"]["prediction_id"] == case.pid
        assert body["created_by"] == case.a.r2.user_id and body["created_by_email"] == case.a.r2.email
        assert _all_frozen(db) == before                                  # A6.1 / A6.2 evidence untouched
        assert _image_state(db, case.img.image_id) == rows_before         # labels untouched until activation

    @pytest.mark.parametrize("kind", ["add_from_prediction", "missed_object", "false_detection", "geometry"])
    def test_every_structured_correction(self, db, api, case, kind):
        c = case
        if kind == "add_from_prediction":
            fid, create = _wrong_class(api, db, c), {}
        elif kind == "missed_object":
            fid = _feedback(api, db, c, feedback_type="missed_object", suggested_category_id=c.cats[2].category_id,
                            suggested_geometry={"type": "bbox", "bbox": [120, 130, 190, 199]})
            create = {}
        elif kind == "false_detection":
            fid = _feedback(api, db, c, feedback_type="false_detection", detection_index=1)
            db.add(Annotation(image_id=c.img.image_id, category_id=c.cats[2].category_id, ai_generated=True,
                              annotated_by=c.owner.user_id, annotation_type="rectangle",
                              label_data_json={"points": [{"x": 5, "y": 5}, {"x": 9, "y": 9}]}))
            db.commit()
            extra = [a for a in db.query(Annotation).filter_by(image_id=c.img.image_id) if a.ai_generated][0]
            create = {"target_object_key": extra.annotation_id}
        else:
            poly = {"type": "polygon", "points": [{"x": 10, "y": 20}, {"x": 120, "y": 20}, {"x": 60, "y": 150}]}
            fid = _feedback(api, db, c, feedback_type="incorrect_geometry", detection_index=0,
                            suggested_geometry=poly)
            create = {"target_object_key": c.ann_id}
        r = _create(api, c.a.r2, fid, **create)
        assert r.status_code == 201, r.text
        body = r.json()
        objs = {o["key"]: o for o in body["contents"]["objects"]}
        cmp = body["comparison"]
        if kind == "add_from_prediction":
            [new] = cmp["added"]
            assert new["label_data"] == {"points": [{"x": 1.5, "y": 2.0}, {"x": 30.25, "y": 40.0}]}
            assert new["ai_generated"] is True and new["class_name"] == "Cat B"    # geometry came from the AI
        elif kind == "missed_object":
            [new] = cmp["added"]
            assert new["ai_generated"] is False and new["annotation_type"] == "rectangle"
            assert new["annotated_by"] == c.owner.user_id
        elif kind == "false_detection":
            assert [o["key"] for o in cmp["removed"]] == [create["target_object_key"]] and list(objs) == [c.ann_id]
        else:
            assert objs[c.ann_id]["annotation_type"] == "polygon" and objs[c.ann_id]["ai_generated"] is False
            assert objs[c.ann_id]["category_id"] == c.cats[0].category_id           # class unchanged

    @pytest.mark.parametrize("decision", [None, "rejected"])
    def test_unapproved_feedback_is_refused(self, db, api, case, decision):
        fid = _wrong_class(api, db, case, decision=decision)
        r = _create(api, case.a.r2, fid)
        assert r.status_code == 409 and "approved administrator decision" in r.text
        assert db.query(LabelRevision).count() == 0
        assert _create(api, case.a.r2, "no-such-feedback").status_code == 404

    def test_other_feedback_and_no_change_are_refused(self, db, api, case):
        fid = _feedback(api, db, case, feedback_type="other", explanation="Rotated image")
        assert _create(api, case.a.r2, fid).status_code == 409
        fid = _feedback(api, db, case, feedback_type="false_detection", detection_index=0)
        r = _create(api, case.a.r2, fid)                                   # nothing to remove
        assert r.status_code == 422 and "target_object_key" in r.text
        r = _create(api, case.a.r2, fid, target_object_key=case.ann_id)  # would empty the label
        assert r.status_code == 409 and "without any labelled object" in r.text
        assert db.query(LabelRevision).filter(LabelRevision.source != "human_annotation").count() == 0

    def test_feedback_is_applied_at_most_once(self, db, api, case):
        fid = _wrong_class(api, db, case)
        first = _create(api, case.a.r2, fid, target_object_key=case.ann_id)
        replay = _create(api, case.a.r3, fid, target_object_key=case.ann_id)
        assert replay.status_code == 200 and replay.json()["idempotent_replay"] is True
        assert replay.json()["revision_id"] == first.json()["revision_id"]
        other = _create(api, case.a.r2, fid)                               # different application
        assert other.status_code == 409 and "already been applied" in other.text
        assert db.query(LabelRevision).filter_by(feedback_id=fid).count() == 1
        assert db.query(LabelRevision).count() == 2                         # + the one recorded capture

    def test_invalid_category_and_geometry_are_refused(self, db, api, case):
        fid = _wrong_class(api, db, case)
        assert _create(api, case.a.r2, fid, target_object_key="not-an-object").status_code == 422
        assert _create(api, case.a.r2, fid, category_id=case.cats[2].category_id).status_code == 422
        cat = db.query(Category).get(case.cats[1].category_id)
        cat.is_active = False
        db.commit()
        r = _create(api, case.a.r2, fid, target_object_key=case.ann_id)
        assert r.status_code == 409 and "inactive" in r.text
        cat.is_active = True
        db.commit()
        FakeDetector.detections = [(0, 0.9, [150.0, 150.0, 260.0, 190.0])]   # outside the 200x200 image
        _as(api, case.owner)
        pid = _predict(api, image_id=case.img.image_id).json()["prediction_id"]
        r = _submit(api, pid, feedback_type="incorrect_class", detection_index=0,
                    suggested_category_id=case.cats[1].category_id)
        fs.decide(db, case.a.r1, r.json()["feedback_id"], "approved", "Approved")
        r = _create(api, case.a.r2, r.json()["feedback_id"])
        assert r.status_code == 422 and "outside the image" in r.text
        assert db.query(LabelRevision).filter(LabelRevision.source != "human_annotation").count() == 0

    def test_prediction_without_image_and_missing_image_are_blocked(self, db, api, case):
        _as(api, case.owner)
        pid = _predict(api).json()["prediction_id"]                        # no image association
        r = _submit(api, pid, feedback_type="incorrect_class", detection_index=0,
                    suggested_category_id=case.cats[1].category_id)
        fs.decide(db, case.a.r1, r.json()["feedback_id"], "approved", "Approved")
        r = _create(api, case.a.r2, r.json()["feedback_id"])
        assert r.status_code == 409 and "no stored image" in r.text
        fid = _wrong_class(api, db, case)
        img = db.query(Image).get(case.img.image_id)
        db.delete(img)                                                      # not eligible: deletion allowed
        db.commit()
        r = _create(api, case.a.r2, fid)
        assert r.status_code == 409 and "image no longer exists" in r.text
        assert db.query(LabelRevision).count() == 0


# ---------------------------------------------------------------------------
# 10-11. Authorization and independent review
# ---------------------------------------------------------------------------

class TestAuthorization:
    def test_only_owner_and_admins_can_read(self, db, api, case):
        rid = _approved_revision(api, db, case)
        stranger = _other_user(db)
        _as(api, stranger)
        for url in (f"/api/label-revisions/image/{case.img.image_id}",
                    f"/api/label-revisions/image/{case.img.image_id}/current", f"/api/label-revisions/{rid}"):
            assert api.get(url).status_code == 404, url
        assert api.post(f"/api/label-revisions/image/{case.img.image_id}/capture").status_code == 404
        _as(api, case.owner)
        own = api.get(f"/api/label-revisions/{rid}").json()
        assert own["status"] == "approved" and "created_by_email" not in own
        assert set(own["source_feedback"]) == {"feedback_id", "feedback_type", "status", "prediction_id"}
        assert all("actor_email" not in e and "actor_id" not in e for e in own["events"])
        text_ = str(own)
        assert settings.UPLOAD_FOLDER not in text_ and ":\\" not in text_       # no filesystem paths

    def test_non_admins_cannot_change_revisions(self, db, api, case):
        fid = _wrong_class(api, db, case)
        _as_admin(case.owner)                                               # the dependency lets a user through
        r = api.post(f"/api/label-revisions/from-feedback/{fid}", json={"reason": REASON})
        assert r.status_code == 403
        rid = _create(api, case.a.r2, fid, target_object_key=case.ann_id).json()["revision_id"]
        _as_admin(case.owner)
        for action in ("submit", "approve", "activate"):
            assert api.post(f"/api/label-revisions/{rid}/{action}").status_code == 403, action
        assert api.get("/api/label-revisions/review-queue").status_code in (403, 200)  # require_admin overridden

    def test_review_must_be_independent(self, db, api, case):
        fid = _wrong_class(api, db, case)
        rid = _create(api, case.a.r2, fid, target_object_key=case.ann_id).json()["revision_id"]
        assert _post(api, case.a.r3, rid, "approve").status_code == 409          # still a draft
        assert _post(api, case.a.r2, rid, "submit").status_code == 200
        assert _post(api, case.a.r2, rid, "submit").json()["idempotent_replay"] is True
        assert _post(api, case.a.r2, rid, "approve").status_code == 403          # its creator
        twin = Admin(admin_name="Twin", admin_email=case.a.r2.email, hash_password="x")
        db.add(twin)
        db.commit()
        assert _post(api, twin, rid, "approve").status_code == 403               # same person, admin account
        assert _post(api, case.a.r3, rid, "reject").status_code == 422           # reason required
        r = _post(api, case.a.r3, rid, "approve", reason="Looks right")
        assert r.status_code == 200 and r.json()["status"] == "approved" and r.json()["idempotent_replay"] is False
        assert _post(api, case.a.r3, rid, "approve").json()["idempotent_replay"] is True
        r = _post(api, case.a.r1, rid, "reject", reason="Changed my mind")
        assert r.status_code == 409 and "already been approved" in r.text
        decisions = db.query(LabelRevisionEvent).filter(LabelRevisionEvent.revision_id == rid,
                                                        LabelRevisionEvent.event.in_(("approved", "rejected")))
        assert [(e.event, e.actor_id) for e in decisions] == [("approved", case.a.r3.user_id)]

    def test_admin_accounts_can_run_the_workflow_and_read_any_image(self, db, api, case):
        creator = Admin(admin_name="Creator", admin_email="creator_a63@example.com", hash_password="x")
        reviewer = Admin(admin_name="Reviewer", admin_email="reviewer_a63@example.com", hash_password="x")
        db.add_all([creator, reviewer])
        db.commit()
        fid = _wrong_class(api, db, case)
        rid = _create(api, creator, fid, target_object_key=case.ann_id).json()["revision_id"]
        assert _post(api, creator, rid, "submit").status_code == 200
        assert _post(api, creator, rid, "approve").status_code == 403
        assert _post(api, reviewer, rid, "approve").json()["status"] == "approved"
        _as_admin(reviewer)
        hist = api.get(f"/api/label-revisions/admin/image/{case.img.image_id}").json()
        assert [i["status"] for i in hist["items"]] == ["approved", "recorded"]
        assert hist["annotations"] == [{"key": case.ann_id, "category_id": case.cats[0].category_id,
                                        "class_name": "Cat A", "annotation_type": "rectangle", "ai_generated": False}]
        assert hist["training_locked"] is False
        one = api.get(f"/api/label-revisions/admin/revision/{rid}").json()
        assert one["created_by"] == creator.admin_id and one["events"][-1]["actor_email"] == reviewer.admin_email
        assert api.get("/api/label-revisions/admin/revision/nope").status_code == 404

    def test_rejected_revision_can_never_become_active(self, db, api, case):
        fid = _wrong_class(api, db, case)
        rid = _create(api, case.a.r2, fid, target_object_key=case.ann_id).json()["revision_id"]
        _post(api, case.a.r2, rid, "submit")
        assert _post(api, case.a.r3, rid, "reject", reason="Wrong class").json()["status"] == "rejected"
        before = _image_state(db, case.img.image_id)
        r = _post(api, case.a.r2, rid, "activate")
        assert r.status_code == 409 and "approved" in r.text
        assert _image_state(db, case.img.image_id) == before
        assert db.query(Image).get(case.img.image_id).training_sequence is None


# ---------------------------------------------------------------------------
# 15-18. Activation, rollback, preservation, snapshots, A6.0 compatibility
# ---------------------------------------------------------------------------

class TestActivation:
    def test_activation_installs_the_revision_and_awaits_a60_review(self, db, api, case):
        original = _rows(db, Annotation, image_id=case.img.image_id)
        img = db.query(Image).get(case.img.image_id)
        old_label = open(img.yolo_txt_path, "rb").read()
        rid = _approved_revision(api, db, case)
        evidence = _all_frozen(db)
        r = _post(api, case.a.r2, rid, "activate")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["finalize"] == {"attempted": True, "finalized": True, "reason": None}
        assert body["active"] and body["label_finalized"] and body["awaiting_label_review"]
        assert body["training_eligible"] is False                                # never by activation itself
        rev = db.query(LabelRevision).get(rid)
        ann = _ann(db, case.img.image_id)
        assert ann.annotation_id == case.ann_id and ann.category_id == case.cats[1].category_id
        assert tds.annotation_fingerprint(db, case.img.image_id) == rev.annotation_fingerprint
        img = db.query(Image).get(case.img.image_id)
        new_label = open(img.yolo_txt_path).read()
        assert new_label == rev.label_text and new_label.encode() != old_label
        assert img.label_sha256 == tds.file_sha256(img.yolo_txt_path)
        assert db.query(LabelRevisionHead).get(case.img.image_id).revision_id == rid
        base = db.query(LabelRevision).get(rev.parent_revision_id)
        assert [{k: v for k, v in o.items() if k in ("key", "category_id", "label_data")}
                for o in base.contents["objects"]] == [
            {"key": a["annotation_id"], "category_id": a["category_id"], "label_data": a["label_data_json"]}
            for a in original]                                                   # original label preserved
        assert base.installed_label_text.encode() == old_label
        assert _all_frozen(db) == evidence                                       # predictions/feedback untouched
        state = tds.label_review_state(db, img)
        assert state["requires_review"] and state["review_reason"] == "ai_suggestions_served"
        # the activator finalized the label, so only another administrator can approve it (A6.0)
        with pytest.raises(tds.LabelReviewError) as exc:
            tds.review_label_revision(db, img.image_id, reviewer_id=case.a.r2.user_id,
                                      reviewer_email=case.a.r2.email, decision="approved",
                                      label_sha256=img.label_sha256)
        assert exc.value.reason == "reviewer_not_independent"
        out = tds.review_label_revision(db, img.image_id, reviewer_id=case.a.r3.user_id,
                                        reviewer_email=case.a.r3.email, decision="approved",
                                        label_sha256=img.label_sha256, reconcile=False)
        assert out["training_eligible"] is True
        assert db.query(Image).get(case.img.image_id).label_provenance == "admin_approved"
        replay = _post(api, case.a.r2, rid, "activate").json()
        assert replay["idempotent_replay"] is True and replay["training_eligible"] is True

    def test_failed_activation_rolls_back_everything(self, db, api, case, monkeypatch):
        rid = _approved_revision(api, db, case)
        before = _image_state(db, case.img.image_id)
        head = _rows(db, LabelRevisionHead, image_id=case.img.image_id)

        def boom(*a, **k):
            raise lrs.IntegrityError("simulated failure after the rows were rewritten", None, None)
        monkeypatch.setattr(lrs, "_move_head", boom)
        r = _post(api, case.a.r2, rid, "activate")
        assert r.status_code == 409 and "nothing was changed" in r.text
        assert _image_state(db, case.img.image_id) == before
        assert _rows(db, LabelRevisionHead, image_id=case.img.image_id) == head
        assert db.query(LabelRevisionEvent).filter_by(revision_id=rid, event="activated").count() == 0

    def test_label_install_failure_keeps_the_label_file(self, db, api, case, monkeypatch):
        rid = _approved_revision(api, db, case)
        img = db.query(Image).get(case.img.image_id)
        label = open(img.yolo_txt_path, "rb").read()

        def broken(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(tds, "_install_label", broken)
        body = _post(api, case.a.r2, rid, "activate").json()
        assert body["finalize"]["finalized"] is False and body["finalize"]["reason"] == "finalize_failed"
        assert body["label_finalized"] is False and body["training_eligible"] is False
        img = db.query(Image).get(case.img.image_id)
        assert open(img.yolo_txt_path, "rb").read() == label and img.label_sha256 is None
        assert db.query(LabelRevisionHead).get(case.img.image_id).revision_id == rid

    def test_stale_revisions_are_not_activated(self, db, api, case):
        rid = _approved_revision(api, db, case)
        ann = _ann(db, case.img.image_id)
        ann.label_data_json = {"points": [{"x": 11, "y": 20}, {"x": 110, "y": 120}]}
        db.commit()
        r = _post(api, case.a.r2, rid, "activate")
        assert r.status_code == 409 and "annotations changed" in r.text
        assert _ann(db, case.img.image_id).category_id == case.cats[0].category_id

    def test_eligible_and_snapshotted_images_are_never_rewritten(self, db, api, user, tmp_path, three_cats, admins):
        _set_threshold(db, 1)
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=True)
        assert db.query(TrainingSnapshot).count() == 1                     # V1 locked with this image
        digest, seq = _snapshot_digest(db), img.training_sequence
        _as(api, user)
        pid = _predict(api, image_id=img.image_id).json()["prediction_id"]
        c = SimpleNamespace(img=img, pid=pid, cats=three_cats, a=admins, owner=user,
                            ann_id=_ann(db, img.image_id).annotation_id)
        state = _image_state(db, img.image_id)
        rid = _approved_revision(api, db, c)
        r = _post(api, admins.r2, rid, "activate")
        assert r.status_code == 409 and "frozen training snapshot" in r.text
        assert _image_state(db, img.image_id) == state                     # rows, label file, sequence
        assert _snapshot_digest(db) == digest and db.query(Image).get(img.image_id).training_sequence == seq
        base = db.query(LabelRevision).get(db.query(LabelRevision).get(rid).parent_revision_id)
        assert base.base_training_sequence == seq and base.base_label_provenance == "user_confirmed"

    def test_human_only_labels_keep_the_user_confirmation_pathway(self, db, api, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        _as(api, user)
        api.post(f"/api/label-revisions/image/{img.image_id}/capture")
        r = tds.finalize_image_labeling(db, img.image_id, finalized_by=user.user_id)
        assert r["training_eligible"] is True and r["label_provenance"] == "user_confirmed"
        listing = api.get(f"/api/label-revisions/image/{img.image_id}").json()
        assert listing["current"]["in_sync_with_annotations"] is True            # finalize changes no rows

    def test_restore_creates_a_reviewed_revision_of_an_earlier_state(self, db, api, case):
        rid = _approved_revision(api, db, case)
        _post(api, case.a.r2, rid, "activate")
        base_id = db.query(LabelRevision).get(rid).parent_revision_id
        _as_admin(case.a.r2)
        r = api.post(f"/api/label-revisions/{base_id}/restore", json={"reason": "Undo the class change"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["source"] == "admin_correction" and body["status"] == "draft"
        assert body["parent_revision_id"] == rid and body["correction"]["restored_revision_id"] == base_id
        assert body["hashes"]["annotation_fingerprint"] == db.query(LabelRevision).get(base_id).annotation_fingerprint
        again = api.post(f"/api/label-revisions/{base_id}/restore", json={"reason": "Undo the class change"})
        assert again.status_code == 200 and again.json()["revision_id"] == body["revision_id"]
        _post(api, case.a.r2, body["revision_id"], "submit")
        _post(api, case.a.r3, body["revision_id"], "approve")
        act = _post(api, case.a.r2, body["revision_id"], "activate")
        assert act.status_code == 200, act.text
        assert _ann(db, case.img.image_id).category_id == case.cats[0].category_id
        r = _post(api, case.a.r2, rid, "activate")                               # superseded
        assert r.status_code == 409 and "superseded" in r.text
        assert [x.revision_number for x in _revs(db, case.img.image_id)] == [1, 2, 3]


# ---------------------------------------------------------------------------
# 12-14. Concurrency and immutability
# ---------------------------------------------------------------------------

def _principal(u):
    return SimpleNamespace(user_id=u.user_id, email=u.email, role="admin")


def _race(Session, fns):
    gate, results = threading.Barrier(len(fns)), [None] * len(fns)

    def run(i):
        s = Session()
        try:
            gate.wait()
            results[i] = ("ok", fns[i](s))
        except Exception as exc:
            results[i] = ("err", getattr(exc, "status_code", type(exc).__name__))
        finally:
            s.close()
    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(fns))]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    return results


class TestConcurrencyAndImmutability:
    def test_concurrent_creation_applies_feedback_once(self, db, Session, api, case):
        _pg(db)
        fid = _wrong_class(api, db, case)
        other = _feedback(api, db, case, feedback_type="missed_object", suggested_category_id=case.cats[2].category_id,
                          suggested_geometry={"type": "bbox", "bbox": [120, 130, 190, 199]})
        p2, p3 = _principal(case.a.r2), _principal(case.a.r3)
        results = _race(Session, [
            lambda s: lrs.create_from_feedback(s, p2, fid, target_object_key=case.ann_id, reason=REASON)[1],
            lambda s: lrs.create_from_feedback(s, p3, fid, target_object_key=case.ann_id, reason=REASON)[1],
            lambda s: lrs.create_from_feedback(s, p3, other, reason=REASON)[1],
        ])
        assert sorted(results[:2]) == [("ok", False), ("ok", True)], results     # one created, one replayed
        assert results[2] == ("ok", False), results
        revs = _revs(db, case.img.image_id)
        assert [r.revision_number for r in revs] == [1, 2, 3]
        assert [r.source for r in revs].count("human_annotation") == 1           # one shared capture
        assert db.query(LabelRevision).filter_by(feedback_id=fid).count() == 1

    def test_concurrent_activation_installs_exactly_one(self, db, Session, api, case):
        _pg(db)
        r1 = _approved_revision(api, db, case)
        fid = _feedback(api, db, case, feedback_type="missed_object", suggested_category_id=case.cats[2].category_id,
                        suggested_geometry={"type": "bbox", "bbox": [120, 130, 190, 199]})
        r2 = _approved_revision(api, db, case, fid=fid, target_object_key=None)
        revs = {r.revision_id: r for r in _revs(db, case.img.image_id)}
        assert revs[r1].parent_revision_id == revs[r2].parent_revision_id     # both proposed on the capture
        who = _principal(case.a.r2)
        results = _race(Session, [lambda s: lrs.activate(s, who, r1)["revision_id"],
                                  lambda s: lrs.activate(s, who, r2)["revision_id"]])
        winners = [r[1] for r in results if r[0] == "ok"]
        assert len(winners) == 1 and ("err", 409) in results, results
        assert db.query(LabelRevisionHead).get(case.img.image_id).revision_id == winners[0]
        assert lrs.rows_fingerprint(db, case.img.image_id) == revs[winners[0]].annotation_fingerprint
        assert db.query(LabelRevisionEvent).filter_by(event="activated").count() == 1

    def test_revisions_and_events_cannot_be_rewritten(self, db, api, case):
        rid = _approved_revision(api, db, case)
        rev = db.query(LabelRevision).get(rid)
        rev.reason = "forged"
        with pytest.raises(LabelRevisionImmutableError):
            db.commit()
        db.rollback()
        db.delete(db.query(LabelRevisionEvent).filter_by(revision_id=rid, event="approved").one())
        with pytest.raises(LabelRevisionImmutableError):
            db.commit()
        db.rollback()
        db.delete(db.query(LabelRevisionHead).get(case.img.image_id))
        with pytest.raises(LabelRevisionImmutableError):
            db.commit()
        db.rollback()
        assert db.query(LabelRevision).get(rid).reason == REASON

    def test_database_enforces_revision_rules(self, db, api, case):
        _pg(db)
        rid = _approved_revision(api, db, case)
        draft_fid = _feedback(api, db, case, feedback_type="missed_object",
                              suggested_category_id=case.cats[2].category_id,
                              suggested_geometry={"type": "bbox", "bbox": [120, 130, 190, 199]})
        draft = _create(api, case.a.r2, draft_fid).json()["revision_id"]
        pending = _feedback(api, db, case, decision=None, feedback_type="false_detection", detection_index=1)
        img = case.img.image_id
        ev = "INSERT INTO label_revision_events (event_id, revision_id, image_id, event, to_status, actor_id, " \
             "actor_role, created_at) VALUES (:e, :r, :i, :ev, 'x', :a, 'admin', now())"
        refused = [
            ("UPDATE label_revisions SET reason = 'forged' WHERE revision_id = :r", {"r": rid}, "append-only"),
            ("DELETE FROM label_revisions WHERE revision_id = :r", {"r": rid}, "append-only"),
            ("UPDATE label_revision_events SET reason = 'x' WHERE revision_id = :r", {"r": rid}, "append-only"),
            ("DELETE FROM label_revision_events WHERE revision_id = :r", {"r": rid}, "append-only"),
            ("DELETE FROM label_revision_heads WHERE image_id = :i", {"i": img}, "cannot be deleted"),
            (ev, {"e": "e1", "r": draft, "i": img, "ev": "approved", "a": "someone"}, "submitted, undecided"),
            (ev, {"e": "e2", "r": draft, "i": img, "ev": "activated", "a": "someone"}, "only an approved"),
            ("UPDATE label_revision_heads SET revision_id = :r, event_id = (SELECT event_id FROM "
             "label_revision_events WHERE revision_id = :r AND event = 'created') WHERE image_id = :i",
             {"r": draft, "i": img}, "recorded or activated"),
            ("INSERT INTO label_revisions (revision_id, image_id, revision_number, source, feedback_id, "
             "prediction_id, created_by, created_by_role, created_at, contents, object_count, class_map, "
             "class_map_sha256, content_sha256, annotation_fingerprint, label_text, label_sha256) VALUES "
             "('forged', :i, 99, 'approved_feedback', :f, :p, 'x', 'admin', now(), '{}', 0, '[]', 'a', 'b', "
             "'c', '', 'd')", {"i": img, "f": pending, "p": case.pid}, "requires approved feedback"),
        ]

        def check(cases):
            for sql, params, msg in cases:
                with pytest.raises(Exception) as exc:
                    db.execute(text(sql), params)
                    db.flush()
                db.rollback()
                assert msg in str(exc.value), (sql, str(exc.value)[:300])
        check(refused)
        _post(api, case.a.r2, draft, "submit")
        check([(ev, {"e": "e3", "r": draft, "i": img, "ev": "approved", "a": case.a.r2.user_id},
                "independent reviewer")])
        assert db.query(LabelRevision).get(rid).reason == REASON


# ---------------------------------------------------------------------------
# 22. Backward compatibility
# ---------------------------------------------------------------------------

class TestCompatibility:
    def test_existing_feedback_and_annotation_apis_are_unchanged(self, db, api, case):
        fid = _wrong_class(api, db, case)
        _as_admin(case.a.r1)
        review = api.get(f"/api/ml/feedback-review/{fid}").json()
        _as(api, case.owner)
        mine = api.get(f"/api/ml/feedback/{fid}").json()
        anns = api.get(f"/api/annotations/image/{case.img.image_id}").json()
        rid = _approved_revision(api, db, case, fid=fid)
        _as_admin(case.a.r1)
        assert api.get(f"/api/ml/feedback-review/{fid}").json() == review
        _as(api, case.owner)
        assert api.get(f"/api/ml/feedback/{fid}").json() == mine
        assert api.get(f"/api/annotations/image/{case.img.image_id}").json() == anns   # not yet activated
        _as_admin(case.a.r2)
        queue = api.get("/api/label-revisions/review-queue", params={"feedback_id": fid}).json()
        assert [i["revision_id"] for i in queue["items"]] == [rid] and queue["items"][0]["status"] == "approved"
        assert api.get("/api/label-revisions/review-queue", params={"status": "submitted"}).json()["total"] == 0
        assert api.get("/api/label-revisions/review-queue", params={"status": "bogus"}).status_code == 422


@pytest.mark.skipif("test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
                    reason="real-JWT access test only runs against an isolated *test* database")
@pytest.mark.parametrize("method,url", [("get", "/api/label-revisions/image/x"), ("get", "/api/label-revisions/x"),
                                        ("post", "/api/label-revisions/from-feedback/x"),
                                        ("post", "/api/label-revisions/x/activate"),
                                        ("get", "/api/label-revisions/review-queue")])
def test_label_revision_endpoints_require_authentication(client, method, url):
    assert getattr(client, method)(url).status_code == 401
