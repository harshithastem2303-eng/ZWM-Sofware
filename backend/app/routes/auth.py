import uuid
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.schemas import UserRegister, UserLogin, ForgotPassword, TokenResponse, TokenRefreshResponse, MessageResponse
from app.dependencies.auth import create_access_token, create_refresh_token, get_current_user

router = APIRouter()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=409, detail="User already exists")

    hashed_password = get_password_hash(user_in.password)
    verification_token = str(uuid.uuid4())

    new_user = User(
        email=user_in.email,
        password_hash=hashed_password,
        full_name=user_in.full_name,
        verification_token=verification_token,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    print(f"Mock sending email to {new_user.email} with token: {verification_token}")

    return {"message": "User registered successfully", "user_id": new_user.user_id}

@router.post("/login", response_model=TokenResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not verify_password(user_in.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(identity=user.user_id, role=user.role)
    refresh_token = create_refresh_token(identity=user.user_id)

    return {
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.user_id,
        "role": user.role
    }

@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(current_user: User = Depends(get_current_user)):
    # Note: normally you'd validate the refresh token explicitly, 
    # but based on the original code logic, we just generate a new access token.
    # To properly implement refresh, you should decode the refresh token specifically.
    new_access_token = create_access_token(identity=current_user.user_id, role=current_user.role)
    return {"access_token": new_access_token}

@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user)):
    return {"message": "Successfully logged out"}

@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(forgot_in: ForgotPassword, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == forgot_in.email).first()
    if user:
        reset_token = str(uuid.uuid4())
        print(f"Mock sending reset email to {user.email} with token: {reset_token}")
        
    return {"message": "If the email is registered, a password reset link has been sent"}
