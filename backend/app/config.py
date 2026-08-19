import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    SECRET_KEY: str = "super-secret-key-change-in-production"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/zwm_db"

    JWT_SECRET_KEY: str = "jwt-secret-key-change-in-production"
    JWT_ACCESS_TOKEN_EXPIRES_HOURS: int = 24

    STORAGE_TYPE: str = "local"
    UPLOAD_FOLDER: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "uploads"
    )

    # AWS S3 — only required when STORAGE_TYPE=s3
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET_NAME: str = "zwm-bucket"
    AWS_REGION: str = "us-east-1"

    CATEGORY_VALIDATED_THRESHOLD: int = 100

    # Path to a trained YOLO .pt model file; 503 is returned if not present
    YOLO_MODEL_PATH: str = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "models",
        "best.pt",
    )


settings = Settings()
