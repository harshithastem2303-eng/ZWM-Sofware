import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship


class Image(Base):
    __tablename__ = "images"

    # -- Core identity -------------------------------------------------------
    image_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    original_filename = Column(String(255), nullable=False)

    # -- Storage paths -------------------------------------------------------
    # temp_s3_path  : path while in temporary storage (uploads/temporary/{user_id}/{uuid}.ext)
    # permanent_s3_path : path after promoted to permanent  (uploads/permanent/{user_id}/{uuid}.ext)
    storage_type = Column(String(20), default="local", nullable=True)
    temp_s3_path = Column(Text, nullable=True)
    permanent_s3_path = Column(Text, nullable=True)
    yolo_txt_path = Column(Text, nullable=True)  # path to YOLO .txt in permanent storage

    # -- Dataset split -------------------------------------------------------
    split_type = Column(String(10), nullable=True)

    # -- Status / validation -------------------------------------------------
    # Lifecycle statuses:
    #   uploaded          - initial state after validation passes
    #   rejected          - image failed validation at upload
    #   annotated         - annotation has been completed
    #   yolo_ready        - YOLO TXT generated and validated
    #   approved          - admin approved (legacy; also triggers promote)
    #   permanent         - successfully moved to permanent storage
    #   conversion_failed - YOLO conversion failed; stays in temp
    #   expired_cleaned   - temp image expired and was cleaned up
    status = Column(String(30), default="uploaded")
    is_validated = Column(Boolean, default=False)

    # -- Rewards -------------------------------------------------------------
    reward_given = Column(Boolean, default=False)
    credits_awarded = Column(Integer, default=0)

    # -- Timestamps (all timezone-aware) -------------------------------------
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Temporary image will be auto-deleted after this time if not promoted
    temporary_expires_at = Column(DateTime(timezone=True), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    annotated_at = Column(DateTime(timezone=True), nullable=True)
    converted_at = Column(DateTime(timezone=True), nullable=True)
    permanent_at = Column(DateTime(timezone=True), nullable=True)

    # -- Relationships -------------------------------------------------------
    annotations = relationship("Annotation", backref="image", lazy=True, cascade="all, delete-orphan")

    # -- Indexes (defined at table level for query performance) ---------------
    __table_args__ = (
        Index("ix_images_status", "status"),
        Index("ix_images_temporary_expires_at", "temporary_expires_at"),
        Index("ix_images_user_id_uploaded_at", "user_id", "uploaded_at"),
    )