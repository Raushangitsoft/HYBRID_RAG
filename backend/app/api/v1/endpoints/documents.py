"""
Document ingestion and management endpoints.
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.document import DocumentResponse, DocumentListResponse
from app.services.ingestion.ingestion_service import IngestionService
from app.models.document import Document, DocumentStatus
import structlog

logger = structlog.get_logger()
router = APIRouter()


@router.post("/upload", response_model=DocumentResponse, status_code=202)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    department: str = Query(default="general"),
    tags: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document for ingestion into the RAG pipeline."""
    allowed_types = {
        "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain", "text/markdown",
    }
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Supported: PDF, DOCX, PPTX, XLSX, TXT",
        )

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    svc = IngestionService(db)
    doc = await svc.create_document_record(
        filename=file.filename,
        content=content,
        content_type=file.content_type,
        department=department,
        tags=tag_list,
    )

    background_tasks.add_task(svc.ingest_document, doc.id, content, file.content_type)
    logger.info("document_upload_queued", doc_id=str(doc.id), filename=file.filename)

    return doc


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    department: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all documents with optional filters."""
    from sqlalchemy import select, func

    query = select(Document)
    if department:
        query = query.where(Document.department == department)
    if status:
        query = query.where(Document.status == status)

    count_q = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_q)
    total = total_result.scalar()

    query = query.offset((page - 1) * page_size).limit(page_size).order_by(Document.created_at.desc())
    result = await db.execute(query)
    docs = result.scalars().all()

    return DocumentListResponse(documents=docs, total=total, page=page, page_size=page_size)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Get a specific document by ID."""
    result = await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Delete a document and remove it from all indexes."""
    from sqlalchemy import select
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    svc = IngestionService(db)
    background_tasks.add_task(svc.delete_document, document_id)
    logger.info("document_delete_queued", doc_id=str(document_id))
