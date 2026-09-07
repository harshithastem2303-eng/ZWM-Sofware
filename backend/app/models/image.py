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

    # -- Category selection & AI validation ----------------------------------
    selected_category_id = Column(Integer, ForeignKey("categories.category_id"), nullable=True)
    ai_predicted_category = Column(String(50), nullable=True)
    ai_confidence_score = Column(Float, nullable=True)
    validation_result = Column(String(50), nullable=True)  # AUTO_ACCEPTED, NEEDS_HUMAN_REVIEW, LOW_CONFIDENCE, CLASS_MISMATCH, MODEL_CLASS_NOT_SUPPORTED
    validation_reason = Column(Text, nullable=True)

    # -- Admin Review audit fields -------------------------------------------
    reviewed_by = Column(String(36), ForeignKey("users.user_id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # -- Status / validation -------------------------------------------------
    # Lifecycle statuses:
    #   uploaded             - initial state after upload
    #   pending_admin_review - needs admin review (mismatch / low confidence / unsupported class)
    #   approved             - auto-accepted or admin approved
    #   rejected             - image failed validation / admin rejected
    #   annotated            - annotation has been completed
    #   yolo_ready           - YOLO TXT generated and validated
    #   permanent            - successfully moved to permanent storage
    #   conversion_failed    - YOLO conversion failed; stays in temp
    #   expired_cleaned      - temp image expired and was cleaned up
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
    selected_category = relationship("Category", foreign_keys=[selected_category_id], lazy="joined")
    reviewer = relationship("User", foreign_keys=[reviewed_by], lazy="select")



    # -- Indexes (defined at table level for query performance) ---------------
    __table_args__ = (
        Index("ix_images_status", "status"),
        Index("ix_images_temporary_expires_at", "temporary_expires_at"),
        Index("ix_images_user_id_uploaded_at", "user_id", "uploaded_at"),
    )