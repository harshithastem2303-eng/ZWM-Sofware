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
