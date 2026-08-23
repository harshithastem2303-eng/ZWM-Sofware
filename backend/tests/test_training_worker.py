import os
import shutil
import uuid
from pathlib import Path
from datetime import datetime, timezone

import pytest

from sqlalchemy.exc import OperationalError
from sqlalchemy import text
from app.database import SessionLocal
from app.models.training import TrainingJob, ModelVersion
from app.models.category import Category
from app.models.image import Image
from app.models.user import User
from worker import training_worker

ROOT = Path(training_worker.WORKER_ROOT.parent)
UPLOADS = Path(training_worker.DATASETS_ROOT.parent.parent) / 'uploads'


def ensure_db_available():
    """Skip tests if the database is not reachable."""
    try:
        db = SessionLocal()
        # quick probe
        db.execute(text('SELECT 1'))
        db.close()
    except OperationalError:
        pytest.skip('Database not available for integration tests')



def setup_permanent_image(db, user_id='testuser'):
    unique_suffix = uuid.uuid4().hex[:8]
    actual_user_id = f'{user_id}_{unique_suffix}'

    user = db.query(User).filter(User.user_id == actual_user_id).first()
    if not user:
        user = User(
            user_id=actual_user_id,
            email=f'{actual_user_id}@example.com',
            password_hash='hashed-password',
            full_name=actual_user_id,
            role='user',
            is_email_verified=True,
        )
        db.add(user)
        db.commit()

    # create directories
    perm_dir = UPLOADS / 'permanent' / actual_user_id
    perm_dir.mkdir(parents=True, exist_ok=True)
    img_path = perm_dir / 'testimg.jpg'
    txt_path = perm_dir / 'testimg.txt'
    img_path.write_bytes(b'JPEGDATA')
    txt_path.write_text('0 0.5 0.5 0.2 0.2')

    img = Image(
        image_id=f'test-image-{unique_suffix}',
        user_id=actual_user_id,
        original_filename='testimg.jpg',
        storage_type='local',
        temp_s3_path=str(img_path),
        permanent_s3_path=str(img_path),
        yolo_txt_path=str(txt_path),
        status='permanent',
        uploaded_at=datetime.now(timezone.utc)
    )
    db.add(img)
    db.commit()
    return img


@pytest.fixture(autouse=True)
def cleanup_dirs():
    # ensure runs and datasets are clean before/after tests
    try:
        if training_worker.RUNS_ROOT.exists():
            shutil.rmtree(training_worker.RUNS_ROOT)
    except Exception:
        pass
    try:
        if training_worker.DATASETS_ROOT.exists():
            shutil.rmtree(training_worker.DATASETS_ROOT)
    except Exception:
        pass
    yield
    try:
        if training_worker.RUNS_ROOT.exists():
            shutil.rmtree(training_worker.RUNS_ROOT)
    except Exception:
        pass
    try:
        if training_worker.DATASETS_ROOT.exists():
            shutil.rmtree(training_worker.DATASETS_ROOT)
    except Exception:
        pass


def test_process_job_success(monkeypatch):
    ensure_db_available()
    db = SessionLocal()
    # Create category
    cat = Category(
        class_name=f'plastic_{uuid.uuid4().hex[:8]}',
        class_code=(uuid.uuid4().int % 1_000_000_000) + 1_000_000_000,
        validated_count=1,
    )
    db.add(cat)
    db.commit()

    # Create a permanent image and record
    setup_permanent_image(db)

    # Create queued job
    job = TrainingJob(version='v1', status='queued')
    db.add(job)
    db.commit()

    # Monkeypatch training to create a fake best.pt
    def fake_train(data_yaml, run_name, epochs=50, imgsz=640):
        run_dir = training_worker.RUNS_ROOT / 'detect' / run_name / 'weights'
        run_dir.mkdir(parents=True, exist_ok=True)
        best = run_dir / 'best.pt'
        best.write_bytes(b'BESTMODEL')
        return best, {'map50': 0.5}

    monkeypatch.setattr(training_worker, 'run_ultralytics_training', fake_train)

    # Process
    processed = training_worker.process_job_once()
    assert processed is True

    # Refresh job from DB
    j = db.query(TrainingJob).filter(TrainingJob.job_id == job.job_id).first()
    assert j.status == 'completed'
    assert j.best_model_path is not None

    # Check ModelVersion
    mv = db.query(ModelVersion).filter(ModelVersion.job_id == job.job_id).first()
    assert mv is not None
    assert mv.is_current is True

    db.close()


def test_process_job_training_failure(monkeypatch):
    ensure_db_available()
    db = SessionLocal()
    # Create category
    cat = Category(
        class_name=f'metal_{uuid.uuid4().hex[:8]}',
        class_code=(uuid.uuid4().int % 1_000_000_000) + 1_000_000_000,
        validated_count=1,
    )
    db.add(cat)
    db.commit()

    setup_permanent_image(db, user_id='user2')

    # Create queued job
    job = TrainingJob(version='v2', status='queued')
    db.add(job)
    db.commit()

    def fake_train_raise(data_yaml, run_name, epochs=50, imgsz=640):
        raise RuntimeError('training failed')

    monkeypatch.setattr(training_worker, 'run_ultralytics_training', fake_train_raise)

    processed = training_worker.process_job_once()
    assert processed is True

    j = db.query(TrainingJob).filter(TrainingJob.job_id == job.job_id).first()
    assert j.status == 'failed'
    db.close()
