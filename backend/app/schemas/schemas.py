"""
Pydantic schemas for request/response validation.

Uses Pydantic v2 ConfigDict instead of deprecated class-based Config.
"""
from pydantic import BaseModel, EmailStr, ConfigDict
from typing import Optional
from datetime import datetime

# ---------------------------------------------------------------------------
# Auth & User Schemas
# ---------------------------------------------------------------------------

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = ""


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPassword(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    message: str
    access_token: str
    refresh_token: str
    user_id: str
    role: str


class TokenRefreshResponse(BaseModel):
    """Returned by POST /api/auth/refresh."""
    access_token: str
    refresh_token: str   # new refresh token (rotation: old one is revoked)


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    is_email_verified: bool
    reward_points: Optional[int] = 0
    image_count: Optional[int] = 0
    created_at: datetime


# ---------------------------------------------------------------------------
# Category Schemas
# ---------------------------------------------------------------------------

class CategoryCreate(BaseModel):
    class_name: str
    class_code: int


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    class_name: str
    class_code: int
    validated_count: int


# ---------------------------------------------------------------------------
# Generic Response
# ---------------------------------------------------------------------------

class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Email Verification / Password Reset
# ---------------------------------------------------------------------------

class VerifyEmailRequest(BaseModel):
    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ---------------------------------------------------------------------------
# Image Schemas
# ---------------------------------------------------------------------------

class ImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    image_id: str
    user_id: str
    original_filename: str
    status: Optional[str] = None
    is_validated: bool
    reward_given: bool
    credits_awarded: Optional[int] = 0
    uploaded_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None


class ImageUploadResponse(BaseModel):
    image_id: str
    original_filename: str
    status: str
    validation: dict


# ---------------------------------------------------------------------------
# Annotation Schemas
# ---------------------------------------------------------------------------

class AnnotationCreate(BaseModel):
    image_id: str
    category_id: int
    label_data: Optional[dict] = None


class AnnotationUpdate(BaseModel):
    category_id: Optional[int] = None
    label_data: Optional[dict] = None


class AnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str
    image_id: str
    category_id: int
    annotated_by: str
    label_json_path: Optional[str] = None
    yolo_label_path: Optional[str] = None
    annotated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Training / ML Schemas
# ---------------------------------------------------------------------------

class TrainingJobCreate(BaseModel):
    version: Optional[str] = None


class TrainingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    version: str
    class_counts: Optional[dict] = None
    status: Optional[str] = None
    best_model_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_id: str
    job_id: str
    version: str
    is_current: Optional[bool] = None
    map_score: Optional[float] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Dataset Schemas
# ---------------------------------------------------------------------------

class CategoryStatsItem(BaseModel):
    category_id: int
    class_name: str
    class_code: int
    validated_count: int
    threshold: int
    ready: bool


class DatasetReadinessResponse(BaseModel):
    ready: bool
    categories: list
    threshold: int


# ---------------------------------------------------------------------------
# Analytics Schemas
# ---------------------------------------------------------------------------

class AnalyticsOverview(BaseModel):
    total_users: int
    total_images: int
    validated_images: int
    pending_images: int
    rejected_images: int
    total_annotations: int
    total_categories: int
    total_training_jobs: int


class LeaderboardEntry(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str] = None
    reward_points: int
    image_count: int
