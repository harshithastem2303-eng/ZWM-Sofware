"""
Application configuration.

All sensitive values MUST come from environment variables (via .env file).
Hardcoded defaults here are ONLY for non-sensitive settings.
"""
import os
import secrets
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # Bootstrap administrator (Block A5.1: no built-in defaults). Both empty = the
    # environment-admin login and startup seeding are disabled; administrators then
    # sign in only through accounts stored in the admins table.
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # Optional demo contributor account for local development only (never production).
    DEMO_USER_EMAIL: str = ""
    DEMO_USER_PASSWORD: str = ""

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    DATABASE_URL: str = ""          # required; set in the environment / .env (no credential fallback)

    # -----------------------------------------------------------------------
    # Redis
    # -----------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

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
    YOLO_CONFIDENCE_THRESHOLD: float = 0.25
    YOLO_INFERENCE_BACKEND: str = "onnx"

    # Automatic (snapshot) training pipeline — v1.1.0 Block A2
    # Immutable, job-specific prepared datasets (one directory per snapshot job).
    TRAINING_DATASETS_DIR: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "worker",
        "snapshot_datasets",
    )
    # Weights produced by snapshot jobs are stored as candidates; never auto-activated.
    CANDIDATE_MODELS_DIR: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "models",
        "candidates",
    )
    # Outbox sweep: how often undispatched jobs are retried, and when a dispatched
    # but still-queued job is considered lost and re-sent (execution stays single
    # because train_model claims queued jobs atomically).
    TRAINING_DISPATCH_INTERVAL_MINUTES: int = 1
    TRAINING_DISPATCH_STALE_MINUTES: int = 30
    # Worker leases (Block A2.1): a running snapshot job is owned by one worker
    # attempt; the owner renews its lease by heartbeat. A job is only considered
    # abandoned when the lease expired more than LEASE_GRACE ago, and is retried
    # at most TRAINING_MAX_ATTEMPTS times in total.
    TRAINING_LEASE_SECONDS: int = 900
    TRAINING_HEARTBEAT_SECONDS: int = 60
    TRAINING_LEASE_GRACE_SECONDS: int = 300
    TRAINING_MAX_ATTEMPTS: int = 3

    # Candidate evaluation (Block A3): isolated, read-only evaluation datasets and
    # the fixed evaluation configuration (part of each evaluation's config hash).
    EVALUATION_DIR: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "worker",
        "evaluations",
    )
    EVAL_IMGSZ: int = 640
    EVAL_CONF: float = 0.001
    EVAL_IOU: float = 0.6

    # Controlled deployment (Block A4): immutable, content-addressed copies of every
    # artifact that was ever served (activation targets and backups of the file
    # being replaced). YOLO_MODEL_PATH stays the single serving path.
    DEPLOYED_MODELS_DIR: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "models",
        "deployed",
    )
    # An activation/rollback that has not finished within this window is
    # considered interrupted and is reconciled by recover_interrupted_deployments().
    DEPLOYMENT_LEASE_SECONDS: int = 900
    # Legacy (non-snapshot) models keep the v1.0 manual activation endpoint; it now
    # runs through the deployment engine (lock, staging, backup, audit). Set False
    # to make approved snapshot candidates the only activatable models.
    ALLOW_LEGACY_MODEL_ACTIVATION: bool = True
    # Block A4.1: legacy (non-snapshot) training jobs register their model and then
    # request activation through the deployment engine (same lock, staging, audit).
    # False = trained legacy models stay inactive until an admin activates them.
    LEGACY_AUTO_ACTIVATE_TRAINED_MODELS: bool = True
    # A running deployment renews its lease at this interval, so recovery never
    # takes over a live activation/rollback (must be well below the lease).
    DEPLOYMENT_HEARTBEAT_SECONDS: int = 60
    # Scheduler sweep: recover expired deployments and reconcile the serving file.
    DEPLOYMENT_RECOVERY_INTERVAL_SECONDS: int = 60
    # os.replace retries on Windows sharing violations (readers holding the file).
    FILE_REPLACE_ATTEMPTS: int = 20
    # Single-flight ONNX export: how long another process waits for a running
    # export, and when an export lock is considered abandoned.
    ONNX_EXPORT_WAIT_SECONDS: int = 120
    ONNX_EXPORT_LOCK_STALE_SECONDS: int = 1800

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



WEAK_PASSWORDS = frozenset({"user123", "password", "password123", "admin", "admin123", "123456", "12345678",
                            "changeme", "qwerty", "letmein"})
MIN_ADMIN_PASSWORD_LENGTH = 12


def env_admin_configured(s: "Settings") -> bool:
    return bool(s.ADMIN_EMAIL.strip()) and bool(s.ADMIN_PASSWORD.strip())


def env_admin_matches(email: str, password: str, s: "Settings" = None) -> bool:
    """Constant-time check against the bootstrap administrator; False when it is not configured."""
    import hmac
    s = s or settings
    if not env_admin_configured(s):
        return False
    email_ok = hmac.compare_digest(email.strip().lower().encode(), s.ADMIN_EMAIL.strip().lower().encode())
    pw_ok = hmac.compare_digest(password.strip().encode(), s.ADMIN_PASSWORD.strip().encode())
    return email_ok and pw_ok


def security_problems(s: "Settings") -> list:
    """Configuration errors that must stop the application (Block A5.1)."""
    problems = []
    if not s.DATABASE_URL.strip():
        problems.append("DATABASE_URL must be set in the environment (.env); there is no built-in default")
    if bool(s.ADMIN_EMAIL.strip()) != bool(s.ADMIN_PASSWORD.strip()):
        problems.append("ADMIN_EMAIL and ADMIN_PASSWORD must be set together (or both left empty)")
    if s.is_production:
        pw = s.ADMIN_PASSWORD.strip()
        if pw and (len(pw) < MIN_ADMIN_PASSWORD_LENGTH or pw.lower() in WEAK_PASSWORDS):
            problems.append(f"ADMIN_PASSWORD must be at least {MIN_ADMIN_PASSWORD_LENGTH} characters "
                            "and not a common password in production")
        if s.DEMO_USER_PASSWORD.strip():
            problems.append("DEMO_USER_PASSWORD must not be set in production")
    return problems


def security_warnings(s: "Settings") -> list:
    pw = s.ADMIN_PASSWORD.strip()
    if pw and (len(pw) < MIN_ADMIN_PASSWORD_LENGTH or pw.lower() in WEAK_PASSWORDS):
        return ["ADMIN_PASSWORD is weak; production startup would refuse it"]
    return []


settings = Settings()

_problems = security_problems(settings)
if _problems:
    raise RuntimeError("Insecure or incomplete configuration: " + "; ".join(_problems))
for _w in security_warnings(settings):
    import logging as _logging
    _logging.getLogger("config").warning(_w)

# Resolve secrets once at startup — ensures consistent keys for the process lifetime.
# In development, if not set, random keys are generated (and stay stable for the session).
_resolved_jwt_secret = settings.get_jwt_secret_key()
_resolved_secret = settings.get_secret_key()

# Monkey-patch the resolved values back so the rest of the app can use settings.JWT_SECRET_KEY
if not settings.JWT_SECRET_KEY:
    settings.JWT_SECRET_KEY = _resolved_jwt_secret
if not settings.SECRET_KEY:
    settings.SECRET_KEY = _resolved_secret
