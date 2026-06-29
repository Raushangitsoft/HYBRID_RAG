import uuid
import enum
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, Enum, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class ConfidentialityLevel(str, enum.Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(512), nullable=False)
    content_type = Column(String(128), nullable=False)
    department = Column(String(128), default="general")
    owner = Column(String(256), default="system")
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, index=True)
    confidentiality = Column(Enum(ConfidentialityLevel), default=ConfidentialityLevel.INTERNAL)
    tags = Column(ARRAY(String), default=list)
    file_path = Column(Text)           # local disk path
    content_hash = Column(String(64))  # SHA-256
    chunk_count = Column(Integer, default=0)
    version = Column(Integer, default=1)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
