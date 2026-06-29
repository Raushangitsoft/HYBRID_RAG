"""
BGE Cross-Encoder Reranker — re-scores top-K candidates.
Loaded lazily on first use to avoid blocking startup.
"""
import asyncio
from typing import List, Dict, Any, Tuple
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class RerankerService:
    _model = None

    @classmethod
    async def _get_model(cls):
        if cls._model is None:
            from FlagEmbedding import FlagReranker
            loop = asyncio.get_event_loop()
            cls._model = await loop.run_in_executor(
                None,
                lambda: FlagReranker(settings.RERANKER_MODEL, use_fp16=False),  # CPU safe
            )
            logger.info("reranker_loaded", model=settings.RERANKER_MODEL)
        return cls._model

    async def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Rerank candidates using cross-encoder.
        candidates: list of dicts with 'payload.text' key.
        Returns top_k sorted by reranker score descending.
        """
        if not candidates:
            return []

        model = await self._get_model()
        pairs = [(query, c["payload"].get("text", "")) for c in candidates]

        loop = asyncio.get_event_loop()
        scores: List[float] = await loop.run_in_executor(
            None, lambda: model.compute_score(pairs, normalize=True)
        )

        for cand, score in zip(candidates, scores):
            cand["reranker_score"] = float(score)

        reranked = sorted(candidates, key=lambda x: x["reranker_score"], reverse=True)
        return reranked[:top_k]
