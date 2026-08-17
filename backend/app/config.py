import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str = "super-secret-key-change-in-production"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/zwm_db"
    
    JWT_SECRET_KEY: str = "jwt-secret-key-change-in-production"
    JWT_ACCESS_TOKEN_EXPIRES_HOURS: int = 24
    
    STORAGE_TYPE: str = "local"
    UPLOAD_FOLDER: str = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "uploads")
    
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET_NAME: str = "zwm-bucket"
    AWS_REGION: str = "us-east-1"
    
    CATEGORY_VALIDATED_THRESHOLD: int = 100
    YOLO_MODEL_PATH: str = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "models", "best.pt")

    class Config:
        env_file = ".env"

settings = Settings()
