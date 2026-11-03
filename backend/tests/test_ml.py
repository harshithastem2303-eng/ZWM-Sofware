"""Tests for ML endpoints: jobs, models, predict."""
from io import BytesIO


def _discard_stub_queued_jobs(job_ids):
    """Jobs 'queued' to a stubbed Celery would linger as queued; close them for later tests."""
    from app.database import SessionLocal
    from app.models.training import TrainingJob
    if not job_ids:
        return
    s = SessionLocal()
    try:
        s.query(TrainingJob).filter(TrainingJob.job_id.in_(job_ids), TrainingJob.status == "queued")             .update({"status": "failed"}, synchronize_session=False)
        s.commit()
    finally:
        s.close()


class TestTrainingJobs:
    def test_list_jobs(self, client, admin_auth):
        r = client.get("/api/ml/jobs", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "jobs" in r.json()

    def test_list_jobs_non_admin(self, client, user_auth):
        r = client.get("/api/ml/jobs", headers=user_auth["headers"])
        assert r.status_code == 403

    def test_get_job_not_found(self, client, admin_auth):
        r = client.get("/api/ml/jobs/nonexistent-id", headers=admin_auth["headers"])
        assert r.status_code == 404

    def test_trigger_training_not_ready(self, client, admin_auth, monkeypatch):
        """Training should fail if dataset is not ready."""
        # Never reach a real queue or the background-thread training fallback.
        from app.tasks.training_tasks import train_model
        queued = []
        monkeypatch.setattr(train_model, "delay", lambda job_id: queued.append(job_id))
        try:
            r = client.post("/api/ml/train", headers=admin_auth["headers"])
        finally:
            _discard_stub_queued_jobs(queued)
        assert r.status_code == 400


class TestModels:
    def test_list_models(self, client, admin_auth):
        r = client.get("/api/ml/models", headers=admin_auth["headers"])
        assert r.status_code == 200
        assert "models" in r.json()

    def test_get_current_model_none(self, client, user_auth):
        r = client.get("/api/ml/models/current", headers=user_auth["headers"])
        # 404 if no current model exists
        assert r.status_code == 404

    def test_get_model_not_found(self, client, admin_auth):
        r = client.get("/api/ml/models/nonexistent", headers=admin_auth["headers"])
        assert r.status_code == 404


class TestPredict:
    def test_predict_no_model(self, client, user_auth):
        """Should return 503 BLOCKED when no .pt model file exists."""
        from PIL import Image as PILImage
        img = PILImage.new("RGB", (640, 480), color=(0, 255, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        r = client.post(
            "/api/ml/predict",
            headers=user_auth["headers"],
            files={"file": ("predict.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 503
        assert "BLOCKED" in r.json()["detail"]

    def test_predict_no_auth(self, client):
        buf = BytesIO(b"fake image data")
        r = client.post(
            "/api/ml/predict",
            files={"file": ("test.jpg", buf, "image/jpeg")},
        )
        assert r.status_code == 401
