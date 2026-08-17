from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# --- Auth & User Schemas ---
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
    access_token: str

class UserProfile(BaseModel):
    user_id: str
    email: EmailStr
    full_name: Optional[str]
    role: str
    is_email_verified: bool
    reward_points: int
    image_count: int
    created_at: datetime

    class Config:
        from_attributes = True

# --- Category Schemas ---
class CategoryCreate(BaseModel):
    class_name: str
    class_code: int

class CategoryResponse(BaseModel):
    category_id: int
    class_name: str
    class_code: int
    validated_count: int

    class Config:
        from_attributes = True

# --- Generic Response ---
class MessageResponse(BaseModel):
    message: str

# --- Email Verification / Password Reset ---
class VerifyEmailRequest(BaseModel):
    token: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# --- Image Schemas ---
class ImageResponse(BaseModel):
    image_id: str
    user_id: str
    original_filename: str
    status: Optional[str]
    is_validated: bool
    reward_given: bool
    credits_awarded: int
    uploaded_at: Optional[datetime]
    validated_at: Optional[datetime]

    class Config:
        from_attributes = True

class ImageUploadResponse(BaseModel):
    image_id: str
    original_filename: str
    status: str
    validation: dict

# --- Annotation Schemas ---
class AnnotationCreate(BaseModel):
    image_id: str
    category_id: int
    label_data: Optional[dict] = None

class AnnotationUpdate(BaseModel):
    category_id: Optional[int] = None
    label_data: Optional[dict] = None

class AnnotationResponse(BaseModel):
    annotation_id: str
    image_id: str
    category_id: int
    annotated_by: str
    label_json_path: Optional[str]
    yolo_label_path: Optional[str]
    annotated_at: Optional[datetime]

    class Config:
        from_attributes = True

# --- Training/ML Schemas ---
class TrainingJobCreate(BaseModel):
    version: Optional[str] = None

class TrainingJobResponse(BaseModel):
    job_id: str
    version: str
    class_counts: Optional[dict]
    status: Optional[str]
    best_model_path: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class ModelVersionResponse(BaseModel):
    model_id: str
    job_id: str
    version: str
    is_current: Optional[bool]
    map_score: Optional[float]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True

# --- Dataset Schemas ---
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

# --- Analytics Schemas ---
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
    full_name: Optional[str]
    reward_points: int
    image_count: int
