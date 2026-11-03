"""
ZWM v1.1.0 Block A6.0 — training eligibility evidence.

A human-only label revision finalized by a person is eligible on finalize (A1,
provenance user_confirmed). Any AI involvement -- AI-generated annotations, or AI
suggestions served for the image -- or annotations by someone else require an
independent administrator approval of the exact revision (admin_approved).

Isolation as in A1-A5.1: per-test SQLite (or the throwaway PostgreSQL database from
ZWM_A1_TEST_DATABASE_URL), synthetic PNGs and labels under tmp_path, no YOLO.
"""
import hashlib
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.models.annotation import Annotation
from app.models.image import Image
from app.models.label_review import LabelReview, LabelReviewImmutableError
from app.models.training import TrainingSnapshot, TrainingSnapshotImage
from app.models.user import User
from app.routes.annotation import _generate_yolo_txt_for_image
from app.services import training_dataset_service as tds
from app.services.lifecycle_service import promote_to_permanent
from test_training_foundation import (  # noqa: F401
    REVIEWER_EMAIL, REVIEWER_ID, Session, _annotate, _approve_label, _complete_many, _set_threshold,
    _uploaded_image, api, db, engine, queued, three_cats, user,
)

APPROVE = "approved"


def _is_pg(db):
    return db.get_bind().dialect.name == "postgresql"


def _labelled(db, user, cat, tmp_path, ai=True, finalize=True):
    """
    Uploaded + annotated + promoted (+ finalized by the contributor). Never approved.
    ai=True (default): the annotation is AI-generated, so the revision needs review;
    ai=False: a human-only label, which finalize makes eligible (user_confirmed).
    """
    img = _uploaded_image(db, user, cat, tmp_path)
    _annotate(db, user, img, cat.category_id)
    if ai:
        a = db.query(Annotation).filter(Annotation.image_id == img.image_id).one()
        a.ai_generated = True
        db.commit()
    txt = _generate_yolo_txt_for_image(img.image_id, db)
    assert promote_to_permanent(db, img.image_id, txt)["success"]
    if finalize:
        r = tds.finalize_image_labeling(db, img.image_id, finalized_by=user.user_id)
        assert r["finalized"] and r["training_eligible"] is (not ai) and r["awaiting_review"] is ai
    db.refresh(img)
    return img


def _pin_pending_revision(db, img, finalized_by):
    """The state finalize left behind while review was mandatory: pinned, not eligible."""
    img.label_sha256 = tds.file_sha256(img.yolo_txt_path)
    img.label_fingerprint = tds.annotation_fingerprint(db, img.image_id)
    img.label_finalized_by = finalized_by
    db.commit()
    db.refresh(img)
    return img


def _review(db, img, decision=APPROVE, reviewer_id=REVIEWER_ID, email=REVIEWER_EMAIL, sha=None):
    db.refresh(img)
    return tds.review_label_revision(db, img.image_id, reviewer_id=reviewer_id, reviewer_email=email,
                                     decision=decision, label_sha256=sha or img.label_sha256)


def _reason(db, img):
    db.expire_all()
    fresh = db.query(Image).filter(Image.image_id == img.image_id).one()
    return tds.evaluate_training_eligibility(db, fresh)


def _snapshot_digest(db):
    rows = (db.query(TrainingSnapshotImage.snapshot_id, TrainingSnapshotImage.image_id,
                     TrainingSnapshotImage.position, TrainingSnapshotImage.training_sequence,
                     TrainingSnapshotImage.split_type)
            .order_by(TrainingSnapshotImage.snapshot_id, TrainingSnapshotImage.position).all())
    snaps = db.query(TrainingSnapshot.snapshot_id, TrainingSnapshot.version, TrainingSnapshot.milestone_count,
                     TrainingSnapshot.dataset_size, TrainingSnapshot.class_map).order_by(TrainingSnapshot.version).all()
    return hashlib.sha256(repr((rows, snaps)).encode()).hexdigest()


# ---------------------------------------------------------------------------
# 1. AI involvement: finalize / AI acceptance / AI annotations never authorize
# ---------------------------------------------------------------------------

class TestNoSelfAuthorization:
    def test_ai_involved_finalize_does_not_authorize_training(self, db, user, tmp_path, three_cats, api):
        a, _, _ = three_cats
        _set_threshold(db, 1)
        img = _labelled(db, user, a, tmp_path, finalize=False)
        r = api.post(f"/api/annotations/image/{img.image_id}/finalize")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["training_eligible"] is False and body["awaiting_review"] is True
        assert body["training_sequence"] is None and body["label_sha256"]
        assert _reason(db, img) == (False, "label_not_reviewed")
        assert db.query(TrainingSnapshot).count() == 0                  # threshold 1, still no snapshot
        again = api.post(f"/api/annotations/image/{img.image_id}/finalize").json()
        assert again["already_finalized"] is True and again["training_sequence"] is None

    def test_mark_training_eligible_refuses_without_approval(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        assert tds.mark_training_eligible(db, img) is False
        db.rollback()
        assert _reason(db, img)[0] is False

    def test_ai_auto_acceptance_alone_does_not_authorize(self, db, user, tmp_path, three_cats, api):
        img = _labelled(db, user, three_cats[0], tmp_path)
        img.is_validated, img.validation_result, img.ai_confidence_score = True, "AUTO_ACCEPTED", 0.99
        db.commit()
        assert _reason(db, img) == (False, "label_not_reviewed")
        # the upload-validation approval (rewards workflow) is not a training approval either
        r = api.post(f"/api/admin/images/{img.image_id}/approve", json={"action": "approve"})
        assert r.status_code == 200
        assert _reason(db, img)[0] is False
        db.expire_all()
        assert db.query(Image).filter(Image.image_id == img.image_id).one().training_sequence is None

    def test_unreviewed_ai_generated_annotations_remain_ineligible(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=True)
        assert _reason(db, img) == (False, "label_not_reviewed")
        assert tds.label_review_state(db, img)["ai_involved"] is True

    def test_historical_backfill_never_grants_ai_labels(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path, finalize=False)
        report = tds.backfill_historical_images(db, apply=True)
        mine = [f for f in report["finalized"] if f["image_id"] == img.image_id]
        assert all(f["training_sequence"] is None and f["awaiting_review"] for f in mine)
        assert _reason(db, img)[0] is False


# ---------------------------------------------------------------------------
# 2. Independent administrator approval
# ---------------------------------------------------------------------------

class TestIndependentApproval:
    def test_approval_of_exact_revision_grants_one_sequence(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        r = _review(db, img)
        assert r["training_eligible"] and r["created"] and r["training_sequence"] == 1
        db.refresh(img)
        review = db.query(LabelReview).filter(LabelReview.review_id == img.training_review_id).one()
        assert review.outcome == APPROVE and review.reviewer_id == REVIEWER_ID
        assert review.label_sha256 == img.label_sha256 == tds.file_sha256(img.yolo_txt_path)
        assert review.annotator_ids == sorted({user.user_id})
        assert img.training_eligible_at is not None

    def test_ai_annotations_eligible_only_after_independent_review(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=True)
        r = _review(db, img)
        assert r["training_eligible"]
        assert db.query(LabelReview).filter(LabelReview.image_id == img.image_id).one().ai_involved is True

    @pytest.mark.parametrize("who", ["uploader_id", "annotator_email", "finalizer_id"])
    def test_reviewer_must_be_independent(self, db, user, tmp_path, three_cats, who):
        img = _labelled(db, user, three_cats[0], tmp_path)
        if who == "finalizer_id":
            img.label_finalized_by = "admin-who-finalized"
            db.commit()
        rid, email = {"uploader_id": (user.user_id, "someone@example.com"),
                      "annotator_email": ("admin-other-id", user.email),
                      "finalizer_id": ("admin-who-finalized", "x@example.com")}[who]
        with pytest.raises(tds.LabelReviewError) as exc:
            _review(db, img, reviewer_id=rid, email=email)
        assert exc.value.reason == "reviewer_not_independent" and exc.value.status == 403
        assert _reason(db, img)[0] is False
        assert db.query(LabelReview).count() == 0

    def test_rejection_is_recorded_and_keeps_image_ineligible(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        r = _review(db, img, decision="rejected")
        assert r["training_eligible"] is False
        assert _reason(db, img) == (False, "label_not_reviewed")
        assert tds.pending_label_reviews(db)["total"] == 0              # decided: leaves the queue
        assert _review(db, img)["training_eligible"]                    # a later approval is still possible

    def test_unfinalized_or_unknown_images_cannot_be_approved(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path, finalize=False)
        with pytest.raises(tds.LabelReviewError, match="label_not_finalized"):
            _review(db, img, sha="0" * 64)
        with pytest.raises(tds.LabelReviewError) as exc:
            tds.review_label_revision(db, str(uuid.uuid4()), reviewer_id=REVIEWER_ID, reviewer_email=None,
                                      decision=APPROVE, label_sha256="0" * 64)
        assert exc.value.status == 404


# ---------------------------------------------------------------------------
# 3. Any change invalidates an approval until reviewed again
# ---------------------------------------------------------------------------

class TestInvalidation:
    def test_annotation_change_after_finalize_requires_refinalize_and_new_review(self, db, user, tmp_path, three_cats):
        a, b, _ = three_cats
        img = _labelled(db, user, a, tmp_path)
        old_sha = img.label_sha256
        _annotate(db, user, img, b.category_id)                        # contributor adds an object
        db.refresh(img)
        assert img.label_sha256 is None                                # finalized revision cleared
        with pytest.raises(tds.LabelReviewError, match="label_not_finalized"):
            _review(db, img, sha=old_sha)
        img.status = "permanent"
        db.commit()
        tds.finalize_image_labeling(db, img.image_id, finalized_by=user.user_id)
        db.refresh(img)
        assert img.label_sha256 != old_sha
        with pytest.raises(tds.LabelReviewError, match="stale_label_revision"):
            _review(db, img, sha=old_sha)                              # screen showed the old revision
        assert _review(db, img)["training_eligible"]

    def test_existing_approval_is_void_after_annotation_change(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        db.add(LabelReview(image_id=img.image_id, label_sha256=img.label_sha256,
                           annotation_fingerprint=img.label_fingerprint, outcome=APPROVE,
                           reviewer_id=REVIEWER_ID, annotator_ids=[user.user_id], ai_involved=False))
        db.commit()
        assert _reason(db, img) == (True, "ok")                        # approved, not yet sequenced
        ann = db.query(Annotation).filter(Annotation.image_id == img.image_id).one()
        ann.label_data_json = {"points": [{"x": 1, "y": 1}, {"x": 50, "y": 50}]}
        db.commit()
        assert _reason(db, img)[0] is False
        db.expire_all()
        fresh = db.query(Image).filter(Image.image_id == img.image_id).one()
        assert tds.mark_training_eligible(db, fresh) is False
        db.rollback()

    def test_label_file_tampering_invalidates(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        sha = img.label_sha256
        Path(img.yolo_txt_path).write_text("0 0.5 0.5 0.9 0.9\n")
        assert _reason(db, img) == (False, "label_changed_since_finalize")
        with pytest.raises(tds.LabelReviewError, match="label_changed_since_finalize"):
            _review(db, img, sha=sha)

    def test_reviews_are_append_only(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        _review(db, img, decision="rejected")
        rev = db.query(LabelReview).one()
        rev.reason = "rewritten"
        with pytest.raises(LabelReviewImmutableError):
            db.commit()
        db.rollback()
        with pytest.raises(LabelReviewImmutableError):
            db.delete(db.query(LabelReview).one())
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# 4. Idempotency and concurrency
# ---------------------------------------------------------------------------

class TestIdempotencyAndConcurrency:
    def test_repeated_requests_do_not_duplicate_sequences(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        seqs = {_review(db, img)["training_sequence"] for _ in range(3)}
        tds.finalize_image_labeling(db, img.image_id, finalized_by=user.user_id)
        assert seqs == {1}
        assert db.query(LabelReview).filter(LabelReview.outcome == APPROVE).count() == 1
        assert db.query(Image).filter(Image.training_sequence.isnot(None)).count() == 1
        with pytest.raises(tds.LabelReviewError):
            _review(db, img, decision="rejected")                      # eligible labels are locked

    def test_concurrent_approvals_assign_exactly_one_sequence(self, db, Session, user, tmp_path, three_cats):
        if not _is_pg(db):
            pytest.skip("row/advisory locks need PostgreSQL")
        img = _labelled(db, user, three_cats[0], tmp_path)
        sha, results, errors = img.label_sha256, [], []
        barrier = threading.Barrier(5)

        def approve(i):
            s = Session()
            try:
                barrier.wait(10)
                results.append(tds.review_label_revision(s, img.image_id, reviewer_id=f"admin-{i}",
                                                         reviewer_email=None, decision=APPROVE, label_sha256=sha))
            except Exception as exc:                                    # noqa: BLE001
                errors.append(repr(exc))
            finally:
                s.close()

        threads = [threading.Thread(target=approve, args=(i,)) for i in range(5)]
        [t.start() for t in threads]
        [t.join(60) for t in threads]
        assert not errors, errors
        assert {r["training_sequence"] for r in results} == {1}
        assert sum(r["created"] for r in results) == 1
        assert db.query(LabelReview).filter(LabelReview.outcome == APPROVE).count() == 1

    def test_concurrent_approval_and_label_change_cannot_bypass(self, db, Session, user, tmp_path, three_cats):
        if not _is_pg(db):
            pytest.skip("row/advisory locks need PostgreSQL")
        a, b, _ = three_cats
        for _round in range(4):
            img = _labelled(db, user, a, tmp_path)
            old_sha, out = img.label_sha256, {}
            barrier = threading.Barrier(2)

            def approve():
                s = Session()
                try:
                    barrier.wait(10)
                    out["approve"] = tds.review_label_revision(s, img.image_id, reviewer_id=REVIEWER_ID,
                                                               reviewer_email=None, decision=APPROVE,
                                                               label_sha256=old_sha)
                except Exception as exc:                                # noqa: BLE001
                    out["approve"] = exc
                finally:
                    s.close()

            def change_and_refinalize():
                s = Session()
                try:
                    barrier.wait(10)
                    target = s.query(Image).filter(Image.image_id == img.image_id).one()
                    if tds.annotation_mutation_block_reason(s, target):
                        out["change"] = "blocked"                        # already eligible: locked
                        return
                    s.add(Annotation(image_id=img.image_id, category_id=b.category_id, annotated_by=user.user_id,
                                     annotation_type="rectangle", image_width=200, image_height=200,
                                     label_data_json={"points": [{"x": 30, "y": 30}, {"x": 90, "y": 90}]}))
                    s.commit()
                    out["change"] = tds.finalize_image_labeling(s, img.image_id, finalized_by=user.user_id)
                except Exception as exc:                                # noqa: BLE001
                    out["change"] = exc
                finally:
                    s.close()

            ts = [threading.Thread(target=approve), threading.Thread(target=change_and_refinalize)]
            [t.start() for t in ts]
            [t.join(60) for t in ts]
            db.expire_all()
            fresh = db.query(Image).filter(Image.image_id == img.image_id).one()
            if fresh.training_sequence is not None:
                # whatever won, the eligible revision is exactly the approved one, unchanged since
                review = db.query(LabelReview).filter(LabelReview.review_id == fresh.training_review_id).one()
                assert review.label_sha256 == fresh.label_sha256 == tds.file_sha256(fresh.yolo_txt_path)
                assert review.annotation_fingerprint == tds.annotation_fingerprint(db, fresh.image_id)
            else:
                assert isinstance(out["approve"], tds.LabelReviewError)


# ---------------------------------------------------------------------------
# 5. PostgreSQL backstops
# ---------------------------------------------------------------------------

class TestDatabaseBackstops:
    @pytest.fixture(autouse=True)
    def _pg_only(self, db):
        if not _is_pg(db):
            pytest.skip("PostgreSQL triggers")

    def test_annotations_of_eligible_image_locked_in_sql(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        _review(db, img)
        for sql in ("UPDATE annotations SET category_id = category_id WHERE image_id = :i",
                    "DELETE FROM annotations WHERE image_id = :i"):
            with pytest.raises(Exception, match="locked"):
                db.execute(text(sql), {"i": img.image_id})
            db.rollback()

    def test_direct_sequence_assignment_is_rejected(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        for sql in ("UPDATE images SET training_sequence = 999 WHERE image_id = :i",
                    "UPDATE images SET training_sequence = 999, training_review_id = 'forged' WHERE image_id = :i"):
            with pytest.raises(Exception, match="administrator approval"):
                db.execute(text(sql), {"i": img.image_id})
            db.rollback()

    def test_rejected_review_cannot_back_eligibility(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        rid = _review(db, img, decision="rejected")["review_id"]
        with pytest.raises(Exception, match="administrator approval"):
            db.execute(text("UPDATE images SET training_sequence = 5, training_review_id = :r WHERE image_id = :i"),
                       {"r": rid, "i": img.image_id})
        db.rollback()

    def test_user_confirmed_path_in_sql_requires_real_human_evidence(self, db, user, tmp_path, three_cats):
        a = three_cats[0]
        human = _pin_pending_revision(db, _labelled(db, user, a, tmp_path, ai=False, finalize=False), user.user_id)
        ai = _labelled(db, user, a, tmp_path)                            # AI-generated annotation
        hinted = _pin_pending_revision(db, _labelled(db, user, a, tmp_path, ai=False, finalize=False), user.user_id)
        tds.record_ai_suggestion(db, hinted.image_id)                   # AI suggestions were served
        unpinned = _labelled(db, user, a, tmp_path, ai=False, finalize=False)
        rejected = _pin_pending_revision(db, _labelled(db, user, a, tmp_path, ai=False, finalize=False), user.user_id)
        _review(db, rejected, decision="rejected")
        forge = ("UPDATE images SET training_sequence = :q, label_provenance = 'user_confirmed', "
                 "training_review_id = NULL WHERE image_id = :i")
        for n, img in enumerate((ai, hinted, unpinned, rejected), start=500):
            with pytest.raises(Exception, match="user-confirmed human label"):
                db.execute(text(forge), {"q": n, "i": img.image_id})
            db.rollback()
        with pytest.raises(Exception, match="administrator approval"):  # provenance cannot borrow a review
            db.execute(text("UPDATE images SET training_sequence = 600, label_provenance = 'user_confirmed', "
                            "training_review_id = 'x' WHERE image_id = :i"), {"i": human.image_id})
        db.rollback()
        db.execute(text(forge), {"q": 700, "i": human.image_id})         # genuine human-only evidence passes
        db.commit()
        db.expire_all()
        assert db.query(Image).filter(Image.image_id == human.image_id).one().training_sequence == 700

    def test_reviews_immutable_and_independent_in_sql(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path)
        _review(db, img, decision="rejected")
        for sql in ("UPDATE label_reviews SET reason = 'x'", "DELETE FROM label_reviews"):
            with pytest.raises(Exception, match="append-only"):
                db.execute(text(sql))
            db.rollback()
        with pytest.raises(Exception, match="independent reviewer"):
            db.execute(text("INSERT INTO label_reviews (review_id, image_id, label_sha256, annotation_fingerprint, "
                            "outcome, reviewer_id, annotator_ids, ai_involved, reviewed_at) VALUES "
                            "('r1', :i, :s, :f, 'approved', :u, '[]', false, now())"),
                       {"i": img.image_id, "s": img.label_sha256, "f": img.label_fingerprint, "u": user.user_id})
        db.rollback()


# ---------------------------------------------------------------------------
# 6. Historical data untouched
# ---------------------------------------------------------------------------

class TestHistoricalPreservation:
    def test_existing_snapshots_unchanged_by_new_approvals(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        _set_threshold(db, 3)
        _complete_many(db, user, [(a, 1), (b, 1), (c, 1)], tmp_path)        # V1 (user-confirmed labels)
        assert db.query(TrainingSnapshot).count() == 1
        before = (_snapshot_digest(db), [(i.image_id, i.training_sequence, i.training_review_id, i.label_sha256)
                                         for i in db.query(Image).order_by(Image.training_sequence).all()])
        pending = [_labelled(db, user, a, tmp_path) for _ in range(2)]
        for img in pending:
            _review(db, img, decision="rejected")
        assert _snapshot_digest(db) == before[0]
        after_rows = [(i.image_id, i.training_sequence, i.training_review_id, i.label_sha256)
                      for i in db.query(Image).filter(Image.training_sequence.isnot(None))
                      .order_by(Image.training_sequence).all()]
        assert after_rows == before[1]

    def test_pre_a60_eligible_rows_stay_eligible_without_backfill(self, db, user, tmp_path, three_cats):
        if not _is_pg(db):
            pytest.skip("simulating a pre-migration row needs trigger bypass (PostgreSQL)")
        img = _labelled(db, user, three_cats[0], tmp_path)
        db.execute(text("SET session_replication_role = replica"))    # rows that existed before A6.0
        db.execute(text("UPDATE images SET training_sequence = 77, training_eligible_at = now(), "
                        "label_sha256 = NULL, label_fingerprint = NULL WHERE image_id = :i"), {"i": img.image_id})
        db.execute(text("SET session_replication_role = DEFAULT"))
        db.commit()
        db.expire_all()
        hist = db.query(Image).filter(Image.image_id == img.image_id).one()
        assert hist.training_review_id is None and db.query(LabelReview).count() == 0   # nothing invented
        hist.status = "permanent"                                       # unrelated updates still allowed
        db.commit()
        assert tds.eligible_images_query(db).filter(Image.image_id == img.image_id).count() == 1


# ---------------------------------------------------------------------------
# 7. Database-stored paths cannot cause deletion outside the upload root
# ---------------------------------------------------------------------------

class TestDeletionConfinement:
    def test_image_delete_only_removes_files_inside_uploads(self, db, user, tmp_path, three_cats, api):
        img = _uploaded_image(db, user, three_cats[0], tmp_path)
        outside = tmp_path / "outside" / "victim.png"
        outside.parent.mkdir()
        outside.write_bytes(b"keep me")
        inside = Path(img.temp_s3_path)
        img.permanent_s3_path = str(outside)
        db.commit()
        r = api.delete(f"/api/images/{img.image_id}")
        assert r.status_code == 200, r.text
        assert outside.exists() and outside.read_bytes() == b"keep me"
        assert not inside.exists()

    def test_annotation_delete_only_removes_files_inside_uploads(self, db, user, tmp_path, three_cats, api):
        img = _uploaded_image(db, user, three_cats[0], tmp_path)
        _annotate(db, user, img, three_cats[0].category_id)
        ann = db.query(Annotation).filter(Annotation.image_id == img.image_id).one()
        outside = tmp_path / "elsewhere.json"
        outside.write_text("{}")
        inside = Path(settings.UPLOAD_FOLDER) / "labels" / "x.json"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_text("{}")
        ann.label_json_path, ann.yolo_label_path = str(outside), str(inside)
        db.commit()
        r = api.delete(f"/api/annotations/{ann.annotation_id}")
        assert r.status_code in (200, 204), r.text
        assert outside.exists() and not inside.exists()

    def test_traversal_and_directories_are_refused(self, tmp_path):
        from app.services.fs_safety import remove_file_within
        root = tmp_path / "uploads"
        (root / "sub").mkdir(parents=True)
        victim = tmp_path / "victim.txt"
        victim.write_text("x")
        assert remove_file_within(str(root / ".." / "victim.txt"), root) is False and victim.exists()
        assert remove_file_within(str(root / "sub"), root) is False and (root / "sub").is_dir()
        assert remove_file_within(None, root) is False


# ---------------------------------------------------------------------------
# 7b. User-confirmed (human-only) labels keep A1's finalize semantics
# ---------------------------------------------------------------------------

class TestUserConfirmedLabels:
    def test_human_only_finalize_is_eligible_immediately(self, db, user, tmp_path, three_cats, api):
        a, _, _ = three_cats
        _set_threshold(db, 1)
        img = _labelled(db, user, a, tmp_path, ai=False, finalize=False)
        body = api.post(f"/api/annotations/image/{img.image_id}/finalize").json()
        assert body["training_eligible"] is True and body["training_sequence"] == 1
        assert body["label_provenance"] == "user_confirmed" and body["snapshots_created"] == [1]
        db.expire_all()
        fresh = db.query(Image).filter(Image.image_id == img.image_id).one()
        assert fresh.training_review_id is None and fresh.label_finalized_by == user.user_id
        assert db.query(LabelReview).count() == 0                        # no approval invented
        assert tds.label_review_state(db, fresh)["requires_review"] is False
        again = api.post(f"/api/annotations/image/{img.image_id}/finalize").json()
        assert again["already_finalized"] and again["training_sequence"] == 1      # idempotent

    def test_ai_suggestions_served_for_the_image_require_review(self, db, user, tmp_path, three_cats, api,
                                                                monkeypatch):
        from app.routes import ai_segmentation
        calls = []
        monkeypatch.setattr(ai_segmentation.ai_detector_instance, "segment_from_click",
                            lambda **kw: calls.append(kw) or {"points": [[1, 1], [9, 1], [9, 9]], "bbox": [1, 1, 9, 9]})
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        r = api.post("/api/ai/polygon-click", json={"image_id": img.image_id, "x": 5, "y": 5})
        assert r.status_code == 200 and calls                             # fake detector only
        # the client saves the suggestion as a "manual" annotation: the server still knows
        body = api.post(f"/api/annotations/image/{img.image_id}/finalize").json()
        assert body["training_eligible"] is False and body["awaiting_review"] is True
        db.expire_all()
        fresh = db.query(Image).filter(Image.image_id == img.image_id).one()
        assert fresh.ai_suggested_at is not None
        assert tds.user_confirmation_problem(db, fresh) == "ai_suggestions_served"
        assert _review(db, fresh)["training_eligible"]                    # independent review grants it
        db.refresh(fresh)
        assert fresh.label_provenance == "admin_approved" and fresh.training_review_id

    def test_ai_segment_marker_is_written_before_suggestions(self, db, user, tmp_path, three_cats, api, monkeypatch):
        from app.routes import ai_segmentation
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        seen = []

        def fake_segment(**kw):
            s = db.get_bind().connect()
            try:
                seen.append(s.execute(text("SELECT ai_suggested_at FROM images WHERE image_id = :i"),
                                      {"i": img.image_id}).scalar())
            finally:
                s.close()
            return [{"points": [[1, 1], [9, 1], [9, 9]]}]

        monkeypatch.setattr(ai_segmentation.ai_detector_instance, "segment_image", fake_segment)
        assert api.post("/api/ai/segment", json={"image_id": img.image_id}).status_code == 200
        assert seen and seen[0] is not None                               # committed before inference

    def test_foreign_annotations_require_review(self, db, user, tmp_path, three_cats):
        other = User(email=f"other_{uuid.uuid4().hex[:6]}@test.com", password_hash="x", role="user")
        db.add(other)
        db.commit()
        a, b, _ = three_cats
        img = _labelled(db, user, a, tmp_path, ai=False, finalize=False)
        _annotate(db, other, img, b.category_id)                         # someone else's object
        img.status = "permanent"
        db.commit()
        r = tds.finalize_image_labeling(db, img.image_id, finalized_by=user.user_id)
        assert r["training_eligible"] is False and r["awaiting_review"] is True
        assert tds.user_confirmation_problem(db, img) == "foreign_annotations"

    def test_rejected_human_revision_is_never_self_confirmed(self, db, user, tmp_path, three_cats, api):
        img = _pin_pending_revision(db, _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False),
                                    user.user_id)
        _review(db, img, decision="rejected")
        body = api.post(f"/api/annotations/image/{img.image_id}/finalize").json()
        assert body["training_eligible"] is False and body["training_sequence"] is None
        assert _reason(db, img) == (False, "label_rejected")

    def test_revision_left_pending_by_mandatory_review_is_granted_on_refinalize(self, db, user, tmp_path,
                                                                                three_cats, api):
        img = _pin_pending_revision(db, _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False),
                                    user.user_id)
        assert db.query(Image).filter(Image.image_id == img.image_id).one().training_sequence is None
        body = api.post(f"/api/annotations/image/{img.image_id}/finalize").json()
        assert body["already_finalized"] and body["training_eligible"] and body["label_provenance"] == "user_confirmed"

    def test_human_only_historical_backfill_follows_a1(self, db, user, tmp_path, three_cats):
        human = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        ai = _labelled(db, user, three_cats[0], tmp_path, finalize=False)
        report = tds.backfill_historical_images(db, apply=True)
        by_id = {f["image_id"]: f for f in report["finalized"]}
        assert by_id[human.image_id]["training_sequence"] is not None
        assert by_id[ai.image_id]["training_sequence"] is None and by_id[ai.image_id]["awaiting_review"]

    def test_user_confirmed_grants_never_alter_existing_snapshots(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        _set_threshold(db, 3)
        _complete_many(db, user, [(a, 1), (b, 1), (c, 1)], tmp_path)
        before = (_snapshot_digest(db), [(i.image_id, i.training_sequence, i.label_sha256)
                                         for i in db.query(Image).order_by(Image.training_sequence).all()])
        _complete_many(db, user, [(a, 1), (b, 1), (c, 1)], tmp_path)    # appended: V2
        v1 = db.query(TrainingSnapshot).filter(TrainingSnapshot.version == 1).one()
        rows = (db.query(TrainingSnapshotImage).filter(TrainingSnapshotImage.snapshot_id == v1.snapshot_id)
                .order_by(TrainingSnapshotImage.position).all())
        assert [r.image_id for r in rows] == [x[0] for x in before[1]]
        old = [(i.image_id, i.training_sequence, i.label_sha256) for i in
               db.query(Image).filter(Image.image_id.in_([x[0] for x in before[1]])).order_by(Image.training_sequence)]
        assert old == before[1] and db.query(TrainingSnapshot).count() == 2

    def test_label_outside_upload_root_is_refused(self, db, user, tmp_path, three_cats):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=False, finalize=False)
        outside = tmp_path / "outside" / "label.txt"
        outside.parent.mkdir()
        outside.write_text(Path(img.yolo_txt_path).read_text())
        original = outside.read_bytes()
        img.yolo_txt_path = str(outside)
        db.commit()
        with pytest.raises(tds.LabelingFinalizationError, match="unsafe_label_path"):
            tds.finalize_image_labeling(db, img.image_id, finalized_by=user.user_id)
        assert outside.read_bytes() == original and not list(outside.parent.glob("*.bak"))
        db.expire_all()
        assert db.query(Image).filter(Image.image_id == img.image_id).one().training_sequence is None


# ---------------------------------------------------------------------------
# 8. Admin HTTP workflow
# ---------------------------------------------------------------------------

class TestAdminApi:
    @pytest.fixture()
    def admin_api(self, api):
        from app.dependencies.auth import require_admin
        from app.main import app as fastapi_app
        reviewer = User(user_id=REVIEWER_ID, email=REVIEWER_EMAIL, role="admin", password_hash="x")
        fastapi_app.dependency_overrides[require_admin] = lambda: reviewer
        return api

    def test_pending_review_approve_flow(self, db, user, tmp_path, three_cats, admin_api):
        img = _labelled(db, user, three_cats[0], tmp_path, ai=True)
        pend = admin_api.get("/api/admin/label-reviews/pending").json()
        assert pend["total"] == 1 and pend["items"][0]["image_id"] == img.image_id
        item = pend["items"][0]
        assert item["ai_involved"] and item["status"] == "label_not_reviewed" and "yolo_txt_path" not in item
        bad = admin_api.post(f"/api/admin/images/{img.image_id}/label-review",
                             json={"decision": "approved", "label_sha256": "0" * 64})
        assert bad.status_code == 409 and "stale" in bad.text
        ok = admin_api.post(f"/api/admin/images/{img.image_id}/label-review",
                            json={"decision": "approved", "label_sha256": item["label_sha256"], "reason": "checked"})
        assert ok.status_code == 200 and ok.json()["training_eligible"] is True
        state = admin_api.get(f"/api/admin/images/{img.image_id}/label-review").json()
        assert state["status"] == "eligible" and state["reviews"][0]["reason"] == "checked"
        assert admin_api.get("/api/admin/label-reviews/pending").json()["total"] == 0
        assert admin_api.post(f"/api/admin/images/{img.image_id}/label-review",
                              json={"decision": "maybe", "label_sha256": "x"}).status_code == 422

    def test_contributor_cannot_approve_own_labels(self, db, user, tmp_path, three_cats, api):
        img = _labelled(db, user, three_cats[0], tmp_path)              # api: require_admin -> the contributor
        r = api.post(f"/api/admin/images/{img.image_id}/label-review",
                     json={"decision": "approved", "label_sha256": img.label_sha256})
        assert r.status_code == 403 and "independent" in r.text
        assert _reason(db, img)[0] is False


@pytest.mark.skipif("test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
                    reason="real-JWT access test only runs against an isolated *test* database")
@pytest.mark.parametrize("method,url", [("get", "/api/admin/label-reviews/pending"),
                                        ("get", "/api/admin/images/x/label-review"),
                                        ("post", "/api/admin/images/x/label-review")])
def test_label_review_endpoints_require_admin(client, user_auth, method, url):
    kw = {"json": {"decision": "approved", "label_sha256": "x"}} if method == "post" else {}
    assert getattr(client, method)(url, **kw).status_code == 401
    assert getattr(client, method)(url, headers=user_auth["headers"], **kw).status_code == 403
