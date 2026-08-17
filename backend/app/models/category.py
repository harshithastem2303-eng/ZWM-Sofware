from app.database import Base
from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship


class Category(Base):
    __tablename__ = "categories"

    category_id = Column(Integer, primary_key=True, autoincrement=True)
    class_name = Column(String(25), unique=True, nullable=False)
    class_code = Column(Integer, unique=True, nullable=False)
    validated_count = Column(Integer, default=0)

    annotations = relationship("Annotation", backref="category", lazy=True)