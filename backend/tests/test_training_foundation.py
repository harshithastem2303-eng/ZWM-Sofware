"""
ZWM v1.1.0 Block A1 — training dataset foundation tests.

Covers: YOLO class mapping, training eligibility, total-image threshold,
cumulative milestones, overflow, snapshot immutability, duplicate protection.

Isolation: these tests NEVER touch the application database. They run on a
per-test SQLite file by default, or on a dedicated throwaway PostgreSQL database
when ZWM_A1_TEST_DATABASE_URL is set (its name must contain "test").
Images and labels are written under pytest's tmp_path.
"""
import os
import threading
import uuid
from io import BytesIO

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base
import app.models  # noqa: F401  (register all tables)
from app.models.annotation import Annotation
from app.models.category import Category
from app.models.image import Image
from app.models.setting import SystemSetting
from app.models.training import (
    SnapshotImmutableError,
    TrainingDataProtectedError,
    TrainingSnapshot,
    TrainingSnapshotImage,
)
from app.models.user import User
from app.routes.annotation import _generate_yolo_txt_for_image
from app.services import training_dataset_service as tds
from app.services.lifecycle_service import promote_to_permanent
from app.services.training_service import check_dataset_readiness


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _png_bytes() -> bytes:
    from PIL import Image as PILImage
    buf = BytesIO()
    PILImage.new("RGB", (200, 200), color=(10, 120, 40)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _png_bytes()


@pytest.fixture()
def engine(tmp_path):
    pg_url = os.getenv("ZWM_A1_TEST_DATABASE_URL")
    if pg_url:
        if "test" not in pg_url.rsplit("/", 1)[-1].lower():
            pytest.fail("ZWM_A1_TEST_DATABASE_URL must point to a dedicated *test* database")
        eng = create_engine(pg_url)
        Base.metadata.drop_all(eng)
    else:
        eng = create_engine(
            f"sqlite:///{tmp_path / 'a1.db'}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    Base.metadata.create_all(eng)
    yield eng
    if pg_url:
        Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def Session(engine):
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture()
def queued(monkeypatch):
    """Celery stub: records job ids instead of contacting the broker (Block A2)."""
    from app.services import training_pipeline_service as tps
    sent = []
    monkeypatch.setattr(tps, "_send_to_queue", lambda job_id: sent.append(job_id) or f"task-{job_id}")
    return sent


@pytest.fixture()
def db(Session, tmp_path, monkeypatch, queued):
    monkeypatch.setattr(settings, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "TRAINING_DATASETS_DIR", str(tmp_path / "snapshot_datasets"))
    monkeypatch.setattr(settings, "CANDIDATE_MODELS_DIR", str(tmp_path / "candidates"))
    session = Session()
    session.add(SystemSetting(id=1, auto_retrain_count=100))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def user(db):
    u = User(email=f"a1_{uuid.uuid4().hex[:8]}@test.com", password_hash="x", role="user")
    db.add(u)
    db.commit()
    return u


def _category(db, name, code, active=True):
    c = Category(class_name=name, class_code=code, is_active=active)
    db.add(c)
    db.commit()
    return c


def _set_threshold(db, value):
    s = db.query(SystemSetting).filter(SystemSetting.id == 1).one()
    s.auto_retrain_count = value
    db.commit()


def _uploaded_image(db, user, category, tmp_path):
    temp_dir = tmp_path / "uploads" / "temporary" / user.user_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    image_id = str(uuid.uuid4())
    path = temp_dir / f"{image_id}.png"
    path.write_bytes(_PNG)
    img = Image(
        image_id=image_id,
        user_id=user.user_id,
        original_filename=f"{image_id}.png",
        temp_s3_path=str(path),
        selected_category_id=category.category_id if category else None,
        status="uploaded",
    )
    db.add(img)
    db.commit()
    return img


def _annotate(db, user, img, category_id):
    db.add(Annotation(
        image_id=img.image_id,
        category_id=category_id,
        annotated_by=user.user_id,
        annotation_type="rectangle",
        label_data_json={"points": [{"x": 10, "y": 20}, {"x": 110, "y": 120}]},
        image_width=200,
        image_height=200,
    ))
    img.status = "annotated"
    db.commit()


def _complete_image(db, user, category, tmp_path):
    """Real pipeline: upload -> annotate -> YOLO TXT -> permanent promotion -> finish labeling."""
    img = _uploaded_image(db, user, category, tmp_path)
    _annotate(db, user, img, category.category_id)
    txt = _generate_yolo_txt_for_image(img.image_id, db)
    assert txt is not None
    result = promote_to_permanent(db, img.image_id, txt)
    assert result["success"], result
    tds.finalize_image_labeling(db, img.image_id)
    db.refresh(img)
    return img


REVIEWER_ID, REVIEWER_EMAIL = "a60-reviewer-admin-0001", "a60-reviewer@example.com"


def _approve_label(db, img, reviewer_id=REVIEWER_ID, reviewer_email=REVIEWER_EMAIL):
    """Block A6.0: an independent administrator approves the finalized label revision
    (needed only when the revision involves AI; human-only labels are eligible on finalize)."""
    db.refresh(img)
    return tds.review_label_revision(db, img.image_id, reviewer_id=reviewer_id, reviewer_email=reviewer_email,
                                     decision="approved", label_sha256=img.label_sha256)


def _complete_many(db, user, cats_and_counts, tmp_path):
    out = []
    for cat, n in cats_and_counts:
        for _ in range(n):
            out.append(_complete_image(db, user, cat, tmp_path))
    return out


def _snapshots(db):
    db.expire_all()
    return db.query(TrainingSnapshot).order_by(TrainingSnapshot.version).all()


def _snapshot_ids(db, snap):
    return tds.get_snapshot_image_ids(db, snap.snapshot_id)


# ---------------------------------------------------------------------------
# A. YOLO class mapping
# ---------------------------------------------------------------------------

class TestYoloClassMapping:
    def test_business_codes_map_to_contiguous_indices(self, db):
        c101 = _category(db, "Cat A", 101)
        c109 = _category(db, "Cat B", 109)
        c500 = _category(db, "Cat C", 500)

        mapping = tds.ensure_yolo_class_indices(db)

        assert mapping[c101.category_id] == 0
        assert mapping[c109.category_id] == 1
        assert mapping[c500.category_id] == 2
        assert sorted(mapping.values()) == list(range(len(mapping)))

    def test_mapping_is_stable_and_never_renumbered(self, db):
        a = _category(db, "Cat A", 500)
        b = _category(db, "Cat B", 101)
        first = tds.ensure_yolo_class_indices(db)
        c = _category(db, "Cat C", 1)  # lowest business code, created last
        second = tds.ensure_yolo_class_indices(db)

        assert second[a.category_id] == first[a.category_id] == 0
        assert second[b.category_id] == first[b.category_id] == 1
        assert second[c.category_id] == 2

    def test_txt_uses_yolo_index_not_business_code(self, db, user, tmp_path):
        _category(db, "Cat A", 101)
        _category(db, "Cat B", 109)
        c500 = _category(db, "Cat C", 500)

        img = _uploaded_image(db, user, c500, tmp_path)
        _annotate(db, user, img, c500.category_id)
        txt = _generate_yolo_txt_for_image(img.image_id, db)

        with open(txt) as fh:
            class_ids = [int(line.split()[0]) for line in fh if line.strip()]
        assert class_ids == [2]
        assert 500 not in class_ids
        # Business code preserved separately
        db.refresh(c500)
        assert c500.class_code == 500 and c500.yolo_class_index == 2

    def test_snapshot_freezes_class_map(self, db, user, tmp_path):
        _set_threshold(db, 2)
        c = _category(db, "Cat A", 101)
        _complete_many(db, user, [(c, 2)], tmp_path)
        snap = _snapshots(db)[0]
        assert snap.class_map == [{
            "yolo_index": 0, "category_id": c.category_id,
            "class_code": 101, "class_name": "Cat A", "is_active": True,
        }]


# ---------------------------------------------------------------------------
# B. Eligibility
# ---------------------------------------------------------------------------

class TestEligibility:
    def test_uploaded_unlabeled_is_not_eligible(self, db, user, tmp_path):
        c = _category(db, "Cat A", 101)
        img = _uploaded_image(db, user, c, tmp_path)
        assert img.training_eligible_at is None
        assert img.training_sequence is None
        assert tds.evaluate_training_eligibility(db, img)[0] is False
        assert tds.count_training_eligible_images(db) == 0

    def test_failed_yolo_generation_is_not_eligible(self, db, user, tmp_path):
        # Valid annotation shape, but no valid category -> no YOLO line can be generated
        img = _uploaded_image(db, user, None, tmp_path)
        _annotate(db, user, img, None)
        assert _generate_yolo_txt_for_image(img.image_id, db) is None
        db.refresh(img)
        assert img.training_sequence is None
        assert tds.count_training_eligible_images(db) == 0

    def test_invalid_yolo_txt_is_not_eligible(self, db, user, tmp_path):
        c = _category(db, "Cat A", 101)
        img = _uploaded_image(db, user, c, tmp_path)
        _annotate(db, user, img, c.category_id)
        bad = tmp_path / "bad.txt"
        bad.write_text("0 1.5 0.5 0.2 0.2\n")  # out-of-range coordinate
        result = promote_to_permanent(db, img.image_id, str(bad))
        db.refresh(img)
        assert result["success"] is False
        assert img.status == "conversion_failed"
        assert img.training_sequence is None
        assert tds.count_training_eligible_images(db) == 0

    def test_business_code_label_is_not_eligible(self, db, user, tmp_path):
        """A legacy-style TXT with class_code as class id must never be counted."""
        c = _category(db, "Cat A", 101)
        tds.ensure_yolo_class_indices(db)
        img = _uploaded_image(db, user, c, tmp_path)
        _annotate(db, user, img, c.category_id)
        legacy = tmp_path / "legacy.txt"
        legacy.write_text("101 0.5 0.5 0.2 0.2\n")
        result = promote_to_permanent(db, img.image_id, str(legacy))
        db.refresh(img)
        assert result["success"] is True  # promotion behaviour unchanged
        assert img.training_sequence is None

    def test_full_pipeline_is_eligible_without_admin_approval(self, db, user, tmp_path):
        c = _category(db, "Cat A", 101)
        img = _complete_image(db, user, c, tmp_path)
        assert img.status == "permanent"
        assert img.reviewed_by is None
        assert img.training_eligible_at is not None
        assert img.training_sequence == 1
        assert tds.count_training_eligible_images(db) == 1

    def test_inactive_category_keeps_historical_eligibility(self, db, user, tmp_path):
        c = _category(db, "Cat A", 101)
        img = _complete_image(db, user, c, tmp_path)
        c.is_active = False
        db.commit()
        assert tds.count_training_eligible_images(db) == 1
        db.refresh(img)
        assert img.training_sequence == 1

    def test_new_image_of_archived_category_is_not_eligible(self, db, user, tmp_path):
        c = _category(db, "Cat A", 101)
        tds.ensure_yolo_class_indices(db)
        c.is_active = False
        db.commit()
        img = _uploaded_image(db, user, c, tmp_path)
        _annotate(db, user, img, c.category_id)
        with pytest.raises(tds.LabelingFinalizationError, match="inactive_category"):
            tds.finalize_image_labeling(db, img.image_id)
        db.refresh(img)
        assert img.training_sequence is None
        assert tds.count_training_eligible_images(db) == 0

    def test_training_sequence_is_stable_insertion_order(self, db, user, tmp_path):
        a = _category(db, "Zeta", 999)
        b = _category(db, "Alpha", 1)
        imgs = [_complete_image(db, user, cat, tmp_path) for cat in (a, b, a, b)]
        assert [i.training_sequence for i in imgs] == [1, 2, 3, 4]


# ---------------------------------------------------------------------------
# C-H. Total threshold, milestones, overflow, immutability
# ---------------------------------------------------------------------------

@pytest.fixture()
def three_cats(db):
    return (
        _category(db, "Cat A", 101),
        _category(db, "Cat B", 102),
        _category(db, "Cat C", 109),
    )


class TestTotalThresholdAndMilestones:
    def test_c_total_threshold_not_per_category(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        _complete_many(db, user, [(a, 50), (b, 30), (c, 20)], tmp_path)

        assert tds.count_training_eligible_images(db) == 100
        snaps = _snapshots(db)
        assert len(snaps) == 1 and snaps[0].dataset_size == 100
        # Readiness API: total-based, never per-category (no category has 100)
        _, stats = check_dataset_readiness(db)
        assert {s["training_eligible_count"] for s in stats} == {50, 30, 20}

    def test_c_readiness_true_at_total(self, db, user, tmp_path, three_cats, monkeypatch):
        a, b, c = three_cats
        # Disable auto-snapshot to observe readiness before locking
        monkeypatch.setattr(tds, "create_next_snapshot_if_ready", lambda db: None)
        _complete_many(db, user, [(a, 50), (b, 30), (c, 20)], tmp_path)
        ready, _ = check_dataset_readiness(db)
        progress = tds.get_training_progress(db)
        assert ready is True
        assert progress["total_training_eligible_images"] == 100
        assert progress["next_milestone"] == 100

    def test_d_below_threshold(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        _complete_many(db, user, [(a, 50), (b, 30), (c, 19)], tmp_path)
        assert _snapshots(db) == []
        p = tds.get_training_progress(db)
        assert p["total_training_eligible_images"] == 99
        assert p["next_milestone"] == 100
        assert p["remaining_to_next_milestone"] == 1
        assert p["ready"] is False

    def test_e_exact_threshold(self, db, user, tmp_path, three_cats):
        a, _, _ = three_cats
        imgs = _complete_many(db, user, [(a, 100)], tmp_path)
        snaps = _snapshots(db)
        assert len(snaps) == 1
        assert snaps[0].version == 1
        assert snaps[0].milestone_count == 100
        assert snaps[0].dataset_size == 100
        assert snaps[0].status == "locked"
        assert _snapshot_ids(db, snaps[0]) == [i.image_id for i in imgs]

    def test_f_overflow(self, db, user, tmp_path, three_cats):
        a, b, _ = three_cats
        imgs = _complete_many(db, user, [(a, 60), (b, 50)], tmp_path)
        snaps = _snapshots(db)
        assert len(snaps) == 1
        ids = _snapshot_ids(db, snaps[0])
        assert len(ids) == 100
        assert ids == [i.image_id for i in imgs[:100]]
        assert not set(ids) & {i.image_id for i in imgs[100:]}

        p = tds.get_training_progress(db)
        assert p["total_training_eligible_images"] == 110
        assert p["images_since_last_milestone"] == 10
        assert p["next_milestone"] == 200
        assert p["remaining_to_next_milestone"] == 90

    def test_f_overflow_when_snapshot_created_late(self, db, user, tmp_path, three_cats, monkeypatch):
        """110 eligible already present before the first snapshot attempt."""
        a, _, _ = three_cats
        real = tds.create_next_snapshot_if_ready
        monkeypatch.setattr(tds, "create_next_snapshot_if_ready", lambda db: None)
        imgs = _complete_many(db, user, [(a, 110)], tmp_path)
        snap = real(db)
        assert snap.dataset_size == 100
        assert _snapshot_ids(db, snap) == [i.image_id for i in imgs[:100]]
        assert real(db) is None  # only 10 overflow; V2 not ready

    def test_g_second_cumulative_milestone(self, db, user, tmp_path, three_cats):
        a, b, c = three_cats
        imgs = _complete_many(db, user, [(a, 100)], tmp_path)
        imgs += _complete_many(db, user, [(b, 60), (c, 39)], tmp_path)
        assert len(imgs) == 199
        assert len(_snapshots(db)) == 1

        imgs += _complete_many(db, user, [(c, 1)], tmp_path)
        snaps = _snapshots(db)
        assert len(snaps) == 2
        v2 = snaps[1]
        assert v2.version == 2
        assert v2.milestone_count == 200
        assert v2.dataset_size == 200
        assert _snapshot_ids(db, v2) == [i.image_id for i in imgs[:200]]
        assert set(_snapshot_ids(db, snaps[0])) <= set(_snapshot_ids(db, v2))
        assert tds.get_training_progress(db)["next_milestone"] == 300

    def test_threshold_change_applies_to_next_milestone_only(self, db, user, tmp_path, three_cats):
        a, _, _ = three_cats
        _complete_many(db, user, [(a, 100)], tmp_path)
        _set_threshold(db, 500)
        p = tds.get_training_progress(db)
        assert p["last_milestone"] == 100
        assert p["next_milestone"] == 600
        v1 = _snapshots(db)[0]
        assert v1.threshold == 100 and v1.dataset_size == 100

    def test_h_snapshot_immutability(self, db, user, tmp_path, three_cats):
        a, b, _ = three_cats
        _complete_many(db, user, [(a, 100)], tmp_path)
        v1 = _snapshots(db)[0]
        before = _snapshot_ids(db, v1)

        _complete_many(db, user, [(b, 10)], tmp_path)
        v1 = _snapshots(db)[0]
        assert v1.dataset_size == 100
        assert _snapshot_ids(db, v1) == before
        assert db.query(func.count()).select_from(TrainingSnapshotImage).filter(
            TrainingSnapshotImage.snapshot_id == v1.snapshot_id
        ).scalar() == 100

    def test_h_orm_guards_reject_mutation(self, db, user, tmp_path, three_cats):
        a, _, _ = three_cats
        _set_threshold(db, 3)
        _complete_many(db, user, [(a, 3)], tmp_path)
        v1 = _snapshots(db)[0]

        v1.dataset_size = 4
        with pytest.raises(SnapshotImmutableError):
            db.commit()
        db.rollback()

        member = db.query(TrainingSnapshotImage).first()
        db.delete(member)
        with pytest.raises(SnapshotImmutableError):
            db.commit()
        db.rollback()

        v1 = _snapshots(db)[0]
        v1.status = "training"  # status is the only mutable field (Block A2)
        db.commit()


# ---------------------------------------------------------------------------
# I. Concurrency / idempotency
# ---------------------------------------------------------------------------

class TestDuplicateSnapshotProtection:
    @pytest.fixture()
    def ready_110(self, db, user, tmp_path, three_cats, monkeypatch):
        a, _, _ = three_cats
        real = tds.create_next_snapshot_if_ready
        monkeypatch.setattr(tds, "create_next_snapshot_if_ready", lambda db: None)
        _complete_many(db, user, [(a, 110)], tmp_path)
        monkeypatch.setattr(tds, "create_next_snapshot_if_ready", real)
        return real

    def _count_for(self, db, milestone):
        db.expire_all()
        return db.query(TrainingSnapshot).filter(TrainingSnapshot.milestone_count == milestone).count()

    def test_repeated_calls_are_idempotent(self, db, ready_110):
        assert ready_110(db) is not None
        assert ready_110(db) is None
        assert self._count_for(db, 100) == 1

    def test_stale_reader_hits_unique_constraint(self, db, Session, ready_110, monkeypatch):
        """Second request computed 'next = 100' before the first committed."""
        assert ready_110(db) is not None

        stale = Session()
        stale_progress = {
            "total_training_eligible_images": 110, "threshold": 100,
            "last_milestone": 0, "next_milestone": 100,
            "remaining_to_next_milestone": 0, "images_since_last_milestone": 110,
            "ready": True, "snapshot_count": 0,
        }
        monkeypatch.setattr(tds, "get_training_progress", lambda _db: dict(stale_progress))
        try:
            assert tds.create_next_snapshot_if_ready(stale) is None
        finally:
            stale.close()
        assert self._count_for(db, 100) == 1

    def test_concurrent_threads_create_one_snapshot(self, db, Session, ready_110):
        barrier = threading.Barrier(4)
        results, errors = [], []

        def worker():
            s = Session()
            try:
                barrier.wait()
                results.append(tds.create_next_snapshot_if_ready(s))
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                s.close()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert sum(1 for r in results if r is not None) == 1
        assert self._count_for(db, 100) == 1
        assert db.query(TrainingSnapshot).count() == 1


# ---------------------------------------------------------------------------
# Integrity 1: snapshotted / eligible images cannot be hard-deleted
# ---------------------------------------------------------------------------

@pytest.fixture()
def api(db, user, monkeypatch):
    """TestClient bound to the isolated test DB; auth resolves to ``user`` / admin."""
    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    from app.database import get_db
    from app.dependencies.auth import get_current_user, require_admin
    from app.services import lifecycle_service

    # Never let admin routes scan/purge the real repository dataset folders.
    monkeypatch.setattr(lifecycle_service, "delete_dataset_category_folder", lambda *a, **k: None)
    monkeypatch.setattr(lifecycle_service, "sync_dataset_folders_with_db", lambda *a, **k: None)

    fastapi_app.dependency_overrides[get_db] = lambda: db
    fastapi_app.dependency_overrides[get_current_user] = lambda: user
    fastapi_app.dependency_overrides[require_admin] = lambda: user
    try:
        yield TestClient(fastapi_app)
    finally:
        fastapi_app.dependency_overrides.clear()


class TestSnapshotImageDeletionProtection:
    def test_delete_route_rejects_snapshotted_image(self, db, user, tmp_path, api, three_cats):
        a, _, _ = three_cats
        _set_threshold(db, 5)
        imgs = _complete_many(db, user, [(a, 5)], tmp_path)
        v1 = _snapshots(db)[0]
        before = _snapshot_ids(db, v1)
        victim = imgs[2]

        r = api.delete(f"/api/images/{victim.image_id}")
        assert r.status_code == 409
        assert "snapshot" in r.text

        db.expire_all()
        img = db.query(Image).filter(Image.image_id == victim.image_id).one()
        assert os.path.isfile(img.permanent_s3_path)
        assert os.path.isfile(img.yolo_txt_path)
        assert _snapshot_ids(db, _snapshots(db)[0]) == before
        assert tds.count_training_eligible_images(db) == 5

    def test_delete_route_rejects_eligible_not_yet_snapshotted(self, db, user, tmp_path, api, three_cats):
        a, _, _ = three_cats
        img = _complete_image(db, user, a, tmp_path)
        assert _snapshots(db) == []
        r = api.delete(f"/api/images/{img.image_id}")
        assert r.status_code == 409
        db.expire_all()
        assert db.query(Image).filter(Image.image_id == img.image_id).count() == 1

    def test_delete_route_still_allows_non_eligible_image(self, db, user, tmp_path, api, three_cats):
        """v1.0.0 behaviour preserved for images that are not training data."""
        a, _, _ = three_cats
        img = _uploaded_image(db, user, a, tmp_path)
        r = api.delete(f"/api/images/{img.image_id}")
        assert r.status_code == 200
        db.expire_all()
        assert db.query(Image).filter(Image.image_id == img.image_id).count() == 0

    def test_orm_backstop_blocks_any_hard_delete_of_snapshot_image(self, db, user, tmp_path, three_cats):
        a, _, _ = three_cats
        _set_threshold(db, 2)
        imgs = _complete_many(db, user, [(a, 2)], tmp_path)
        db.delete(db.query(Image).filter(Image.image_id == imgs[0].image_id).one())
        with pytest.raises(TrainingDataProtectedError):
            db.commit()
        db.rollback()
        # Cascade path (user deletion -> images) is blocked as well
        db.delete(db.query(User).filter(User.user_id == user.user_id).one())
        with pytest.raises(TrainingDataProtectedError):
            db.commit()
        db.rollback()
        assert len(_snapshot_ids(db, _snapshots(db)[0])) == 2


# ---------------------------------------------------------------------------
# Integrity 2: category deletion never breaks YOLO 0..N-1
# ---------------------------------------------------------------------------

class TestCategoryDeletionVsYoloIndex:
    def test_delete_indexed_category_archives_and_keeps_contiguous_map(self, db, api):
        pet = _category(db, "PET", 101)
        mlp = _category(db, "MLP", 102)
        hdpe = _category(db, "HDPE", 109)
        tds.ensure_yolo_class_indices(db)

        r = api.delete(f"/api/admin/categories/{mlp.category_id}")
        assert r.status_code == 200
        assert r.json()["archived"] is True

        db.expire_all()
        archived = db.query(Category).filter(Category.category_id == mlp.category_id).one()
        assert archived.is_active is False
        assert archived.yolo_class_index == 1
        class_map = tds.get_class_map(db)
        assert [c["yolo_index"] for c in class_map] == [0, 1, 2]
        assert [c["class_code"] for c in class_map] == [101, 102, 109]
        assert [c["is_active"] for c in class_map] == [True, False, True]

        new = _category(db, "LDPE", 104)
        mapping = tds.ensure_yolo_class_indices(db)
        assert mapping[new.category_id] == 3
        assert mapping[pet.category_id] == 0 and mapping[hdpe.category_id] == 2

    def test_archived_category_images_keep_labels_and_history(self, db, user, tmp_path, api):
        pet = _category(db, "PET", 101)
        mlp = _category(db, "MLP", 102)
        _complete_image(db, user, pet, tmp_path)
        m_img = _complete_image(db, user, mlp, tmp_path)
        api.delete(f"/api/admin/categories/{mlp.category_id}")
        db.expire_all()
        ann = db.query(Annotation).filter(Annotation.image_id == m_img.image_id).one()
        assert ann.category_id == mlp.category_id  # FK not nulled
        txt_path = db.query(Image).filter(Image.image_id == m_img.image_id).one().yolo_txt_path
        with open(txt_path) as fh:
            assert fh.read().split()[0] == "1"
        assert tds.count_training_eligible_images(db) == 2

    def test_orm_backstop_blocks_hard_delete_of_indexed_category(self, db):
        c = _category(db, "PET", 101)
        tds.ensure_yolo_class_indices(db)
        db.delete(c)
        with pytest.raises(TrainingDataProtectedError):
            db.commit()
        db.rollback()

    def test_unindexed_category_still_hard_deletes(self, db, api):
        """v1.0.0 behaviour preserved for categories with no YOLO history."""
        c = _category(db, "a1-never-indexed", 4242)
        assert c.yolo_class_index is None
        r = api.delete(f"/api/admin/categories/{c.category_id}")
        assert r.status_code == 200
        db.expire_all()
        assert db.query(Category).filter(Category.category_id == c.category_id).count() == 0

    def test_class_map_gap_is_detected_not_renumbered(self, db):
        _category(db, "PET", 101)
        _category(db, "HDPE", 109)
        tds.ensure_yolo_class_indices(db)
        db.query(Category).filter(Category.class_code == 109).update({"yolo_class_index": 5})
        db.commit()
        with pytest.raises(tds.ClassMapIntegrityError):
            tds.get_class_map(db)
        db.expire_all()
        assert db.query(Category).filter(Category.class_code == 109).one().yolo_class_index == 5


# ---------------------------------------------------------------------------
# Integrity 3: snapshot creation failure is recoverable and idempotent
# ---------------------------------------------------------------------------

def _fail_class_map(monkeypatch, times):
    """Make snapshot creation fail ``times`` times (None = always)."""
    real = tds.get_class_map
    state = {"left": times}

    def flaky(db):
        if state["left"] is None or state["left"] > 0:
            if state["left"] is not None:
                state["left"] -= 1
            raise RuntimeError("simulated snapshot failure")
        return real(db)

    monkeypatch.setattr(tds, "get_class_map", flaky)
    return lambda: monkeypatch.setattr(tds, "get_class_map", real)


class TestSnapshotFailureRecovery:
    def test_failure_at_milestone_does_not_break_promotion_or_lose_milestone(
        self, db, user, tmp_path, three_cats, monkeypatch
    ):
        a, b, _ = three_cats
        imgs = _complete_many(db, user, [(a, 99)], tmp_path)
        _fail_class_map(monkeypatch, 1)

        imgs.append(_complete_image(db, user, b, tmp_path))  # 100th: promotion OK, snapshot fails
        assert imgs[-1].status == "permanent"
        assert _snapshots(db) == []
        p = tds.get_training_progress(db)
        assert p["ready"] is True and p["next_milestone"] == 100

        created = tds.reconcile_training_snapshots(db)
        assert len(created) == 1
        assert tds.reconcile_training_snapshots(db) == []
        snaps = _snapshots(db)
        assert len(snaps) == 1 and snaps[0].version == 1 and snaps[0].dataset_size == 100
        assert _snapshot_ids(db, snaps[0]) == [i.image_id for i in imgs]

    def test_next_promotion_retries_automatically_with_exact_size(
        self, db, user, tmp_path, three_cats, monkeypatch
    ):
        a, _, _ = three_cats
        _fail_class_map(monkeypatch, 1)
        imgs = _complete_many(db, user, [(a, 101)], tmp_path)
        snaps = _snapshots(db)
        assert len(snaps) == 1
        assert snaps[0].dataset_size == 100
        assert _snapshot_ids(db, snaps[0]) == [i.image_id for i in imgs[:100]]
        assert tds.get_training_progress(db)["images_since_last_milestone"] == 1

    def test_reconcile_catches_up_multiple_missed_milestones(
        self, db, user, tmp_path, three_cats, monkeypatch
    ):
        a, _, _ = three_cats
        restore = _fail_class_map(monkeypatch, None)
        imgs = _complete_many(db, user, [(a, 205)], tmp_path)
        assert _snapshots(db) == []
        restore()

        created = tds.reconcile_training_snapshots(db)
        assert [s.milestone_count for s in created] == [100, 200]
        snaps = _snapshots(db)
        assert [s.dataset_size for s in snaps] == [100, 200]
        assert _snapshot_ids(db, snaps[1]) == [i.image_id for i in imgs[:200]]
        assert tds.reconcile_training_snapshots(db) == []

    def test_reconcile_endpoint_is_idempotent(self, db, user, tmp_path, three_cats, api, monkeypatch):
        a, _, _ = three_cats
        _set_threshold(db, 3)
        _fail_class_map(monkeypatch, 1)
        _complete_many(db, user, [(a, 3)], tmp_path)
        assert _snapshots(db) == []
        r1 = api.post("/api/dataset/snapshots/reconcile")
        r2 = api.post("/api/dataset/snapshots/reconcile")
        assert r1.status_code == 200 and r1.json()["count"] == 1
        assert r2.status_code == 200 and r2.json()["count"] == 0
        assert len(_snapshots(db)) == 1


# ---------------------------------------------------------------------------
# Final closure: historical eligibility, frozen annotations, multi-object save
# ---------------------------------------------------------------------------

_RECT_1 = {"points": [{"x": 10, "y": 20}, {"x": 110, "y": 120}]}
_RECT_2 = {"points": [{"x": 120, "y": 130}, {"x": 190, "y": 190}]}


def _api_annotate(api, img, cat, label=_RECT_1):
    """Exactly what the frontend sends: one POST per drawn object."""
    return api.post("/api/annotations/", json={
        "image_id": img.image_id,
        "annotation_type": "rectangle",
        "label_data": label,
        "category_id": cat.category_id,
        "image_width": 200,
        "image_height": 200,
        "ai_generated": False,
    })


def _first_annotation(db, img):
    db.expire_all()
    return (
        db.query(Annotation)
        .filter(Annotation.image_id == img.image_id)
        .order_by(Annotation.annotated_at)
        .first()
    )


def _label_lines(db, img):
    db.expire_all()
    path = db.query(Image).filter(Image.image_id == img.image_id).one().yolo_txt_path
    with open(path) as fh:
        return [line.split() for line in fh if line.strip()]


class TestCumulativeInvariantAfterArchive:
    def test_v1_subset_of_v2_with_archive_and_blocked_mutations(self, db, user, tmp_path, api, three_cats):
        pet, mlp, hdpe = three_cats
        _set_threshold(db, 5)

        # A1..A5 -> V1 (includes MLP images that will be archived)
        a_imgs = _complete_many(db, user, [(pet, 2), (mlp, 2), (hdpe, 1)], tmp_path)
        v1 = _snapshots(db)[0]
        v1_ids = _snapshot_ids(db, v1)
        assert v1_ids == [i.image_id for i in a_imgs]
        map_before = tds.get_class_map(db)

        # 1. Archive MLP
        r = api.delete(f"/api/admin/categories/{mlp.category_id}")
        assert r.status_code == 200 and r.json()["archived"] is True
        assert tds.count_training_eligible_images(db) == 5

        # 2. Delete a V1 annotation -> blocked
        mlp_img = a_imgs[2]
        ann = _first_annotation(db, mlp_img)
        assert api.delete(f"/api/annotations/{ann.annotation_id}").status_code == 409

        # 3. Update a V1 annotation (category / geometry) -> blocked
        assert api.put(f"/api/annotations/{ann.annotation_id}",
                       json={"category_id": pet.category_id}).status_code == 409
        assert api.put(f"/api/annotations/{ann.annotation_id}",
                       json={"label_data": _RECT_2}).status_code == 409

        db.expire_all()
        assert _first_annotation(db, mlp_img).category_id == mlp.category_id
        assert _label_lines(db, mlp_img) == [["1", "0.300000", "0.350000", "0.500000", "0.500000"]]
        assert _snapshot_ids(db, _snapshots(db)[0]) == v1_ids

        # New MLP image cannot become eligible while archived
        archived_new = _uploaded_image(db, user, mlp, tmp_path)
        _annotate(db, user, archived_new, mlp.category_id)
        with pytest.raises(tds.LabelingFinalizationError):
            tds.finalize_image_labeling(db, archived_new.image_id)
        db.refresh(archived_new)
        assert archived_new.training_sequence is None

        # B1..B5 from active categories -> V2
        b_imgs = _complete_many(db, user, [(pet, 3), (hdpe, 2)], tmp_path)
        snaps = _snapshots(db)
        assert len(snaps) == 2
        v1, v2 = snaps
        v2_ids = _snapshot_ids(db, v2)

        assert v1.dataset_size == 5
        assert v2.dataset_size == 10 and v2.milestone_count == 10
        assert v2_ids == [i.image_id for i in a_imgs + b_imgs]
        assert set(v1_ids) <= set(v2_ids)
        assert {a_imgs[2].image_id, a_imgs[3].image_id} <= set(v2_ids)  # archived MLP history
        assert archived_new.image_id not in v2_ids

        # YOLO mapping unchanged; archived class keeps its index
        map_after = tds.get_class_map(db)
        assert [(c["yolo_index"], c["category_id"]) for c in map_after] == \
               [(c["yolo_index"], c["category_id"]) for c in map_before]
        assert v2.class_map[1]["category_id"] == mlp.category_id and v2.class_map[1]["is_active"] is False

    def test_v1_v2_v3_chain_with_threshold_100(self, db, user, tmp_path, api, three_cats):
        pet, mlp, hdpe = three_cats
        a = _complete_many(db, user, [(pet, 50), (mlp, 30), (hdpe, 20)], tmp_path)
        api.delete(f"/api/admin/categories/{pet.category_id}")
        b = _complete_many(db, user, [(mlp, 60), (hdpe, 40)], tmp_path)
        c = _complete_many(db, user, [(hdpe, 100)], tmp_path)
        v1, v2, v3 = _snapshots(db)
        ids1, ids2, ids3 = (_snapshot_ids(db, s) for s in (v1, v2, v3))
        assert (len(ids1), len(ids2), len(ids3)) == (100, 200, 300)
        assert set(ids1) < set(ids2) < set(ids3)
        assert ids3 == [i.image_id for i in a + b + c]


class TestAnnotationDeleteProtection:
    def test_non_eligible_annotation_delete_allowed(self, db, user, tmp_path, api, three_cats):
        pet, _, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _annotate(db, user, img, pet.category_id)
        ann = _first_annotation(db, img)
        assert api.delete(f"/api/annotations/{ann.annotation_id}").status_code == 200
        db.expire_all()
        assert db.query(Annotation).filter(Annotation.image_id == img.image_id).count() == 0

    def test_eligible_annotation_delete_blocked(self, db, user, tmp_path, api, three_cats):
        pet, _, _ = three_cats
        img = _complete_image(db, user, pet, tmp_path)
        assert _snapshots(db) == []
        ann = _first_annotation(db, img)
        r = api.delete(f"/api/annotations/{ann.annotation_id}")
        assert r.status_code == 409
        db.expire_all()
        img = db.query(Image).filter(Image.image_id == img.image_id).one()
        assert db.query(Annotation).filter(Annotation.annotation_id == ann.annotation_id).count() == 1
        assert os.path.isfile(img.yolo_txt_path)
        assert img.training_sequence == 1 and img.training_eligible_at is not None
        assert tds.count_training_eligible_images(db) == 1

    def test_snapshotted_annotation_delete_blocked(self, db, user, tmp_path, api, three_cats):
        pet, _, _ = three_cats
        _set_threshold(db, 1)
        img = _complete_image(db, user, pet, tmp_path)
        assert len(_snapshots(db)) == 1
        ann = _first_annotation(db, img)
        assert api.delete(f"/api/annotations/{ann.annotation_id}").status_code == 409
        assert _snapshot_ids(db, _snapshots(db)[0]) == [img.image_id]

    def test_orm_backstop_blocks_eligible_annotation_delete(self, db, user, tmp_path, three_cats):
        pet, _, _ = three_cats
        img = _complete_image(db, user, pet, tmp_path)
        db.delete(_first_annotation(db, img))
        with pytest.raises(TrainingDataProtectedError):
            db.commit()
        db.rollback()


class TestAnnotationUpdateProtection:
    def test_non_eligible_annotation_update_allowed(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _annotate(db, user, img, pet.category_id)
        ann = _first_annotation(db, img)
        r = api.put(f"/api/annotations/{ann.annotation_id}",
                    json={"category_id": mlp.category_id, "label_data": _RECT_2})
        assert r.status_code == 200
        assert r.json()["category_id"] == mlp.category_id

    def test_eligible_annotation_update_blocked(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        img = _complete_image(db, user, pet, tmp_path)
        before = _label_lines(db, img)
        ann = _first_annotation(db, img)
        for body in (
            {"category_id": mlp.category_id},
            {"label_data": _RECT_2},
            {"annotation_type": "polygon"},
            {"image_width": 400},
            {"ai_generated": True},   # A6.0: provenance is part of the frozen label evidence
        ):
            assert api.put(f"/api/annotations/{ann.annotation_id}", json=body).status_code == 409
        db.expire_all()
        ann = _first_annotation(db, img)
        assert ann.category_id == pet.category_id and ann.label_data_json == _RECT_1
        assert not ann.ai_generated
        assert _label_lines(db, img) == before

    def test_snapshotted_annotation_update_blocked(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        _set_threshold(db, 1)
        img = _complete_image(db, user, pet, tmp_path)
        ann = _first_annotation(db, img)
        assert api.put(f"/api/annotations/{ann.annotation_id}",
                       json={"category_id": mlp.category_id}).status_code == 409

    def test_orm_backstop_blocks_eligible_annotation_update(self, db, user, tmp_path, three_cats):
        pet, mlp, _ = three_cats
        img = _complete_image(db, user, pet, tmp_path)
        ann = _first_annotation(db, img)
        ann.category_id = mlp.category_id
        with pytest.raises(TrainingDataProtectedError):
            db.commit()
        db.rollback()


_RECT_3 = {"points": [{"x": 5, "y": 150}, {"x": 60, "y": 195}]}


def _finalize(api, img):
    return api.post(f"/api/annotations/image/{img.image_id}/finalize")


def _reload(db, img):
    db.expire_all()
    return db.query(Image).filter(Image.image_id == img.image_id).one()


def _file_digest(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _state_fingerprint(db, root):
    """DB + filesystem fingerprint used to prove dry-runs change nothing."""
    db.expire_all()
    images = sorted(
        (i.image_id, i.status, i.training_sequence, str(i.training_eligible_at), i.yolo_txt_path)
        for i in db.query(Image).all()
    )
    snaps = sorted(
        (m.snapshot_id, m.image_id, m.position) for m in db.query(TrainingSnapshotImage).all()
    )
    files = {}
    for dirpath, _, names in os.walk(root):
        for n in names:
            full = os.path.join(dirpath, n)
            files[full] = _file_digest(full)
    return images, snaps, files


class TestFinishLabeling:
    def test_three_objects_finalize_into_one_label(self, db, user, tmp_path, api, three_cats):
        pet, mlp, hdpe = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)

        for cat, rect in ((pet, _RECT_1), (mlp, _RECT_2), (hdpe, _RECT_3)):
            assert _api_annotate(api, img, cat, rect).status_code == 201
            img = _reload(db, img)
            assert img.training_sequence is None          # never eligible before finalize
            assert tds.count_training_eligible_images(db) == 0
        assert img.status == "permanent"                   # promoted by first object, kept

        r = _finalize(api, img)
        assert r.status_code == 200, r.text
        assert r.json()["already_finalized"] is False
        img = _reload(db, img)
        assert img.training_sequence == 1
        assert sorted(line[0] for line in _label_lines(db, img)) == ["0", "1", "2"]
        assert tds.count_training_eligible_images(db) == 1

    def test_snapshot_only_after_finalize_with_complete_object_set(self, db, user, tmp_path, api, three_cats):
        pet, mlp, hdpe = three_cats
        _set_threshold(db, 1)
        img = _uploaded_image(db, user, pet, tmp_path)
        for cat, rect in ((pet, _RECT_1), (mlp, _RECT_2), (hdpe, _RECT_3)):
            assert _api_annotate(api, img, cat, rect).status_code == 201
            assert _snapshots(db) == []                    # no timing window: nothing locks early

        assert _finalize(api, img).status_code == 200
        snaps = _snapshots(db)
        assert len(snaps) == 1 and _snapshot_ids(db, snaps[0]) == [img.image_id]
        assert len(_label_lines(db, img)) == 3             # snapshot holds the full object set

        # Frozen afterwards: no add / update / delete
        before = _label_lines(db, img)
        assert _api_annotate(api, img, pet, _RECT_1).status_code == 409
        ann = _first_annotation(db, img)
        assert api.put(f"/api/annotations/{ann.annotation_id}", json={"label_data": _RECT_3}).status_code == 409
        assert api.delete(f"/api/annotations/{ann.annotation_id}").status_code == 409
        assert _label_lines(db, img) == before
        assert db.query(Annotation).filter(Annotation.image_id == img.image_id).count() == 3

    def test_edits_before_finalize_are_reflected_in_final_label(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, img, pet, _RECT_1)
        r2 = _api_annotate(api, img, mlp, _RECT_2)
        api.put(f"/api/annotations/{r2.json()['annotation_id']}", json={"category_id": pet.category_id})
        assert _finalize(api, img).status_code == 200
        assert [line[0] for line in _label_lines(db, img)] == ["0", "0"]

    def test_duplicate_finalize_is_idempotent_and_awards_nothing(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, img, pet, _RECT_1)
        _api_annotate(api, img, mlp, _RECT_2)
        db.refresh(user)
        points = user.reward_points
        from app.models.user import RewardTransaction
        tx_count = db.query(RewardTransaction).count()

        first = _finalize(api, img).json()
        second = _finalize(api, img).json()
        third = _finalize(api, img).json()
        assert first["already_finalized"] is False
        assert second["already_finalized"] is True and third["already_finalized"] is True
        assert first["training_sequence"] == second["training_sequence"] == third["training_sequence"]
        db.expire_all()
        assert db.query(User).filter(User.user_id == user.user_id).one().reward_points == points
        assert db.query(RewardTransaction).count() == tx_count
        assert tds.count_training_eligible_images(db) == 1

    def test_concurrent_finalize_assigns_one_sequence(self, db, Session, user, tmp_path, api, three_cats):
        if db.get_bind().dialect.name != "postgresql":
            pytest.skip("row/advisory locking semantics require PostgreSQL")
        pet, mlp, _ = three_cats
        other = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, other, pet, _RECT_1)
        _finalize(api, other)                           # sequence 1 taken
        img = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, img, pet, _RECT_1)
        _api_annotate(api, img, mlp, _RECT_2)

        barrier = threading.Barrier(4)
        results, errors = [], []

        def worker():
            s = Session()
            try:
                barrier.wait()
                results.append(tds.finalize_image_labeling(s, img.image_id))
            except Exception as exc:
                errors.append(exc)
            finally:
                s.close()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert sum(1 for r in results if not r["already_finalized"]) == 1
        assert {r["training_sequence"] for r in results} == {2}
        assert tds.count_training_eligible_images(db) == 2
        assert len(_label_lines(db, img)) == 2

    def test_invalid_annotation_set_cannot_become_eligible(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, img, pet, _RECT_1)
        # Incomplete object: no shape data
        assert api.post("/api/annotations/", json={
            "image_id": img.image_id, "category_id": pet.category_id,
        }).status_code == 201
        before = _label_lines(db, img)

        r = _finalize(api, img)
        assert r.status_code == 422 and "invalid_annotation" in r.text
        img = _reload(db, img)
        assert img.training_sequence is None
        assert _label_lines(db, img) == before
        assert tds.count_training_eligible_images(db) == 0

    def test_archived_category_object_blocks_finalize(self, db, user, tmp_path, api, three_cats):
        pet, mlp, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, img, pet, _RECT_1)
        _api_annotate(api, img, mlp, _RECT_2)
        api.delete(f"/api/admin/categories/{mlp.category_id}")  # archive
        r = _finalize(api, img)
        assert r.status_code == 422 and "inactive_category" in r.text
        assert _reload(db, img).training_sequence is None

    def test_unauthorized_user_cannot_finalize(self, db, user, tmp_path, api, three_cats):
        from app.main import app as fastapi_app
        from app.dependencies.auth import get_current_user
        pet, _, _ = three_cats
        img = _uploaded_image(db, user, pet, tmp_path)
        _api_annotate(api, img, pet, _RECT_1)

        intruder = User(email=f"x_{uuid.uuid4().hex[:6]}@test.com", password_hash="x", role="user")
        db.add(intruder)
        db.commit()
        fastapi_app.dependency_overrides[get_current_user] = lambda: intruder
        assert _finalize(api, img).status_code == 403
        assert _reload(db, img).training_sequence is None

        admin = User(email=f"a_{uuid.uuid4().hex[:6]}@test.com", password_hash="x", role="admin")
        db.add(admin)
        db.commit()
        fastapi_app.dependency_overrides[get_current_user] = lambda: admin
        assert _finalize(api, img).status_code == 200  # admins may finalize


# ---------------------------------------------------------------------------
# Historical (pre-A1) permanent image audit + backfill
# ---------------------------------------------------------------------------

@pytest.fixture()
def historical(db, user, tmp_path, three_cats):
    """
    Mix of pre-A1 permanent images, built only through the real promote path:
      eligible_snapshotted : finalized + in V1 (threshold 1)
      legacy               : TXT uses business class_code
      ready                : TXT already uses YOLO index, never finalized
      missing_label        : permanent label file gone
      no_annotations       : annotation removed after promotion
      mismatch             : TXT has 1 object, DB has 2 annotations (v1.0.0 multi-object bug)
    """
    pet, mlp, hdpe = three_cats
    _set_threshold(db, 1)
    tds.ensure_yolo_class_indices(db)
    out = {"eligible_snapshotted": _complete_image(db, user, pet, tmp_path)}
    _set_threshold(db, 1000)

    def promoted(cat, txt_body=None):
        img = _uploaded_image(db, user, cat, tmp_path)
        _annotate(db, user, img, cat.category_id)
        txt = _generate_yolo_txt_for_image(img.image_id, db)
        if txt_body is not None:
            with open(txt, "w") as fh:
                fh.write(txt_body)
        assert promote_to_permanent(db, img.image_id, txt)["success"]
        db.refresh(img)
        return img

    out["legacy"] = promoted(mlp, "102 0.300000 0.350000 0.500000 0.500000\n")
    out["ready"] = promoted(hdpe)
    out["missing_label"] = promoted(pet)
    os.remove(out["missing_label"].yolo_txt_path)
    out["no_annotations"] = promoted(pet)
    db.query(Annotation).filter(Annotation.image_id == out["no_annotations"].image_id).delete()
    db.commit()
    out["mismatch"] = promoted(pet)
    _annotate(db, user, out["mismatch"], mlp.category_id)
    db.query(Image).filter(Image.image_id == out["mismatch"].image_id).update({"status": "permanent"})
    db.commit()
    return out


class TestHistoricalAudit:
    def test_audit_classifies_old_permanent_images(self, db, historical):
        audit = tds.audit_historical_images(db)
        by_id = {r["image_id"]: r for r in audit["images"]}
        cls = {k: by_id[v.image_id]["classification"] for k, v in historical.items()}
        assert cls == {
            "eligible_snapshotted": "already_eligible",
            "legacy": "legacy_class_codes",
            "ready": "ready",
            "missing_label": "missing_label_file",
            "no_annotations": "no_annotations",
            "mismatch": "label_annotation_mismatch",
        }
        assert by_id[historical["eligible_snapshotted"].image_id]["in_snapshot"] is True
        assert audit["permanent_images"] == 6 and audit["in_snapshots"] == 1

    def test_audit_and_dry_run_change_nothing(self, db, historical, tmp_path):
        before = _state_fingerprint(db, tmp_path / "uploads")
        tds.audit_historical_images(db)
        plan = tds.backfill_historical_images(db)  # dry-run default
        assert plan["dry_run"] is True
        assert set(plan["candidates"]) == {historical["legacy"].image_id, historical["ready"].image_id}
        assert {s["classification"] for s in plan["skipped"]} == {
            "missing_label_file", "no_annotations", "label_annotation_mismatch",
        }
        assert _state_fingerprint(db, tmp_path / "uploads") == before

    def test_apply_backfill_repairs_without_touching_history(self, db, historical):
        v1 = _snapshots(db)[0]
        v1_ids = _snapshot_ids(db, v1)
        legacy = historical["legacy"]
        legacy_txt = legacy.yolo_txt_path
        original = open(legacy_txt).read()

        report = tds.backfill_historical_images(db, apply=True)
        assert report["failed"] == []
        assert [f["image_id"] for f in report["finalized"]] == [legacy.image_id, historical["ready"].image_id]
        assert [f["training_sequence"] for f in report["finalized"]] == [2, 3]  # appended after history

        assert _label_lines(db, legacy)[0][0] == "1"                     # MLP -> YOLO index 1
        assert open(legacy_txt + tds.PRE_A1_LABEL_SUFFIX).read() == original  # recovery copy kept
        snaps = _snapshots(db)
        assert len(snaps) == 1 and _snapshot_ids(db, snaps[0]) == v1_ids   # history untouched
        for key in ("missing_label", "no_annotations", "mismatch"):
            assert _reload(db, historical[key]).training_sequence is None

        again = tds.backfill_historical_images(db, apply=True)            # idempotent
        assert again["candidates"] == [] and again["finalized"] == []
