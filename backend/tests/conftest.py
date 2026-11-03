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

# ---------------------------------------------------------------------------
# Block A5.1 — fail-closed test isolation, established BEFORE the app is imported.
# Every data path points into a fresh disposable directory under the system temp
# dir; an audit hook blocks any write/delete/rename on the repository's uploads/,
# models/, worker/ and bundled weights; and only a database whose name contains
# "test" may be used (the session reset below TRUNCATEs tables).
# ---------------------------------------------------------------------------
import tempfile as _tempfile
from app.services import fs_safety as _fs_safety

_TEST_FS_ROOT = _tempfile.mkdtemp(prefix="zwm_test_fs_")
os.environ[_fs_safety.TEST_ROOT_ENV] = _TEST_FS_ROOT
for _name, _rel in (("UPLOAD_FOLDER", "uploads"), ("YOLO_MODEL_PATH", os.path.join("models", "best.pt")),
                    ("TRAINING_DATASETS_DIR", os.path.join("worker", "snapshot_datasets")),
                    ("CANDIDATE_MODELS_DIR", os.path.join("models", "candidates")),
                    ("EVALUATION_DIR", os.path.join("worker", "evaluations")),
                    ("DEPLOYED_MODELS_DIR", os.path.join("models", "deployed"))):
    os.environ[_name] = os.path.join(_TEST_FS_ROOT, _rel)
os.makedirs(os.path.join(_TEST_FS_ROOT, "models"), exist_ok=True)
# A5.1: a per-session bootstrap administrator (no built-in default credentials exist)
import secrets as _secrets
os.environ["ADMIN_EMAIL"] = "test-bootstrap-admin@example.com"
os.environ["ADMIN_PASSWORD"] = _secrets.token_urlsafe(24)
os.environ.pop("DEMO_USER_PASSWORD", None)
_fs_safety.install_test_audit_hook()

from app.config import settings as _settings  # noqa: E402

try:
    _fs_safety.validate_settings_paths(_settings, _TEST_FS_ROOT)
except _fs_safety.UnsafeFilesystemOperation as _exc:
    pytest.exit(f"UNSAFE TEST FILESYSTEM CONFIGURATION: {_exc}", returncode=3)

_db_name = _settings.DATABASE_URL.rsplit("/", 1)[-1].split("?", 1)[0].lower()
if "test" not in _db_name:
    pytest.exit(f"UNSAFE TEST DATABASE: DATABASE_URL must name a disposable *test* database (got '{_db_name}')",
                returncode=3)

from sqlalchemy import text
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models.user import User


class RealTrainingBlocked(RuntimeError):
    """Raised when a test reaches real YOLO training or a weight download."""


@pytest.fixture(autouse=True)
def _block_real_yolo_training(monkeypatch):
    """
    Fail-closed guard for every test: real YOLO training and model-weight
    downloads are impossible, even through directly imported training functions
    (the block sits on ultralytics itself, below every project wrapper).
    Tests that need a training result must monkeypatch the project wrapper
    with a fake; anything that slips through raises RealTrainingBlocked.
    """
    from pathlib import Path
    import ultralytics.engine.model as yolo_model
    import ultralytics.engine.trainer as yolo_trainer
    import ultralytics.utils.downloads as yolo_downloads

    def blocked(*args, **kwargs):
        raise RealTrainingBlocked("real YOLO training/evaluation is blocked in tests")

    def blocked_download(*args, **kwargs):
        raise RealTrainingBlocked("model/weight downloads are blocked in tests")

    original_attempt = yolo_downloads.attempt_download_asset

    def local_only(file, *args, **kwargs):
        if Path(str(file)).exists():
            return original_attempt(file, *args, **kwargs)
        raise RealTrainingBlocked(f"weight download blocked in tests: {file}")

    monkeypatch.setattr(yolo_model.Model, "train", blocked)
    monkeypatch.setattr(yolo_model.Model, "val", blocked)          # no real evaluation either (A3)
    # A5.1: no real inference or export either (tests mock the project wrappers instead)
    for _method in ("predict", "__call__", "track", "export", "benchmark", "tune"):
        if hasattr(yolo_model.Model, _method):
            monkeypatch.setattr(yolo_model.Model, _method, blocked)
    monkeypatch.setattr(yolo_trainer.BaseTrainer, "train", blocked)
    monkeypatch.setattr(yolo_downloads, "safe_download", blocked_download)
    monkeypatch.setattr(yolo_downloads, "attempt_download_asset", local_only)


@pytest.fixture(scope="session", autouse=True)
def _disposable_fs_root():
    """The per-session disposable data root; removed at the end only after re-validation."""
    yield _TEST_FS_ROOT
    import shutil
    shutil.rmtree(_fs_safety.validate_test_root(_TEST_FS_ROOT), ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def reset_test_data():
    """Clear persisted table state before the test suite to keep the DB isolated."""
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except Exception:
        session.close()
        return

    try:
        session.execute(text("TRUNCATE TABLE model_versions, training_jobs, annotations, images, users, categories RESTART IDENTITY CASCADE"))
        session.commit()
    except Exception:
        try:
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
        except Exception:
            pass

    # Training/deployment history and admin settings survive the core truncate above,
    # so earlier sessions' snapshots, thresholds and deployments leaked into later runs.
    # Reset them too, but ONLY on a dedicated *test* database: TRUNCATE bypasses the
    # snapshot immutability guards and must never reach a real database.
    db_name = (session.get_bind().url.database or "").lower()
    if "test" in db_name.rsplit("/", 1)[-1]:
        try:
            session.execute(text(
                "TRUNCATE TABLE deployment_events, model_deployments, model_approvals, model_evaluations, "
                "evaluation_policies, training_snapshot_images, training_snapshots, training_job_events, "
                "scheduler_heartbeats, admins, label_reviews, prediction_records, prediction_feedback_decisions, prediction_feedback, "
                "label_revision_heads, label_revision_events, label_revisions "
                "RESTART IDENTITY CASCADE"))  # A5.1 admins; A6.0 reviews; A6.2 feedback; A6.3 revisions
            session.execute(text("DELETE FROM system_settings"))   # admin routes recreate defaults (id=1)
            session.commit()
        except Exception:
            session.rollback()
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
    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
    except Exception:
        import pytest
        pytest.skip("Database not available for auth fixture setup")

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
def auth_headers(user_auth):
    """Headers dictionary for regular user authentication."""
    return user_auth["headers"]


@pytest.fixture()
def admin_headers(admin_auth):
    """Headers dictionary for admin user authentication."""
    return admin_auth["headers"]


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
