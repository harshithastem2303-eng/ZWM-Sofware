import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Widened from String(30) → String(255) to support all valid email lengths
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    full_name = Column(String(150), nullable=True)
    role = Column(String(20), default="user")
    is_email_verified = Column(Boolean, default=False)

    # Email verification token (set on registration, cleared after use)
    verification_token = Column(Text, nullable=True)

    # Password reset — stored in a dedicated field separate from verification
    password_reset_token = Column(Text, nullable=True)
    reset_token_expiry = Column(DateTime(timezone=True), nullable=True)

    reward_points = Column(Integer, default=0)
    image_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    images = relationship("Image", backref="user", lazy=True, cascade="all, delete-orphan")
    annotations = relationship("Annotation", backref="annotator", lazy=True)


class Admin(Base):
    __tablename__ = "admins"

    admin_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    admin_name = Column(String(150), nullable=False)
    admin_email = Column(String(255), unique=True, nullable=False)
    is_email_verified = Column(Boolean, default=False)
    hash_password = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RewardTransaction(Base):
    __tablename__ = "reward_transactions"
    
    transaction_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.user_id"), nullable=False)
    image_id = Column(String(36), ForeignKey("images.image_id"), nullable=True)
    points = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))