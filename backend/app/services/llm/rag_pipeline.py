"""
RAG Pipeline — orchestrates: query rewrite → hybrid search → rerank → compress → LLM.
"""
import time
from typing import List, Optional, AsyncIterator
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval.embedding_service import EmbeddingService
from app.services.retrieval.vector_store import VectorStoreService
from app.services.retrieval.keyword_store import KeywordStoreService
from app.services.retrieval.hybrid_search import HybridSearchService
from app.services.retrieval.reranker import RerankerService
from app.services.llm.ollama_service import OllamaLLMService
from app.schemas.query import QueryResponse, Citation
from app.core.config import settings

logger = structlog.get_logger()


async def rewrite_query(query: str, llm: OllamaLLMService) -> str:
    """Expand short/ambiguous queries for better retrieval."""
    if len(query.split()) > 8:
        return query  # already specific enough
    prompt_chunks = [{"payload": {"text": "", "filename": "", "page": "", "section": ""}}]
    rewrite_prompt = f'Rewrite this short query into a detailed question for document search. Return ONLY the rewritten query, nothing else.\nQuery: "{query}"\nRewritten:'
    try:
        rewritten = await llm.generate(rewrite_prompt, prompt_chunks, [])
        rewritten = rewritten.strip().strip('"').strip("'")
        logger.info("query_rewritten", original=query, rewritten=rewritten)
        return rewritten if rewritten else query
    except Exception:
        return query


def deduplicate_chunks(chunks: List[dict]) -> List[dict]:
    seen = set()
    result = []
    for c in chunks:
        text = c["payload"].get("text", "")[:100]
        if text not in seen:
            seen.add(text)
            result.append(c)
    return result


class RAGPipeline:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
        keyword_store: KeywordStoreService,
        db: AsyncSession,
    ):
        self.hybrid = HybridSearchService(embedding_service, vector_store, keyword_store)
        self.reranker = RerankerService()
        self.llm = OllamaLLMService()
        self.db = db

    async def run(
        self,
        query: str,
        department: Optional[str] = None,
        top_k: int = 10,
        conversation_history: Optional[List[dict]] = None,
    ) -> QueryResponse:
        t0 = time.time()

        # 1. Query rewriting
        rewritten = await rewrite_query(query, self.llm)

        # 2. Hybrid search
        candidates = await self.hybrid.search(
            rewritten,
            top_k=settings.RETRIEVAL_TOP_K,
            department=department,
        )
        logger.info("hybrid_search_done", candidates=len(candidates))

        # 3. Reranking
        reranked = await self.reranker.rerank(rewritten, candidates, top_k=top_k)
        logger.info("reranking_done", top=len(reranked))

        # 4. Dedup + compress
        final_chunks = deduplicate_chunks(reranked)[:top_k]

        # 5. LLM generation
        answer = await self.llm.generate(query, final_chunks, conversation_history or [])

        latency = round((time.time() - t0) * 1000, 1)
        logger.info("rag_pipeline_done", latency_ms=latency, chunks=len(final_chunks))

        citations = [
            Citation(
                document_id=c["payload"].get("document_id", ""),
                filename=c["payload"].get("filename", ""),
                page=c["payload"].get("page"),
                section=c["payload"].get("section"),
                chunk_text=c["payload"].get("text", "")[:300],
                score=round(c.get("reranker_score", c.get("score", 0.0)), 4),
            )
            for c in final_chunks
        ]

        return QueryResponse(
            answer=answer,
            citations=citations,
            rewritten_query=rewritten if rewritten != query else None,
            retrieval_count=len(candidates),
            latency_ms=latency,
        )

    async def stream(
        self,
        query: str,
        department: Optional[str] = None,
        top_k: int = 10,
        conversation_history: Optional[List[dict]] = None,
    ) -> AsyncIterator[str]:
        rewritten = await rewrite_query(query, self.llm)
        candidates = await self.hybrid.search(rewritten, top_k=settings.RETRIEVAL_TOP_K, department=department)
        reranked = await self.reranker.rerank(rewritten, candidates, top_k=top_k)
        final_chunks = deduplicate_chunks(reranked)[:top_k]

        async for token in self.llm.stream(query, final_chunks, conversation_history or []):
            yield token
