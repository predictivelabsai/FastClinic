from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, DateTime, func
from datetime import datetime

# Create the base class for SQLAlchemy models
Base = declarative_base()

class BaseModel(Base):
    """Base model class that includes common fields and methods"""
    __abstract__ = True

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow) 