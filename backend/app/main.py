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
from app.routes.user import router as user_router
from app.routes.admin import router as admin_router
from app.routes.image import router as image_router
from app.routes.ml import router as ml_router
from app.routes.dataset import router as dataset_router
from app.routes.annotation import router as annotation_router
from app.routes.lifecycle import router as lifecycle_router
from app.services.cleanup_worker import start_scheduler, stop_scheduler

# ---------------------------------------------------------------------------
# Rate limiter (SlowAPI)
# Uses in-memory storage by default.  For production with multiple workers,
# switch to Redis:  Limiter(key_func=..., storage_uri="redis://localhost:6379")
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_DEFAULT])


# ---------------------------------------------------------------------------
# Lifespan — start/stop the background cleanup scheduler
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the APScheduler cleanup worker on startup; stop it on shutdown."""
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
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(image_router, prefix="/api/images", tags=["Image"])
app.include_router(ml_router, prefix="/api/ml", tags=["ML"])
app.include_router(dataset_router, prefix="/api/dataset", tags=["Dataset"])
app.include_router(annotation_router, prefix="/api/annotations", tags=["Annotation"])
app.include_router(lifecycle_router, prefix="/api/lifecycle", tags=["Lifecycle"])


@app.get("/")
def read_root():
    return {"message": "Welcome to the ZWM API"}


from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.sql import text
from app.database import get_db

@app.get("/api/health/db", tags=["Health"])
def health_db(db: Session = Depends(get_db)):
    """Database connectivity healthcheck query."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database health check failed: {str(e)}"
        )
