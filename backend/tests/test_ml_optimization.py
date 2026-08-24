import os
import shutil
import tempfile
import pytest
from io import BytesIO
from PIL import Image as PILImage
from unittest.mock import MagicMock, patch, ANY

from app.config import settings
from app.models.training import TrainingJob, ModelVersion
from app.models.user import User
from app.services.model_cache import YOLOModelCache
from app.main import app

@pytest.fixture(autouse=True)
def clean_model_cache():
    YOLOModelCache().reload()
    yield
    YOLOModelCache().reload()

@pytest.fixture
def dummy_weights():
    model_path = settings.YOLO_MODEL_PATH
    model_dir = os.path.dirname(model_path)
    os.makedirs(model_dir, exist_ok=True)
    
    backup_path = None
    if os.path.exists(model_path):
        fd, tmp_backup = tempfile.mkstemp(prefix="best.pt.backup.")
        os.close(fd)
        os.remove(tmp_backup)
        shutil.move(model_path, tmp_backup)
        backup_path = tmp_backup
        
    with open(model_path, "wb") as f:
        f.write(b"fake yolo weights")
        
    yield model_path
    
    if os.path.exists(model_path):
        os.remove(model_path)
    if backup_path and os.path.exists(backup_path):
        shutil.move(backup_path, model_path)


def test_enrich_model_version_api(client, admin_auth, db):
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database connection not available")

    import uuid
    job_id = str(uuid.uuid4())
    model_id = str(uuid.uuid4())
    
    job = TrainingJob(
        job_id=job_id,
        version="v100",
        status="completed",
        best_model_path="/fake/path/v100.pt",
        class_counts={"plastic": 150}
    )
    db.add(job)
    db.commit()
    
    model = ModelVersion(
        model_id=model_id,
        job_id=job_id,
        version="v100",
        is_current=True,
        map_score=0.92
    )
    db.add(model)
    db.commit()
    
    r = client.get("/api/ml/models", headers=admin_auth["headers"])
    assert r.status_code == 200
    data = r.json()
    assert "models" in data
    found = [m for m in data["models"] if m["model_id"] == model_id]
    assert len(found) == 1
    assert found[0]["version"] == "v100"
    assert found[0]["model_path"] == "/fake/path/v100.pt"
    assert found[0]["dataset_info"] == {"plastic": 150}
    assert found[0]["status"] == "active"
    
    db.delete(model)
    db.delete(job)
    db.commit()


def test_activate_model_endpoints(client, admin_auth, db):
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Database connection not available")

    import uuid
    job_id_1 = str(uuid.uuid4())
    model_id_1 = str(uuid.uuid4())
    job_id_2 = str(uuid.uuid4())
    model_id_2 = str(uuid.uuid4())
    
    temp_dir = tempfile.mkdtemp()
    weights_path_1 = os.path.join(temp_dir, "weights1.pt")
    weights_path_2 = os.path.join(temp_dir, "weights2.pt")
    with open(weights_path_1, "wb") as f: f.write(b"weights1")
    with open(weights_path_2, "wb") as f: f.write(b"weights2")
    
    job1 = TrainingJob(job_id=job_id_1, version="v90", status="completed", best_model_path=weights_path_1)
    job2 = TrainingJob(job_id=job_id_2, version="v91", status="completed", best_model_path=weights_path_2)
    db.add_all([job1, job2])
    db.commit()
    
    model1 = ModelVersion(model_id=model_id_1, job_id=job_id_1, version="v90", is_current=True)
    model2 = ModelVersion(model_id=model_id_2, job_id=job_id_2, version="v91", is_current=False)
    db.add_all([model1, model2])
    db.commit()
    
    try:
        original_model_path = settings.YOLO_MODEL_PATH
        backup_path = None
        if os.path.exists(original_model_path):
            backup_path = original_model_path + ".bak"
            shutil.copy2(original_model_path, backup_path)
            
        r = client.post(f"/api/ml/models/{model_id_2}/activate", headers=admin_auth["headers"])
        assert r.status_code == 200
        
        db.refresh(model1)
        db.refresh(model2)
        assert model1.is_current is False
        assert model2.is_current is True
        
        assert os.path.exists(original_model_path)
        with open(original_model_path, "rb") as f:
            assert f.read() == b"weights2"
            
        job_failed_id = str(uuid.uuid4())
        model_failed_id = str(uuid.uuid4())
        job_failed = TrainingJob(job_id=job_failed_id, version="v92", status="failed")
        model_failed = ModelVersion(model_id=model_failed_id, job_id=job_failed_id, version="v92")
        db.add_all([job_failed, model_failed])
        db.commit()
        
        r_fail = client.post(f"/api/ml/models/{model_failed_id}/activate", headers=admin_auth["headers"])
        assert r_fail.status_code == 400
        
        db.delete(model_failed)
        db.delete(job_failed)
        db.commit()
        
    finally:
        db.delete(model1)
        db.delete(model2)
        db.delete(job1)
        db.delete(job2)
        db.commit()
        
        shutil.rmtree(temp_dir, ignore_errors=True)
        if os.path.exists(original_model_path):
            os.remove(original_model_path)
        if backup_path and os.path.exists(backup_path):
            shutil.move(backup_path, original_model_path)


@patch("ultralytics.YOLO")
def test_predict_model_caching(mock_yolo_cls, client, user_auth, dummy_weights):
    mock_model_instance = MagicMock()
    mock_yolo_cls.return_value = mock_model_instance
    
    mock_box = MagicMock()
    mock_box.cls = [0]
    mock_box.conf = [0.85]
    mock_box.xyxy = [[10.0, 20.0, 30.0, 40.0]]
    
    mock_result = MagicMock()
    mock_result.boxes = [mock_box]
    mock_model_instance.return_value = [mock_result]
    
    img = PILImage.new("RGB", (640, 480), color=(0, 255, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    
    r1 = client.post(
        "/api/ml/predict",
        headers=user_auth["headers"],
        files={"file": ("predict1.jpg", buf, "image/jpeg")},
    )
    assert r1.status_code == 200
    
    buf.seek(0)
    r2 = client.post(
        "/api/ml/predict",
        headers=user_auth["headers"],
        files={"file": ("predict2.jpg", buf, "image/jpeg")},
    )
    assert r2.status_code == 200
    
    assert mock_yolo_cls.call_count == 1
    assert mock_model_instance.call_count == 2
    mock_model_instance.assert_any_call(ANY, conf=settings.YOLO_CONFIDENCE_THRESHOLD)


def test_predict_invalid_image_type(client, user_auth):
    buf = BytesIO(b"fake text content")
    r = client.post(
        "/api/ml/predict",
        headers=user_auth["headers"],
        files={"file": ("predict.txt", buf, "text/plain")},
    )
    assert r.status_code == 400
    assert "Invalid file type" in r.json()["detail"]


@patch("ultralytics.YOLO")
def test_yolo_model_cache_unit(mock_yolo_cls, dummy_weights):
    mock_model_instance = MagicMock()
    mock_yolo_cls.return_value = mock_model_instance
    
    original_backend = settings.YOLO_INFERENCE_BACKEND
    settings.YOLO_INFERENCE_BACKEND = "pytorch"
    
    try:
        cache = YOLOModelCache()
        cache.reload()
        
        # First call: should call constructor
        m1 = cache.get_model()
        assert m1 is mock_model_instance
        assert mock_yolo_cls.call_count == 1
        
        # Second call: should use cache
        m2 = cache.get_model()
        assert m2 is mock_model_instance
        assert mock_yolo_cls.call_count == 1
        
        # Reload: should clear cache
        cache.reload()
        m3 = cache.get_model()
        assert m3 is mock_model_instance
        assert mock_yolo_cls.call_count == 2
    finally:
        settings.YOLO_INFERENCE_BACKEND = original_backend
