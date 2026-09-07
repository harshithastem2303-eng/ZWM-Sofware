from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime
from datetime import datetime, timezone
from app.database import Base

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, default=1)
    
    # Platform Information
    platform_name = Column(String(255), default="Zero Waste Management System")
    admin_email = Column(String(255), default="admin@zwm-system.com")
    api_base_url = Column(String(255), default="http://localhost:8000/api")
    maintenance_mode = Column(Boolean, default=False)

    # Machine Learning Pipeline
    active_model = Column(String(50), default="YOLO11")
    epochs = Column(Integer, default=50)
    image_size = Column(String(50), default="640 × 640")
    batch_size = Column(Integer, default=16)
    device = Column(String(50), default="GPU (CUDA)")
    optimizer = Column(String(50), default="AdamW")
    learning_rate = Column(Float, default=0.01)
    auto_retrain_count = Column(Integer, default=1000)
    confidence_threshold = Column(Float, default=0.65)
    auto_train_toggle = Column(Boolean, default=True)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
