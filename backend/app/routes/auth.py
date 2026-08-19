"""
Authentication routes.

POST /register          – create account
POST /verify-email      – confirm email address
POST /login             – issue access + refresh tokens
POST /refresh           – use a refresh token to get a new access token
POST /logout            – revoke the current access token
POST /forgot-password   – generate a password-reset token (console output in dev)
POST /reset-password    – consume reset token and set a new password
"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.schemas import (
    UserRegister, UserLogin, ForgotPassword,
    TokenResponse, TokenRefreshResponse, MessageResponse,
    VerifyEmailRequest, ResetPasswordRequest,
)
from app.dependencies.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_current_user_from_refresh_token,
    get_token_jti,
    revoke_token,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


# ---------------------------------------------------------------------------
# Reset token helpers
# ---------------------------------------------------------------------------

RESET_TOKEN_TTL_MINUTES = 60   # password-reset tokens expire after 60 min


def _generate_reset_token() -> str:
    return f"reset:{uuid.uuid4()}"


def _reset_token_expired(user: User) -> bool:
    """Return True if the stored reset token has expired."""
    if user.reset_token_expiry is None:
        return True
    return datetime.now(timezone.utc) > user.reset_token_expiry


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account."""
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(status_code=409, detail="User already exists")

    hashed_password = get_password_hash(user_in.password)
    verification_token = f"verify:{uuid.uuid4()}"

    new_user = User(
        email=user_in.email,
        password_hash=hashed_password,
        full_name=user_in.full_name,
        verification_token=verification_token,
        reward_points=0,
        image_count=0,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # In production, send a real verification email here.
    # In development, the token is printed to the console.
    print(
        f"[DEV] Email verification for {new_user.email} → token: {verification_token}"
    )

    return {"message": "User registered successfully", "user_id": new_user.user_id}


@router.post("/verify-email", response_model=MessageResponse)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    """Verify an email address using the token sent during registration."""
    token = body.token
    user = db.query(User).filter(
        User.verification_token == token,
        User.is_email_verified == False,  # noqa: E712
    ).first()

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid or already-used verification token",
        )

    user.is_email_verified = True
    user.verification_token = None
    db.commit()

    return {"message": "Email verified successfully"}


@router.post("/login", response_model=TokenResponse)
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and return JWT access + refresh tokens."""
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
        "role": user.role,
    }


@router.post("/refresh", response_model=TokenRefreshResponse)
def refresh(
    user_and_jti: tuple = Depends(get_current_user_from_refresh_token),
):
    """
    Issue a new access token using a valid refresh token.

    IMPORTANT: only a refresh token is accepted here; sending an access token
    will result in a 401 error.
    """
    current_user, old_jti = user_and_jti

    # Revoke the used refresh token (one-time use per token).
    if old_jti:
        revoke_token(old_jti)

    new_access_token = create_access_token(
        identity=current_user.user_id,
        role=current_user.role,
    )
    new_refresh_token = create_refresh_token(identity=current_user.user_id)

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(
    jti: str = Depends(get_token_jti),
    current_user: User = Depends(get_current_user),
):
    """
    Invalidate the current access token.

    After logout, the token is added to the revocation blacklist and will be
    rejected by every protected endpoint.
    """
    if jti:
        revoke_token(jti)
    return {"message": "Successfully logged out"}


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(forgot_in: ForgotPassword, db: Session = Depends(get_db)):
    """
    Generate a password-reset token for the given email address.

    Always returns 200 regardless of whether the email is registered, to
    prevent user-enumeration attacks. In development the token is printed to
    the console; in production, plug in your email provider here.
    """
    user = db.query(User).filter(User.email == forgot_in.email).first()
    if user:
        reset_token = _generate_reset_token()
        expiry = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

        user.password_reset_token = reset_token
        user.reset_token_expiry = expiry
        db.commit()

        # In production, send reset_token via email.
        print(
            f"[DEV] Password reset for {user.email} → token: {reset_token} "
            f"(expires in {RESET_TOKEN_TTL_MINUTES} min)"
        )

    return {
        "message": "If the email is registered, a password reset link has been sent"
    }


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """
    Reset a user's password using a valid reset token.

    The token must:
      * start with the 'reset:' prefix
      * match a user's stored password_reset_token
      * not be expired
    """
    token = body.token
    if not token.startswith("reset:"):
        raise HTTPException(status_code=400, detail="Invalid reset token")

    user = db.query(User).filter(User.password_reset_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if _reset_token_expired(user):
        # Clean up expired token
        user.password_reset_token = None
        user.reset_token_expiry = None
        db.commit()
        raise HTTPException(status_code=400, detail="Reset token has expired")

    user.password_hash = get_password_hash(body.new_password)
    user.password_reset_token = None
    user.reset_token_expiry = None
    db.commit()

    return {"message": "Password reset successfully"}
