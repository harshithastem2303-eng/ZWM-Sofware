import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class Annotation(Base):
    __tablename__ = "annotations"

    # -- Core identity --------------------------------------------------------
    annotation_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    image_id = Column(String(36), ForeignKey("images.image_id"), nullable=False, index=True)
    # category_id is nullable: set via predefined dropdown — no hardcoded default
    category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    annotated_by = Column(String(36), ForeignKey("users.user_id"), nullable=False)

    # -- Shape / annotation type ----------------------------------------------
    # Supported values: rectangle | polygon | circle | freehand
    annotation_type = Column(String(20), nullable=True)

    # -- Inline JSON storage (primary storage for shape data) -----------------
    # rectangle / polygon / freehand: {"points": [{"x": 10, "y": 20}, ...]}
    # circle:                         {"cx": 100, "cy": 100, "r": 40}
    label_data_json = Column(JSON, nullable=True)

    # -- AI / metadata --------------------------------------------------------
    ai_generated = Column(Boolean, default=False, nullable=True)

    # -- Image dimensions (used for YOLO coordinate normalization) ------------
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)

    # -- Legacy file-path columns (retained for backward compatibility) --------
    label_json_path = Column(Text, nullable=True)
    yolo_label_path = Column(Text, nullable=True)

    # -- Timestamps -----------------------------------------------------------
    annotated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))