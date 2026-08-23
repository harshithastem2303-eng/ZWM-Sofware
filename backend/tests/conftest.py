"""
Shared pytest fixtures for ZWM backend tests.
Auto-generates test users and JWT tokens — no manual input needed.
"""
import os
import sys
import uuid
import pytest
from io import BytesIO

# Ensure the backend directory is on the path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
os.chdir(backend_dir)

from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, ".env"))

from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.user import User


@pytest.fixture(scope="session", autouse=True)
def reset_test_data():
    """Clear persisted table state before the test suite to keep the DB isolated."""
    session = SessionLocal()
    try:
        session.execute(text("TRUNCATE TABLE model_versions, training_jobs, annotations, images, users, categories RESTART IDENTITY CASCADE"))
        session.commit()
    except Exception:
        for table in [
            "model_versions",
            "training_jobs",
            "annotations",
            "images",
            "users",
            "categories",
        ]:
            session.execute(text(f"DELETE FROM {table}"))
        session.commit()
    finally:
        session.close()


@pytest.fixture(scope="session")
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture(scope="session")
def db():
    """Database session for direct DB operations in tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _create_user(client, role="user"):
    """Register a user, optionally promote to admin, login, return auth dict."""
    email = f"test_{role}_{uuid.uuid4().hex[:8]}@test.com"
    password = "TestPassword123!"
    full_name = f"Test {role.capitalize()}"

    # Register
    client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": full_name,
    })

    # Promote to admin if needed
    if role == "admin":
        session = SessionLocal()
        user = session.query(User).filter(User.email == email).first()
        if user:
            user.role = "admin"
            session.commit()
        session.close()

    # Login
    r = client.post("/api/auth/login", json={
        "email": email,
        "password": password,
    })
    data = r.json()
    return {
        "email": email,
        "password": password,
        "user_id": data.get("user_id"),
        "access_token": data.get("access_token"),
        "refresh_token": data.get("refresh_token"),
        "headers": {"Authorization": f"Bearer {data.get('access_token', '')}"},
    }


@pytest.fixture(scope="session")
def user_auth(client):
    """Registered and logged-in regular user."""
    return _create_user(client, role="user")


@pytest.fixture(scope="session")
def admin_auth(client):
    """Registered and logged-in admin user."""
    return _create_user(client, role="admin")


@pytest.fixture()
def test_image_file():
    """Create a valid 800x600 JPEG image with texture (passes blur check)."""
    from PIL import Image as PILImage, ImageDraw
    import random
    img = PILImage.new("RGB", (800, 600), color=(100, 150, 200))
    draw = ImageDraw.Draw(img)
    # Draw random lines/shapes to create texture that passes Laplacian blur check
    random.seed(42)
    for _ in range(200):
        x1, y1 = random.randint(0, 799), random.randint(0, 599)
        x2, y2 = random.randint(0, 799), random.randint(0, 599)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.line([(x1, y1), (x2, y2)], fill=color, width=2)
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    buf.name = "test_image.jpg"
    return buf


@pytest.fixture()
def small_image_file():
    """Create an image that's too small (below min dimensions) for validation tests."""
    from PIL import Image as PILImage
    img = PILImage.new("RGB", (100, 100), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    buf.name = "small_image.jpg"
    return buf
