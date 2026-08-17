import uuid
from datetime import datetime, timezone

from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    user_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(30), unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    full_name = Column(String(150), nullable=True)
    role = Column(String(20), default="user")
    is_email_verified = Column(Boolean, default=False)
    verification_token = Column(Text, nullable=True)
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
    admin_email = Column(String(30), unique=True, nullable=False)
    is_email_verified = Column(Boolean, default=False)
    hash_password = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )