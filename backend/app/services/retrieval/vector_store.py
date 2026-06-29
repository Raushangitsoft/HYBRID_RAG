"""
Qdrant vector store — handles collection creation, upsert, and similarity search.
"""
from typing import List, Optional, Dict, Any
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter, FieldCondition,
    MatchValue, SearchRequest, ScoredPoint,
)
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class VectorStoreService:
    def __init__(self):
        self._client: AsyncQdrantClient | None = None

    async def initialize(self):
        self._client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
        exists = await self._client.collection_exists(settings.QDRANT_COLLECTION_NAME)
        if not exists:
            await self._client.create_collection(
                collection_name=settings.QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=settings.EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", name=settings.QDRANT_COLLECTION_NAME)

    async def ping(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception:
            return False

    async def upsert(self, points: List[Dict[str, Any]]):
        """Upsert points. Each dict: {id, vector, payload}."""
        qdrant_points = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
            for p in points
        ]
        await self._client.upsert(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points=qdrant_points,
            wait=True,
        )

    async def search(
        self,
        vector: List[float],
        top_k: int = 50,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filter_ = None
        if department:
            filter_ = Filter(
                must=[FieldCondition(key="department", match=MatchValue(value=department))]
            )

        results: List[ScoredPoint] = await self._client.search(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            query_vector=vector,
            limit=top_k,
            query_filter=filter_,
            with_payload=True,
        )
        return [
            {"id": str(r.id), "score": r.score, "payload": r.payload}
            for r in results
        ]

    async def delete_by_document_id(self, document_id: str):
        from qdrant_client.models import FilterSelector
        await self._client.delete(
            collection_name=settings.QDRANT_COLLECTION_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                )
            ),
        )

    async def close(self):
        if self._client:
            await self._client.close()
