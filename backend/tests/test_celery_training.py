import uuid
import pytest
from unittest.mock import MagicMock
from sqlalchemy.exc import OperationalError
from celery.exceptions import MaxRetriesExceededError, Retry

from app.database import SessionLocal
from app.models.training import TrainingJob, ModelVersion
from app.models.category import Category
from app.tasks.training_tasks import train_model
from worker import training_worker
from test_training_worker import setup_permanent_image, ensure_db_available

def test_celery_task_success(monkeypatch, db):
    ensure_db_available()
    
    # Create category
    cat = Category(
        class_name=f'plastic_{uuid.uuid4().hex[:8]}',
        class_code=(uuid.uuid4().int % 1_000_000_000) + 1_000_000_000,
        validated_count=1,
    )
    db.add(cat)
    db.commit()
    
    # Create permanent image
    setup_permanent_image(db)
    
    # Create queued job
    job = TrainingJob(version='v1', status='queued')
    db.add(job)
    db.commit()
    
    # Mock YOLO training to create fake best.pt
    def fake_train(data_yaml, run_name, epochs=50, imgsz=640):
        run_dir = training_worker.RUNS_ROOT / 'detect' / run_name / 'weights'
        run_dir.mkdir(parents=True, exist_ok=True)
        best = run_dir / 'best.pt'
        best.write_bytes(b'BESTMODEL')
        return best, {'map50': 0.8}
        
    monkeypatch.setattr(training_worker, 'run_ultralytics_training', fake_train)
    
    # Execute the Celery task synchronously
    result = train_model(job.job_id)
    assert "completed successfully" in result
    
    # Assert DB updates
    db.expire_all()
    j = db.query(TrainingJob).filter(TrainingJob.job_id == job.job_id).first()
    assert j.status == 'completed'
    assert j.best_model_path is not None
    assert j.metadata_path is not None
    
    mv = db.query(ModelVersion).filter(ModelVersion.job_id == job.job_id).first()
    assert mv is not None
    assert mv.is_current is True
    assert mv.map_score == 0.8


def test_celery_task_permanent_failure(monkeypatch, db):
    ensure_db_available()
    
    cat = Category(
        class_name=f'metal_{uuid.uuid4().hex[:8]}',
        class_code=(uuid.uuid4().int % 1_000_000_000) + 1_000_000_000,
        validated_count=1,
    )
    db.add(cat)
    db.commit()
    
    setup_permanent_image(db, user_id='user_fail')
    
    job = TrainingJob(version='v2', status='queued')
    db.add(job)
    db.commit()
    
    # Mock YOLO training to raise non-retryable exception
    def fake_train_fail(data_yaml, run_name, epochs=50, imgsz=640):
        raise ValueError("Invalid configuration for YOLO")
        
    monkeypatch.setattr(training_worker, 'run_ultralytics_training', fake_train_fail)
    
    result = train_model(job.job_id)
    assert "failed" in result
    
    db.expire_all()
    j = db.query(TrainingJob).filter(TrainingJob.job_id == job.job_id).first()
    assert j.status == 'failed'
    assert j.metadata_path is not None


def test_celery_task_retry_transient_failure(monkeypatch, db):
    ensure_db_available()
    
    job = TrainingJob(version='v3', status='queued')
    db.add(job)
    db.commit()
    
    # Track calls
    retry_called = []
    
    # Mock task's retry method
    def fake_retry(self_task, exc, **kwargs):
        retry_called.append(exc)
        # Raise Retry exception to simulate Celery flow
        raise Retry("Simulated Celery Retry")
        
    monkeypatch.setattr(train_model, 'retry', fake_retry.__get__(train_model, type(train_model)))
    
    # Mock build_dataset_from_permanent to raise transient database OperationalError
    def fake_build_dataset_fail(dest_dir):
        raise OperationalError("SELECT 1", {}, "Database connection lost")
        
    monkeypatch.setattr('app.tasks.training_tasks.build_dataset_from_permanent', fake_build_dataset_fail)
    
    with pytest.raises(Retry):
        train_model(job.job_id)
        
    assert len(retry_called) == 1
    assert isinstance(retry_called[0], OperationalError)


def test_celery_task_retry_exhausted(monkeypatch, db):
    ensure_db_available()
    
    job = TrainingJob(version='v4', status='queued')
    db.add(job)
    db.commit()
    
    # Mock retry to raise MaxRetriesExceededError
    def fake_retry_exhaust(self_task, exc, **kwargs):
        raise MaxRetriesExceededError("Simulated Max Retries Exceeded")
        
    monkeypatch.setattr(train_model, 'retry', fake_retry_exhaust.__get__(train_model, type(train_model)))
    
    def fake_build_dataset_fail(dest_dir):
        raise OperationalError("SELECT 1", {}, "Database connection lost")
        
    monkeypatch.setattr('app.tasks.training_tasks.build_dataset_from_permanent', fake_build_dataset_fail)
    
    with pytest.raises(MaxRetriesExceededError):
        train_model(job.job_id)
        
    db.expire_all()
    j = db.query(TrainingJob).filter(TrainingJob.job_id == job.job_id).first()
    assert j.status == 'failed'
    assert j.metadata_path is not None


def test_celery_task_duplicate_worker_skips(db):
    ensure_db_available()
    
    job = TrainingJob(version='v5', status='running')
    db.add(job)
    db.commit()
    
    result = train_model(job.job_id)
    assert "skipped" in result
    
    db.expire_all()
    j = db.query(TrainingJob).filter(TrainingJob.job_id == job.job_id).first()
    assert j.status == 'running'  # unchanged


def test_api_trigger_async(client, admin_auth, monkeypatch):
    # Mock check_dataset_readiness to return True
    monkeypatch.setattr('app.routes.ml.check_dataset_readiness', lambda db: (True, [{"class_name": "plastic", "validated_count": 500}]))
    
    # Mock trigger_training_job to return a fake TrainingJob
    fake_job = TrainingJob(job_id='fake-celery-job-id', version='v6', status='queued')
    monkeypatch.setattr('app.routes.ml.trigger_training_job', lambda db, version, class_counts: fake_job)
    
    # Mock Celery delay call
    delay_called_with = []
    monkeypatch.setattr(train_model, 'delay', lambda job_id: delay_called_with.append(job_id))
    
    r = client.post(
        "/api/ml/train",
        headers=admin_auth["headers"]
    )
    
    assert r.status_code == 201
    data = r.json()
    assert data["job_id"] == 'fake-celery-job-id'
    assert data["status"] == 'queued'
    assert len(delay_called_with) == 1
    assert delay_called_with[0] == 'fake-celery-job-id'
