import uuid
import jwt
from datetime import datetime, timedelta, timezone
from typing import Set
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ---------------------------------------------------------------------------
# In-memory token blacklist.
# Stores jti (JWT ID) strings of revoked tokens.
# Note: This is cleared on server restart. For production, use Redis or a DB
# table. For the current single-process development setup this is sufficient.
# ---------------------------------------------------------------------------
_revoked_jtis: Set[str] = set()


def revoke_token(jti: str) -> None:
    """Add a token's JTI to the revocation list."""
    _revoked_jtis.add(jti)


def is_token_revoked(jti: str) -> bool:
    """Return True if this token has been revoked."""
    return jti in _revoked_jtis


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(identity: str, role: str = "user") -> str:
    expires_delta = timedelta(hours=settings.JWT_ACCESS_TOKEN_EXPIRES_HOURS)
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": identity,
        "role": role,
        "type": "access",
        "exp": expire,
        "jti": str(uuid.uuid4()),   # unique token ID for revocation
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256")


def create_refresh_token(identity: str) -> str:
    expires_delta = timedelta(days=30)
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {
        "sub": identity,
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid.uuid4()),   # unique token ID for revocation
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256")


# ---------------------------------------------------------------------------
# Token decoding
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises 401 HTTPException on any failure."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    # Check revocation blacklist
    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate an ACCESS token and return the authenticated user."""
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: access token required",
        )

    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


def get_current_user_from_refresh_token(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> tuple:
    """
    Validate a REFRESH token and return (user, jti).
    Refuses access tokens — refresh tokens must be distinct.
    """
    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: refresh token required",
        )

    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    jti = payload.get("jti", "")
    return user, jti


def get_token_jti(token: str = Depends(oauth2_scheme)) -> str:
    """Extract and return the jti from any valid token (used for logout)."""
    payload = decode_token(token)
    return payload.get("jti", "")


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
