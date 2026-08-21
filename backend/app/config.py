"""
Application configuration.

All sensitive values MUST come from environment variables (via .env file).
Hardcoded defaults here are ONLY for non-sensitive settings.
"""
import os
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # -----------------------------------------------------------------------
    # Environment mode:  development | staging | production
    # Controls debug output, CORS strictness, and security enforcement.
    # -----------------------------------------------------------------------
    APP_ENV: str = "development"

    # -----------------------------------------------------------------------
    # Core secrets — MUST be set in .env for staging/production.
    # In development, random secrets are generated automatically so the app
    # can start without manual configuration.
    # -----------------------------------------------------------------------
    SECRET_KEY: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_ACCESS_TOKEN_EXPIRES_HOURS: int = 24

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/zwm_db"

    # -----------------------------------------------------------------------
    # CORS — comma-separated list of allowed origins.
    # In development, defaults to common local dev origins.
    # In production, set to your actual frontend domain(s).
    # Example: CORS_ORIGINS=https://zwm.example.com,https://admin.zwm.example.com
    # -----------------------------------------------------------------------
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"

    # -----------------------------------------------------------------------
    # Rate limiting (requests per window).
    # Uses SlowAPI with in-memory backend (use Redis in production).
    # -----------------------------------------------------------------------
    RATE_LIMIT_AUTH: str = "10/minute"     # login, register, forgot-password
    RATE_LIMIT_DEFAULT: str = "60/minute"  # general API endpoints

    # -----------------------------------------------------------------------
    # Storage
    # -----------------------------------------------------------------------
    STORAGE_TYPE: str = "local"
    UPLOAD_FOLDER: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "uploads"
    )

    # AWS S3 — required only when STORAGE_TYPE=s3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET_NAME: str = "zwm-bucket"
    AWS_REGION: str = "us-east-1"

    # -----------------------------------------------------------------------
    # Dataset & ML
    # -----------------------------------------------------------------------
    CATEGORY_VALIDATED_THRESHOLD: int = 100

    YOLO_MODEL_PATH: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "models",
        "best.pt",
    )

    # -----------------------------------------------------------------------
    # Image Lifecycle
    # -----------------------------------------------------------------------
    # Number of days before an unprocessed temporary image is auto-deleted.
    TEMP_EXPIRY_DAYS: int = 7
    # How often (in hours) the background cleanup job runs.
    CLEANUP_INTERVAL_HOURS: int = 1

    # -----------------------------------------------------------------------
    # Derived / computed properties
    # -----------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list. In development, also allow '*' via Swagger."""
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        return origins

    def get_secret_key(self) -> str:
        """Return SECRET_KEY, generating one for dev if not set."""
        if self.SECRET_KEY:
            return self.SECRET_KEY
        if self.is_production:
            raise ValueError(
                "SECRET_KEY must be set in .env for production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return secrets.token_urlsafe(32)

    def get_jwt_secret_key(self) -> str:
        """Return JWT_SECRET_KEY, generating one for dev if not set."""
        if self.JWT_SECRET_KEY:
            return self.JWT_SECRET_KEY
        if self.is_production:
            raise ValueError(
                "JWT_SECRET_KEY must be set in .env for production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return secrets.token_urlsafe(32)


settings = Settings()

# Resolve secrets once at startup — ensures consistent keys for the process lifetime.
# In development, if not set, random keys are generated (and stay stable for the session).
_resolved_jwt_secret = settings.get_jwt_secret_key()
_resolved_secret = settings.get_secret_key()

# Monkey-patch the resolved values back so the rest of the app can use settings.JWT_SECRET_KEY
if not settings.JWT_SECRET_KEY:
    settings.JWT_SECRET_KEY = _resolved_jwt_secret
if not settings.SECRET_KEY:
    settings.SECRET_KEY = _resolved_secret
