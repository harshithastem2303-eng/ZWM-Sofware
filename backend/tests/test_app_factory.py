"""
Test that the FastAPI application starts correctly and basic health endpoints respond.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestAppStartup:
    """Verify the FastAPI app initializes and serves requests."""

    def test_app_instance_exists(self):
        assert app is not None
        assert app.title == "ZWM Backend API"

    def test_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Welcome to the ZWM API"}

    def test_openapi_schema_loads(self):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert len(schema["paths"]) > 0

    def test_image_health(self):
        response = client.get("/api/images/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_ml_health(self):
        response = client.get("/api/ml/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_dataset_health(self):
        response = client.get("/api/dataset/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_annotation_health(self):
        response = client.get("/api/annotations/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_unknown_route_returns_404(self):
        response = client.get("/api/nonexistent")
        assert response.status_code == 404
