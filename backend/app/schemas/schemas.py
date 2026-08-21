"""
Pydantic schemas for request/response validation.

Uses Pydantic v2 ConfigDict instead of deprecated class-based Config.
"""
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from typing import Optional, Any
from datetime import datetime

# Supported annotation shape types
ANNOTATION_TYPES = {"rectangle", "polygon", "circle", "freehand"}

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
    storage_type: Optional[str] = "local"
    status: Optional[str] = None
    is_validated: bool
    reward_given: bool
    credits_awarded: Optional[int] = 0
    uploaded_at: Optional[datetime] = None
    validated_at: Optional[datetime] = None
    temporary_expires_at: Optional[datetime] = None
    annotated_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    permanent_at: Optional[datetime] = None
    yolo_txt_path: Optional[str] = None


class ImageUploadResponse(BaseModel):
    image_id: str
    original_filename: str
    status: str
    validation: dict


# ---------------------------------------------------------------------------
# Annotation Schemas
# ---------------------------------------------------------------------------

class AnnotationCreate(BaseModel):
    """
    Create a new annotation on an uploaded image.

    - annotation_type: rectangle | polygon | circle | freehand
    - label_data:      shape coordinates — see per-type rules below:
        rectangle / polygon / freehand:
            {"points": [{"x": 10, "y": 20}, {"x": 80, "y": 90}, ...]}
        circle:
            {"cx": 100, "cy": 150, "r": 40}
    - category_id:  integer FK to the categories table (from the dropdown);
                    nullable — can be omitted if no category is selected yet.
    - ai_generated: set True when the annotation was produced by the AI model.
    """
    image_id: str
    annotation_type: Optional[str] = None
    label_data: Optional[dict] = None
    category_id: Optional[int] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    ai_generated: bool = False

    @field_validator('annotation_type')
    @classmethod
    def check_annotation_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        normalised = v.strip().lower()
        if normalised not in ANNOTATION_TYPES:
            raise ValueError(
                f"annotation_type must be one of {sorted(ANNOTATION_TYPES)}, got '{v}'"
            )
        return normalised


class AnnotationUpdate(BaseModel):
    """
    Update an existing annotation (partial update — all fields optional).
    """
    annotation_type: Optional[str] = None
    label_data: Optional[dict] = None
    category_id: Optional[int] = None
    image_width: Optional[int] = None
    image_height: Optional[int] = None
    ai_generated: Optional[bool] = None

    @field_validator('annotation_type')
    @classmethod
    def check_annotation_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalised = v.strip().lower()
        if normalised not in ANNOTATION_TYPES:
            raise ValueError(
                f"annotation_type must be one of {sorted(ANNOTATION_TYPES)}, got '{v}'"
            )
        return normalised


class AnnotationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    annotation_id: str
    image_id: str
    category_id: Optional[int] = None
    annotated_by: str
    annotation_type: Optional[str] = None
    label_data_json: Optional[Any] = None
    ai_generated: Optional[bool] = False
    image_width: Optional[int] = None
    image_height: Optional[int] = None
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
