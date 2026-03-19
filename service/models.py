import uuid
from sqlalchemy import Column, String, DateTime, Text, Enum
from sqlalchemy.sql import func
from database import Base
import enum

class JobStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    done       = "done"
    failed     = "failed"

class Job(Base):
    __tablename__ = "jobs"

    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status     = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False, index=True)
    payload    = Column(Text, nullable=True)
    result     = Column(Text, nullable=True)
    error      = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())