import os
import shutil
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import text
from app.config import settings
from app.database import engine
from app.dependencies.auth import is_token_revoked, revoke_token
from app.services.model_cache import YOLOModelCache
from app.main import app

def test_db_healthcheck_endpoint(client, db):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database connection not available")

    r = client.get("/api/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "database": "connected"}


def test_database_connection_pool_settings():
    assert engine.pool.size() == 10
    pool = engine.pool
    assert hasattr(pool, "_recycle") and pool._recycle == 1800
    assert pool._pre_ping is True


@patch("app.dependencies.auth.redis_client")
def test_redis_token_revocation_and_memory_fallback(mock_redis):
    mock_redis.setex.side_effect = Exception("Redis connection refused")
    mock_redis.get.side_effect = Exception("Redis connection refused")
    
    revoke_token("test-jti-123", exp=9999999999)
    assert is_token_revoked("test-jti-123") is True
    
    from app.dependencies.auth import _revoked_jtis_fallback
    _revoked_jtis_fallback.discard("test-jti-123")


@patch("ultralytics.YOLO")
def test_onnx_export_and_fallback_cache(mock_yolo_cls):
    mock_pt_model = MagicMock()
    mock_onnx_model = MagicMock()
    
    def mock_yolo_init(path, *args, **kwargs):
        if path.endswith(".onnx"):
            return mock_onnx_model
        return mock_pt_model
        
    mock_yolo_cls.side_effect = mock_yolo_init
    
    temp_dir = tempfile.mkdtemp()
    pt_path = os.path.join(temp_dir, "best.pt")
    onnx_path = os.path.join(temp_dir, "best.onnx")
    with open(pt_path, "wb") as f:
        f.write(b"pytorch-weights")
        
    original_pt_path = settings.YOLO_MODEL_PATH
    original_backend = settings.YOLO_INFERENCE_BACKEND
    
    settings.YOLO_MODEL_PATH = pt_path
    settings.YOLO_INFERENCE_BACKEND = "onnx"
    
    cache = YOLOModelCache()
    cache.reload()
    
    try:
        m = cache.get_model()
        mock_pt_model.export.assert_called_once_with(format="onnx", imgsz=640, dynamic=True)
        
    finally:
        settings.YOLO_MODEL_PATH = original_pt_path
        settings.YOLO_INFERENCE_BACKEND = original_backend
        shutil.rmtree(temp_dir, ignore_errors=True)
        cache.reload()
