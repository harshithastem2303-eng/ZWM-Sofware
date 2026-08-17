import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class Image(Base):
    __tablename__ = "images"

    image_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    original_filename = Column(String(255), nullable=False)
    temp_s3_path = Column(Text, nullable=True)
    permanent_s3_path = Column(Text, nullable=True)
    split_type = Column(String(10), nullable=True)
    status = Column(String(30), default="uploaded")
    is_validated = Column(Boolean, default=False)
    reward_given = Column(Boolean, default=False)
    credits_awarded = Column(Integer, default=0)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    validated_at = Column(DateTime(timezone=True), nullable=True)

    annotations = relationship("Annotation", backref="image", lazy=True, cascade="all, delete-orphan")