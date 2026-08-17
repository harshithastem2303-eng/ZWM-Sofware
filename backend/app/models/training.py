import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class TrainingJob(Base):
    __tablename__ = "training_jobs"

    job_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version = Column(String(20), nullable=False)
    class_counts = Column(JSON, nullable=True)
    status = Column(String(20), default="queued")
    best_model_path = Column(Text, nullable=True)
    metadata_path = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    model_versions = relationship("ModelVersion", backref="training_job", lazy=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    model_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("training_jobs.job_id"), nullable=False)
    version = Column(String(20), nullable=False)
    is_current = Column(Boolean, default=False)
    map_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )