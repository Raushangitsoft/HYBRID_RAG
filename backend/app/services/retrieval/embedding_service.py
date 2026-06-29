"""
Embedding service using sentence-transformers (BAAI/bge-m3).
Runs entirely on CPU inside the backend container.
"""
from typing import List
import asyncio
import structlog
from sentence_transformers import SentenceTransformer
from app.core.config import settings

logger = structlog.get_logger()


class EmbeddingService:
    def __init__(self):
        self._model: SentenceTransformer | None = None

    async def initialize(self):
        """Load model in executor to avoid blocking event loop."""
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            None, lambda: SentenceTransformer(settings.EMBEDDING_MODEL)
        )
        logger.info("embedding_model_loaded", model=settings.EMBEDDING_MODEL)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, returns list of float vectors."""
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(
            None, lambda: self._model.encode(texts, normalize_embeddings=True).tolist()
        )
        return vectors

    async def embed_query(self, query: str) -> List[float]:
        vecs = await self.embed([query])
        return vecs[0]

    async def close(self):
        self._model = None
