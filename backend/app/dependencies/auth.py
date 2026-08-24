"""
Authentication dependencies for FastAPI.

Security scheme: OAuth2PasswordBearer
  — Swagger's "Authorize" dialog shows Username + Password fields.
  — When you click Authorize, Swagger auto-calls POST /api/auth/token
    with your credentials, receives the access_token, and stores it.
  — Every subsequent request automatically includes Authorization: Bearer <token>.
  — No manual copy-paste needed.

The /api/auth/token endpoint accepts form data (OAuth2 standard).
The /api/auth/login endpoint accepts JSON (for frontend/mobile apps).
Both return the same JWT tokens.
"""
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

# ---------------------------------------------------------------------------
# Swagger / OpenAPI security scheme
#
# OAuth2PasswordBearer tells Swagger UI to show a Username + Password form
# in the "Authorize" dialog.  When the user clicks Authorize, Swagger sends
# a POST to tokenUrl with form-encoded credentials, receives the token, and
# attaches it automatically to every subsequent request.
#
# tokenUrl points to the form-data endpoint (/api/auth/token).
# The JSON endpoint (/api/auth/login) is for frontend/mobile clients.
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


import logging
import redis

# ---------------------------------------------------------------------------
# Redis Token Blacklist with In-memory Fallback.
# Stores jti (JWT ID) strings of revoked tokens.
# ---------------------------------------------------------------------------
logger = logging.getLogger("auth_redis")

try:
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
except Exception as e:
    logger.warning(f"Failed to initialize Redis client: {e}. Blacklist fallback to memory will be used.")
    redis_client = None

_revoked_jtis_fallback: Set[str] = set()


def revoke_token(jti: str, exp: int = None) -> None:
    """Add a token's JTI to the revocation blacklist (Redis or memory fallback)."""
    if not jti:
        return
        
    ttl = 2592000  # Default 30 days
    if exp:
        now = int(datetime.now(timezone.utc).timestamp())
        ttl = max(1, exp - now)
        
    if redis_client is not None:
        try:
            redis_client.setex(f"blacklist:{jti}", ttl, "true")
            logger.info(f"Revoked JTI {jti} in Redis with TTL={ttl}s")
            return
        except Exception as e:
            logger.warning(f"Redis write error during token revocation of {jti}: {e}")
            
    _revoked_jtis_fallback.add(jti)
    logger.warning(f"Revoked JTI {jti} in memory fallback due to Redis unavailable")


def is_token_revoked(jti: str) -> bool:
    """Return True if this token JTI is blacklisted in Redis or memory fallback."""
    if not jti:
        return False
        
    if redis_client is not None:
        try:
            val = redis_client.get(f"blacklist:{jti}")
            if val is not None:
                return True
        except Exception as e:
            logger.warning(f"Redis read error during validation check of JTI {jti}: {e}")
            
    return jti in _revoked_jtis_fallback


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
        "jti": str(uuid.uuid4()),
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
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")


# ---------------------------------------------------------------------------
# Token decoding & validation
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises 401 on expired, invalid, or revoked tokens.
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

def _require_token(token: str | None) -> str:
    """Raise 401 if no token was supplied."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Validate an ACCESS token and return the authenticated User."""
    token = _require_token(token)
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: access token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.logging_config import user_id_var
    user_id_var.set(user_id)

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_user_from_refresh_token(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> tuple:
    """
    Validate a REFRESH token and return (user, jti).
    Access tokens are rejected with 401.
    """
    token = _require_token(token)
    payload = decode_token(token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from app.logging_config import user_id_var
    user_id_var.set(user_id)

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
    token: str | None = Depends(oauth2_scheme),
) -> str:
    """Extract and return the jti claim from any valid token (used by logout)."""
    token = _require_token(token)
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
