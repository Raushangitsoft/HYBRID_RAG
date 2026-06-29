"""
Hybrid search: combines BM25 (Elasticsearch) and dense vector (Qdrant)
results using Reciprocal Rank Fusion (RRF).
"""
from typing import List, Dict, Any, Optional
import structlog
from app.services.retrieval.vector_store import VectorStoreService
from app.services.retrieval.keyword_store import KeywordStoreService
from app.services.retrieval.embedding_service import EmbeddingService
from app.core.config import settings

logger = structlog.get_logger()

RRF_K = 60  # RRF constant


def reciprocal_rank_fusion(
    bm25_results: List[Dict],
    vector_results: List[Dict],
) -> List[Dict]:
    """
    Merge two ranked lists using RRF.
    score = sum(1 / (k + rank)) across lists.
    """
    scores: Dict[str, float] = {}
    payloads: Dict[str, Dict] = {}

    for rank, item in enumerate(bm25_results, start=1):
        cid = item["id"]
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank)
        payloads[cid] = item.get("payload", {})

    for rank, item in enumerate(vector_results, start=1):
        cid = item["id"]
        scores[cid] = scores.get(cid, 0) + 1 / (RRF_K + rank)
        if cid not in payloads:
            payloads[cid] = item.get("payload", {})

    merged = [
        {"id": cid, "score": score, "payload": payloads[cid]}
        for cid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ]
    return merged


class HybridSearchService:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
        keyword_store: KeywordStoreService,
    ):
        self.embedding = embedding_service
        self.vector_store = vector_store
        self.keyword_store = keyword_store

    async def search(
        self,
        query: str,
        top_k: int = 50,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Run parallel BM25 + vector search then fuse results."""
        import asyncio

        query_vector = await self.embedding.embed_query(query)

        bm25_task = self.keyword_store.search(query, top_k=top_k, department=department)
        vec_task = self.vector_store.search(query_vector, top_k=top_k, department=department)

        bm25_results, vector_results = await asyncio.gather(bm25_task, vec_task)

        logger.info(
            "hybrid_search_raw",
            bm25_count=len(bm25_results),
            vector_count=len(vector_results),
        )

        fused = reciprocal_rank_fusion(bm25_results, vector_results)
        return fused[:top_k]
