import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from uac_parser.database import Base


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey("uac_collections.id"), nullable=True)
    status = Column(String, default="pending")  # pending | running | completed | failed | partial
    upload_path = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)

    artifact_jobs = relationship("ArtifactJob", back_populates="processing_job", cascade="all, delete-orphan")
    logs = relationship("ProcessingLog", back_populates="processing_job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ProcessingJob(id={self.id}, status='{self.status}')>"


class ArtifactJob(Base):
    __tablename__ = "artifact_jobs"

    id = Column(Integer, primary_key=True)
    processing_job_id = Column(Integer, ForeignKey("processing_jobs.id"), nullable=False)
    artifact_type = Column(String)  # processes | netconns | auth | cmdhistory | users
    status = Column(String, default="pending")
    celery_task_id = Column(String)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    record_count = Column(Integer, default=0)
    error_message = Column(String)

    processing_job = relationship("ProcessingJob", back_populates="artifact_jobs")
    logs = relationship("ProcessingLog", back_populates="artifact_job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ArtifactJob(type='{self.artifact_type}', status='{self.status}')>"


class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True)
    processing_job_id = Column(Integer, ForeignKey("processing_jobs.id"), nullable=True)
    artifact_job_id = Column(Integer, ForeignKey("artifact_jobs.id"), nullable=True)
    level = Column(String)  # INFO | WARNING | ERROR | DEBUG
    message = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    processing_job = relationship("ProcessingJob", back_populates="logs")
    artifact_job = relationship("ArtifactJob", back_populates="logs")

    def __repr__(self):
        return f"<ProcessingLog(level='{self.level}', message='{self.message[:40]}')>"


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("artifact_type", "artifact_id", name="uq_note"),
    )

    id            = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey("uac_collections.id"), nullable=False)
    artifact_type = Column(String, nullable=False)
    artifact_id   = Column(Integer, nullable=False)
    content       = Column(String, nullable=False)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<Note({self.artifact_type}#{self.artifact_id})>"


class Tag(Base):
    __tablename__ = "tags"

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False, unique=True)
    color      = Column(String, nullable=False, default="gray")
    is_default = Column(Boolean, default=False)

    taggings = relationship("Tagging", back_populates="tag", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tag(name='{self.name}', color='{self.color}')>"


class Tagging(Base):
    __tablename__ = "taggings"
    __table_args__ = (
        UniqueConstraint("tag_id", "artifact_type", "artifact_id", name="uq_tagging"),
    )

    id            = Column(Integer, primary_key=True)
    tag_id        = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    artifact_type = Column(String, nullable=False)   # processes | auth | cmdhistory | netconns | files
    artifact_id   = Column(Integer, nullable=False)
    collection_id = Column(Integer, ForeignKey("uac_collections.id"), nullable=False)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)

    tag = relationship("Tag", back_populates="taggings")

    def __repr__(self):
        return f"<Tagging(tag_id={self.tag_id}, {self.artifact_type}#{self.artifact_id})>"
