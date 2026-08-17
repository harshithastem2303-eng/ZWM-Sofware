"""Tests for ML endpoints: jobs, models, predict."""
from io import BytesIO


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

    def test_trigger_training_not_ready(self, client, admin_auth):
        """Training should fail if dataset is not ready."""
        r = client.post("/api/ml/train", headers=admin_auth["headers"])
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
