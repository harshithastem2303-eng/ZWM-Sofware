from celery import Celery
from app.config import settings

import os
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=1.0,
        environment=os.getenv("APP_ENV", "development"),
    )

celery_app = Celery(
    "zwm_backend",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.training_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

from celery.signals import setup_logging

@setup_logging.connect
def config_loggers(*args, **kwargs):
    from app.logging_config import setup_logging as app_setup_logging
    app_setup_logging()
