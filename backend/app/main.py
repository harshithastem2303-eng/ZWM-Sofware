"""
ZWM Backend API — FastAPI application factory.

Includes:
  - CORS middleware (origins from config, not hardcoded '*')
  - Rate limiting via SlowAPI
  - All route registrations
  - Background cleanup scheduler (APScheduler) for expired temporary images
"""
from app.logging_config import setup_logging
setup_logging()

import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    def before_send(event, hint):
        req = event.get("request", {})
        if req:
            headers = req.get("headers", {})
            for key in list(headers.keys()):
                if any(k in key.lower() for k in ["authorization", "cookie", "token", "jwt", "x-api-key"]):
                    headers[key] = "[REDACTED]"
            data = req.get("data")
            if isinstance(data, dict):
                for key in list(data.keys()):
                    if any(k in key.lower() for k in ["password", "token", "jwt", "secret", "credentials"]):
                        data[key] = "[REDACTED]"
        extra = event.get("extra", {})
        for key in list(extra.keys()):
            if any(k in key.lower() for k in ["password", "token", "jwt", "secret", "credentials"]):
                extra[key] = "[REDACTED]"
        return event

    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[FastApiIntegration()],
        traces_sample_rate=1.0,
        environment=os.getenv("APP_ENV", "development"),
        before_send=before_send,
    )

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.routes.auth import router as auth_router
from app.routes.user import router as user_router, users_router
from app.routes.admin import router as admin_router
from app.routes.image import router as image_router
from app.routes.ml import router as ml_router
from app.routes.dataset import router as dataset_router
from app.routes.annotation import router as annotation_router
from app.routes.lifecycle import router as lifecycle_router
from app.routes.category import router as category_router
from app.routes.ai_segmentation import router as ai_segmentation_router
from app.services.cleanup_worker import start_scheduler, stop_scheduler

# ---------------------------------------------------------------------------
# Rate limiter (SlowAPI)
# Uses in-memory storage by default.  For production with multiple workers,
# switch to Redis:  Limiter(key_func=..., storage_uri="redis://localhost:6379")
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


def init_db_and_seed():
    """Ensure database schema exists and seed default admin, user, and categories."""
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING"):
        return

    try:
        from app.database import engine, SessionLocal, Base
        from app.models.user import User
        from app.models.category import Category
        from app.routes.auth import get_password_hash

        Base.metadata.create_all(bind=engine)

        db = SessionLocal()
        try:
            # Seed Admin User in User & Admin tables
            from app.models.user import Admin
            admin_email = settings.ADMIN_EMAIL.strip().lower()
            admin_password = settings.ADMIN_PASSWORD.strip()
            admin_user = db.query(User).filter(User.email == admin_email).first()
            if not admin_user:
                admin_user = User(
                    email=admin_email,
                    password_hash=get_password_hash(admin_password),
                    full_name="System Admin",
                    role="admin",
                    is_email_verified=True,
                )
                db.add(admin_user)
            else:
                admin_user.password_hash = get_password_hash(admin_password)
                admin_user.role = "admin"

            admin_rec = db.query(Admin).filter(Admin.admin_email == admin_email).first()
            if not admin_rec:
                admin_rec = Admin(
                    admin_email=admin_email,
                    admin_name="System Admin",
                    hash_password=get_password_hash(admin_password),
                    is_email_verified=True,
                )
                db.add(admin_rec)
            else:
                admin_rec.hash_password = get_password_hash(admin_password)

            # Seed Demo User
            demo_email = "keerthana@zwm.eco"
            demo_user = db.query(User).filter(User.email == demo_email).first()
            if not demo_user:
                demo_user = User(
                    email=demo_email,
                    password_hash=get_password_hash("password123"),
                    full_name="Keerthana H M",
                    role="user",
                    is_email_verified=True,
                    reward_points=320,
                    image_count=128
                )
                db.add(demo_user)
            else:
                demo_user.password_hash = get_password_hash("password123")
                demo_user.role = "user"
                demo_user.is_email_verified = True

            db.commit()

            # Seed Default Categories if table is empty
            if db.query(Category).count() == 0:
                default_categories = [
                    {"name": "Plastic", "code": 101, "desc": "Plastic bottles, containers, and packaging"},
                    {"name": "Paper & Cardboard", "code": 102, "desc": "Paper sheets, magazines, boxes, and cardboard"},
                    {"name": "Metal", "code": 103, "desc": "Aluminum cans, tin foil, and metal objects"},
                    {"name": "Glass", "code": 104, "desc": "Glass bottles, jars, and glass products"},
                    {"name": "Organic Waste", "code": 105, "desc": "Food waste, compostable organic materials"},
                    {"name": "E-Waste", "code": 106, "desc": "Electronic components and small appliances"},
                ]
                for cat_data in default_categories:
                    db.add(Category(
                        class_name=cat_data["name"],
                        class_code=cat_data["code"],
                        description=cat_data["desc"],
                        is_active=True
                    ))

            # Seed Default SystemSetting if table is empty
            from app.models.setting import SystemSetting
            if db.query(SystemSetting).count() == 0:
                db.add(SystemSetting(id=1))

            db.commit()

            # Ensure dataset folder structure exists for all active categories under uploads/dataset/{category_slug}/
            from app.services.lifecycle_service import slugify_category_name
            all_cats = db.query(Category).all()
            for cat in all_cats:
                slug = slugify_category_name(cat.class_name)
                cat_dir = os.path.join(settings.UPLOAD_FOLDER, "dataset", slug)
                os.makedirs(os.path.join(cat_dir, "images"), exist_ok=True)
                os.makedirs(os.path.join(cat_dir, "labels"), exist_ok=True)

        except Exception as e:
            db.rollback()
            print(f"[INIT_DB] Warning: DB seeding skipped: {e}")
        finally:
            db.close()
    except Exception as e:
        print(f"[INIT_DB] Warning: DB init skipped: {e}")


# ---------------------------------------------------------------------------
# Lifespan — start/stop the background cleanup scheduler & init database
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start DB seed and APScheduler cleanup worker on startup; stop it on shutdown."""
    init_db_and_seed()
    start_scheduler()
    yield
    stop_scheduler()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ZWM Backend API",
    version="1.0.0",
    description="Zero Waste Management — image collection, annotation, and ML training platform.",
    lifespan=lifespan,
)

# Attach limiter to app state (required by SlowAPI)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

from app.exceptions import (
    ZWMException,
    zwm_exception_handler,
    http_exception_handler,
    validation_exception_handler,
    unhandled_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

app.add_exception_handler(ZWMException, zwm_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ---------------------------------------------------------------------------
# CORS — origins come from settings, NOT hardcoded '*'
# In development:  http://localhost:3000, http://localhost:5173, etc.
# In production:   set CORS_ORIGINS env var to your real frontend domain(s).
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.middleware.logging_middleware import StructuredLoggingMiddleware
app.add_middleware(StructuredLoggingMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(user_router, prefix="/api/user", tags=["User"])
app.include_router(users_router, prefix="/api/users", tags=["Users"])
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(category_router, prefix="/api/categories", tags=["Category"])
app.include_router(image_router, prefix="/api/images", tags=["Image"])
app.include_router(ml_router, prefix="/api/ml", tags=["ML"])
app.include_router(dataset_router, prefix="/api/dataset", tags=["Dataset"])
app.include_router(annotation_router, prefix="/api/annotations", tags=["Annotation"])
app.include_router(lifecycle_router, prefix="/api/lifecycle", tags=["Lifecycle"])
app.include_router(ai_segmentation_router, prefix="/api/ai", tags=["AI Segmentation"])



@app.get("/")
def read_root():
    return {"message": "Welcome to the ZWM API"}


from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from app.database import get_db

@app.get("/api/health/db", tags=["Health"])
def health_db(db: Session = Depends(get_db)):
    """Database connectivity healthcheck query — verified."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database health check failed: {str(e)}"
        )
