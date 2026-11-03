"""
ZWM v1.1.0 A1 / A1.1 API integration test (real JWT auth, real upload endpoint).

Upload -> multi-object annotate -> finalize -> permanent dataset -> cumulative
snapshots, through the public HTTP API only (DB is read for label-file checks).

Uses conftest's client/auth fixtures, which TRUNCATE the DATABASE_URL database:
this module refuses to run unless DATABASE_URL points at a database whose name
contains "test".
"""
import os
import threading

import pytest

from app.config import settings
from app.models.image import Image
from app.models.training import TrainingJob
from app.models.user import User
from test_annotations import _create_category, _upload_image

pytestmark = pytest.mark.skipif(
    "test" not in settings.DATABASE_URL.rsplit("/", 1)[-1].lower(),
    reason="integration test only runs against an isolated *test* database",
)

_RECTS = [
    {"points": [{"x": 10, "y": 10}, {"x": 200, "y": 150}]},
    {"points": [{"x": 300, "y": 200}, {"x": 500, "y": 400}]},
    {"points": [{"x": 600, "y": 50}, {"x": 780, "y": 300}]},
]


@pytest.fixture(autouse=True)
def no_training(monkeypatch, tmp_path):
    """Fail loudly if anything tries to run YOLO training; Celery delivery is stubbed."""
    from app.services import training_pipeline_service as tps
    from app.tasks import training_tasks
    from worker import training_worker

    def boom(*a, **k):
        raise AssertionError("YOLO training must not be triggered in Block A1")

    monkeypatch.setattr(training_tasks.train_model, "delay", boom)
    monkeypatch.setattr(training_worker, "run_ultralytics_training", boom)
    monkeypatch.setattr(training_tasks, "run_ultralytics_training", boom)
    monkeypatch.setattr(tps, "_send_to_queue", lambda job_id: f"stub-{job_id}")
    monkeypatch.setattr(settings, "TRAINING_DATASETS_DIR", str(tmp_path / "snapshot_datasets"))
    monkeypatch.setattr(settings, "CANDIDATE_MODELS_DIR", str(tmp_path / "candidates"))


def _annotate(client, headers, image_id, category_id, rect):
    return client.post("/api/annotations/", json={
        "image_id": image_id,
        "annotation_type": "rectangle",
        "label_data": rect,
        "category_id": category_id,
        "image_width": 800,
        "image_height": 600,
    }, headers=headers)


def _finalize(client, headers, image_id):
    return client.post(f"/api/annotations/image/{image_id}/finalize", headers=headers)


def _readiness(client, admin_headers):
    r = client.get("/api/dataset/readiness", headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _snapshots(client, admin_headers):
    r = client.get("/api/dataset/snapshots", headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()["snapshots"]


def _snapshot_image_ids(client, admin_headers, snapshot_id):
    r = client.get(f"/api/dataset/snapshots/{snapshot_id}/images", headers=admin_headers)
    assert r.status_code == 200, r.text
    return r.json()["image_ids"]


def _image(db, image_id):
    db.expire_all()
    return db.query(Image).filter(Image.image_id == image_id).one()


def _label_class_ids(db, image_id):
    with open(_image(db, image_id).yolo_txt_path) as fh:
        return [int(line.split()[0]) for line in fh if line.strip()]


def _points(db, user_id):
    db.expire_all()
    return db.query(User).filter(User.user_id == user_id).one().reward_points


def test_full_workflow_through_api(client, user_auth, admin_auth, db):
    uh, ah = user_auth["headers"], admin_auth["headers"]
    jobs_before = db.query(TrainingJob).count()

    cat_a = _create_category(client, ah)
    cat_b = _create_category(client, ah)
    assert client.put("/api/admin/settings", json={"auto_retrain_count": 2}, headers=ah).status_code == 200

    base = _readiness(client, ah)
    assert base["threshold"] == 2
    if base["total_training_eligible_images"] != base["last_milestone"]:
        pytest.skip("database has un-snapshotted eligible images; needs a fresh isolated DB")
    base_last = base["last_milestone"]
    snaps_before = len(_snapshots(client, ah))

    # --- multi-object image: nothing eligible until finalize -----------------
    img1 = _upload_image(client, uh, seed=9101)
    for cat, rect in ((cat_a, _RECTS[0]), (cat_b, _RECTS[1]), (cat_a, _RECTS[2])):
        assert _annotate(client, uh, img1, cat, rect).status_code == 201
        assert _readiness(client, ah)["total_training_eligible_images"] == base_last
        assert _image(db, img1).training_sequence is None
    assert _image(db, img1).status == "permanent"

    points_before = _points(db, user_auth["user_id"])
    r = _finalize(client, uh, img1)
    assert r.status_code == 200, r.text
    assert r.json()["already_finalized"] is False
    seq = r.json()["training_sequence"]
    again = _finalize(client, uh, img1).json()
    assert again["already_finalized"] is True and again["training_sequence"] == seq
    assert _points(db, user_auth["user_id"]) == points_before          # no reward on finalize/retry
    assert _readiness(client, ah)["total_training_eligible_images"] == base_last + 1  # counted once

    # Complete YOLO TXT: 3 objects, contiguous indices (never business class_code)
    cats = {c["category_id"]: c for c in client.get("/api/admin/categories", headers=ah).json()["categories"]}
    ids = _label_class_ids(db, img1)
    assert len(ids) == 3
    assert all(0 <= i < len(cats) for i in ids)
    assert ids.count(ids[0]) == 2 and ids[0] != ids[1]

    # Finalized annotation set is frozen
    anns = client.get(f"/api/annotations/image/{img1}", headers=uh).json()["annotations"]
    ann_id = anns[0]["annotation_id"]
    assert client.put(f"/api/annotations/{ann_id}", json={"label_data": _RECTS[1]}, headers=uh).status_code == 409
    assert client.delete(f"/api/annotations/{ann_id}", headers=uh).status_code == 409
    assert _annotate(client, uh, img1, cat_b, _RECTS[1]).status_code == 409
    assert len(_label_class_ids(db, img1)) == 3

    # --- second image crosses the milestone (total across categories) -------
    img2 = _upload_image(client, uh, seed=9102)
    assert _annotate(client, uh, img2, cat_b, _RECTS[0]).status_code == 201
    assert len(_snapshots(client, ah)) == snaps_before                # not before finalize
    assert _finalize(client, uh, img2).status_code == 200
    snaps = _snapshots(client, ah)
    assert len(snaps) == snaps_before + 1
    v1 = snaps[-1]
    assert v1["milestone_count"] == base_last + 2 and v1["dataset_size"] == base_last + 2
    v1_ids = _snapshot_image_ids(client, ah, v1["snapshot_id"])
    assert v1_ids[-2:] == [img1, img2]
    ready = _readiness(client, ah)
    assert ready["last_milestone"] == base_last + 2 and ready["next_milestone"] == base_last + 4
    assert ready["ready"] is False

    # --- archive category A: history preserved, cumulative V2 ----------------
    r = client.delete(f"/api/admin/categories/{cat_a}", headers=ah)
    assert r.status_code == 200 and r.json()["archived"] is True
    assert _readiness(client, ah)["total_training_eligible_images"] == base_last + 2

    for seed in (9103, 9104):
        img = _upload_image(client, uh, seed=seed)
        assert _annotate(client, uh, img, cat_b, _RECTS[0]).status_code == 201
        assert _finalize(client, uh, img).status_code == 200
    v2 = _snapshots(client, ah)[-1]
    assert v2["dataset_size"] == base_last + 4
    v2_ids = _snapshot_image_ids(client, ah, v2["snapshot_id"])
    assert v2_ids[: len(v1_ids)] == v1_ids                             # V1 subset of V2, same order
    assert img1 in v2_ids                                               # archived-category history kept
    assert _snapshot_image_ids(client, ah, v1["snapshot_id"]) == v1_ids  # V1 unchanged

    # A2: exactly one durable job per newly locked snapshot; nothing trained/activated.
    db.expire_all()
    new_jobs = db.query(TrainingJob).filter(
        TrainingJob.snapshot_id.in_([v1["snapshot_id"], v2["snapshot_id"]])
    ).all()
    assert len(new_jobs) == db.query(TrainingJob).count() - jobs_before == 2
    assert {j.snapshot_id for j in new_jobs} == {v1["snapshot_id"], v2["snapshot_id"]}
    assert all(j.status in ("queued", "failed") and j.best_model_path is None for j in new_jobs)
    from app.models.training import ModelVersion
    assert db.query(ModelVersion).filter(ModelVersion.job_id.in_([j.job_id for j in new_jobs])).count() == 0


def test_unauthorized_finalize_rejected(client, user_auth, admin_auth, db):
    from conftest import _create_user

    cat = _create_category(client, admin_auth["headers"])
    img = _upload_image(client, user_auth["headers"], seed=9201)
    assert _annotate(client, user_auth["headers"], img, cat, _RECTS[0]).status_code == 201

    other = _create_user(client)
    assert _finalize(client, other["headers"], img).status_code == 403
    assert client.post(f"/api/annotations/image/{img}/finalize").status_code in (401, 403)
    assert _image(db, img).training_sequence is None


def test_concurrent_finalize_through_api(client, user_auth, admin_auth, db):
    from fastapi.testclient import TestClient
    from app.main import app

    uh, ah = user_auth["headers"], admin_auth["headers"]
    cat = _create_category(client, ah)
    img = _upload_image(client, uh, seed=9301)
    for rect in _RECTS[:2]:
        assert _annotate(client, uh, img, cat, rect).status_code == 201
    total_before = _readiness(client, ah)["total_training_eligible_images"]

    barrier = threading.Barrier(4)
    responses, errors = [], []

    def worker():
        c = TestClient(app)
        try:
            barrier.wait()
            responses.append(_finalize(c, uh, img))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert [r.status_code for r in responses] == [200] * 4
    bodies = [r.json() for r in responses]
    assert sum(1 for b in bodies if not b["already_finalized"]) == 1
    assert len({b["training_sequence"] for b in bodies}) == 1
    assert _readiness(client, ah)["total_training_eligible_images"] == total_before + 1
    assert len(_label_class_ids(db, img)) == 2
