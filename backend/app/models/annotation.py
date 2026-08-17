import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class Annotation(Base):
    __tablename__ = "annotations"

    annotation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    image_id = Column(String(36), ForeignKey("images.image_id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=False)
    annotated_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    label_json_path = Column(Text, nullable=True)
    yolo_label_path = Column(Text, nullable=True)
    annotated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))