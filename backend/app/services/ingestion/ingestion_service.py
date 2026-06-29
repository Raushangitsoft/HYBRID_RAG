"""
Ingestion service: saves file → parses → chunks → embeds → indexes in Qdrant + ES + PG.
"""
import uuid
import hashlib
import asyncio
from pathlib import Path
from typing import List, Dict, Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.cache import cache_invalidate_by_prefix
from app.models.document import Document, DocumentStatus
from app.services.retrieval.embedding_service import EmbeddingService
from app.services.retrieval.vector_store import VectorStoreService
from app.services.retrieval.keyword_store import KeywordStoreService

logger = structlog.get_logger()


def compute_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> List[str]:
    """Simple sentence-aware chunker with overlap."""
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk_words = words[i: i + chunk_size]
        chunks.append(" ".join(chunk_words))
        i += chunk_size - overlap
    return [c.strip() for c in chunks if c.strip()]


async def parse_document(content: bytes, content_type: str, filename: str) -> List[Dict[str, Any]]:
    """Parse document into structured chunks using docling."""
    try:
        from docling.document_converter import DocumentConverter
        import tempfile, os

        with tempfile.NamedTemporaryFile(
            suffix=Path(filename).suffix, delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        loop = asyncio.get_event_loop()
        def _convert():
            converter = DocumentConverter()
            result = converter.convert(tmp_path)
            return result.document.export_to_markdown()

        md_text = await loop.run_in_executor(None, _convert)
        os.unlink(tmp_path)

        # Layout-aware chunking: split at markdown headings first
        sections = []
        current_heading = "General"
        current_text = []
        for line in md_text.split("\n"):
            if line.startswith("#"):
                if current_text:
                    sections.append({"heading": current_heading, "text": "\n".join(current_text)})
                    current_text = []
                current_heading = line.lstrip("#").strip()
            else:
                current_text.append(line)
        if current_text:
            sections.append({"heading": current_heading, "text": "\n".join(current_text)})

        # Sub-chunk long sections
        chunks = []
        for page_num, sec in enumerate(sections, start=1):
            for sub in chunk_text(sec["text"], settings.CHUNK_SIZE, settings.CHUNK_OVERLAP):
                if sub.strip():
                    chunks.append({"section": sec["heading"], "text": sub, "page": page_num})
        return chunks

    except Exception as e:
        logger.warning("docling_parse_failed", error=str(e), fallback="plain_text")
        # Fallback: plain text chunking
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        return [
            {"section": "Document", "text": sub, "page": i + 1}
            for i, sub in enumerate(chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP))
        ]


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_document_record(
        self,
        filename: str,
        content: bytes,
        content_type: str,
        department: str,
        tags: List[str],
    ) -> Document:
        doc = Document(
            filename=filename,
            content_type=content_type,
            department=department,
            tags=tags,
            content_hash=compute_hash(content),
            status=DocumentStatus.PENDING,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def ingest_document(self, doc_id: uuid.UUID, content: bytes, content_type: str):
        """Background task: full ingestion pipeline."""
        # Need fresh DB session (background task)
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if not doc:
                return

            try:
                doc.status = DocumentStatus.PROCESSING
                await db.commit()

                # 1. Save to local disk
                doc_dir = Path(settings.DOCUMENTS_PATH)
                doc_dir.mkdir(parents=True, exist_ok=True)
                file_path = doc_dir / f"{doc_id}_{doc.filename}"
                file_path.write_bytes(content)
                doc.file_path = str(file_path)

                # 2. Parse
                raw_chunks = await parse_document(content, content_type, doc.filename)
                logger.info("document_parsed", doc_id=str(doc_id), chunks=len(raw_chunks))

                # 3. Embed all chunks
                embed_svc = EmbeddingService()
                await embed_svc.initialize()
                texts = [c["text"] for c in raw_chunks]
                vectors = await embed_svc.embed(texts)

                # 4. Prepare index points
                qdrant_points = []
                es_docs = []
                for i, (chunk, vector) in enumerate(zip(raw_chunks, vectors)):
                    chunk_id = str(uuid.uuid4())
                    payload = {
                        "chunk_id": chunk_id,
                        "document_id": str(doc_id),
                        "filename": doc.filename,
                        "department": doc.department,
                        "text": chunk["text"],
                        "section": chunk.get("section", ""),
                        "page": chunk.get("page", 1),
                        "tags": doc.tags or [],
                    }
                    qdrant_points.append({"id": chunk_id, "vector": vector, "payload": payload})
                    es_docs.append(payload)

                # 5. Index
                vs = VectorStoreService()
                await vs.initialize()
                await vs.upsert(qdrant_points)

                ks = KeywordStoreService()
                await ks.initialize()
                await ks.index_chunks(es_docs)

                # 6. Update DB
                doc.chunk_count = len(raw_chunks)
                doc.status = DocumentStatus.INDEXED
                await db.commit()
                logger.info("document_indexed", doc_id=str(doc_id), chunks=len(raw_chunks))

            except Exception as e:
                logger.error("ingestion_failed", doc_id=str(doc_id), error=str(e))
                doc.status = DocumentStatus.FAILED
                doc.error_message = str(e)
                await db.commit()

    async def delete_document(self, doc_id: uuid.UUID):
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Document).where(Document.id == doc_id))
            doc = result.scalar_one_or_none()
            if not doc:
                return

            vs = VectorStoreService()
            await vs.initialize()
            await vs.delete_by_document_id(str(doc_id))

            ks = KeywordStoreService()
            await ks.initialize()
            await ks.delete_by_document_id(str(doc_id))

            # Remove file from disk
            if doc.file_path:
                try:
                    Path(doc.file_path).unlink(missing_ok=True)
                except Exception:
                    pass

            await cache_invalidate_by_prefix(f"doc:{doc_id}")

            doc.status = DocumentStatus.DELETED
            await db.commit()
            logger.info("document_deleted", doc_id=str(doc_id))
