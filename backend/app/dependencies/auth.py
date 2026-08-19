"""
Authentication dependencies for FastAPI.

Security scheme: HTTPBearer  (correct for JWT-based APIs)
  — In Swagger UI, click "Authorize", paste your access_token in the
    "Value" field.  Swagger will send it as  Authorization: Bearer <token>.

OAuth2PasswordBearer is NOT used here because our /login endpoint accepts
JSON (not form data), and HTTPBearer is the appropriate scheme for custom
JWT authentication.
"""
import uuid
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Set

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User

# ---------------------------------------------------------------------------
# Swagger / OpenAPI security scheme
#
# HTTPBearer instructs Swagger UI to show a simple "Value" input field
# where the user pastes their JWT access token.  It then sends the header:
#   Authorization: Bearer <token>
#
# auto_error=False lets us return a clean 401 (instead of FastAPI's default
# 403) when the Authorization header is missing.
# ---------------------------------------------------------------------------
_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# In-memory token blacklist.
# Stores jti (JWT ID) strings of revoked tokens.
#
# ⚠  Production note: this set is cleared on every server restart.
#    For a multi-process or multi-instance deployment replace this with
#    a Redis SET or a database table (e.g., revoked_tokens).
# ---------------------------------------------------------------------------
_revoked_jtis: Set[str] = set()


def revoke_token(jti: str) -> None:
    """Add a token's JTI to the revocation blacklist."""
    _revoked_jtis.add(jti)


def is_token_revoked(jti: str) -> bool:
    """Return True if this token has been revoked (logged out)."""
    return jti in _revoked_jtis


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(identity: str, role: str = "user") -> str:
    """Create a signed JWT access token valid for JWT_ACCESS_TOKEN_EXPIRES_HOURS."""
    expires_delta = timedelta(hours=settings.JWT_ACCESS_TOKEN_EXPIRES_HOURS)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": identity,
        "role": role,
        "type": "access",
        "exp": expire,
        "jti": str(uuid.uuid4()),   # unique ID — enables individual revocation
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


def create_refresh_token(identity: str) -> str:
    """Create a signed JWT refresh token valid for 30 days."""
    expires_delta = timedelta(days=30)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": identity,
        "type": "refresh",
        "exp": expire,
        "jti": str(uuid.uuid4()),   # unique ID — enables individual revocation
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


# ---------------------------------------------------------------------------
# Token decoding & validation
# ---------------------------------------------------------------------------

def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str:
    """
    Pull the raw JWT string out of an HTTPAuthorizationCredentials object.
    Raises 401 if no credentials were supplied.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. "
                   "In Swagger: click 'Authorize' and paste your access_token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises 401 HTTPException on:
      - expired token
      - invalid signature / malformed token
      - revoked token (logged out)
    """
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=["HS256"]
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check revocation blacklist (logout)
    jti = payload.get("jti")
    if jti and is_token_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


# ---------------------------------------------------------------------------
# FastAPI dependency functions
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Validate an ACCESS token and return the authenticated User.

    Usage in Swagger:
      1. Call POST /api/auth/login — copy the 'access_token' from the response.
      2. Click 'Authorize' (padlock icon, top-right).
      3. Paste the token value in the 'Value' field → click Authorize.
      4. All locked endpoints now work automatically.
    """
    token = _extract_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: an access token is required here",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_from_refresh_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> tuple:
    """
    Validate a REFRESH token and return (user, jti).

    IMPORTANT: only a refresh token is accepted here.
    Access tokens are rejected with 401.
    """
    token = _extract_token(credentials)
    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: a refresh token is required here. "
                   "Use the refresh_token from your login response.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jti = payload.get("jti", "")
    return user, jti


def get_token_jti(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """Extract and return the jti claim from any valid token (used by logout)."""
    token = _extract_token(credentials)
    payload = decode_token(token)
    return payload.get("jti", "")


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: require the authenticated user to have the 'admin' role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
