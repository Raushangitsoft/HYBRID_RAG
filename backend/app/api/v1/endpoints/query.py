"""
Query endpoint — orchestrates the full RAG pipeline via LangGraph.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.database import get_db
from app.core.cache import cache_get, cache_set, make_cache_key
from app.schemas.query import QueryRequest, QueryResponse
from app.services.llm.rag_pipeline import RAGPipeline

logger = structlog.get_logger()
router = APIRouter()


@router.post("/", response_model=QueryResponse)
async def query_documents(
    request: Request,
    payload: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a query and get an answer with citations.
    Full pipeline: rewrite → hybrid search → rerank → compress → LLM → answer.
    """
    if not payload.query.strip():
        raise HTTPException(status_code=422, detail="Query cannot be empty")

    # Cache lookup
    cache_key = make_cache_key("query", payload.query, payload.department or "all")
    if payload.use_cache:
        cached = await cache_get(cache_key)
        if cached:
            logger.info("cache_hit", query=payload.query[:60])
            return QueryResponse(**cached)

    # Build pipeline with shared services from app state
    pipeline = RAGPipeline(
        embedding_service=request.app.state.embedding_service,
        vector_store=request.app.state.vector_store,
        keyword_store=request.app.state.keyword_store,
        db=db,
    )

    result = await pipeline.run(
        query=payload.query,
        department=payload.department,
        top_k=payload.top_k or 10,
        conversation_history=payload.conversation_history or [],
    )

    if payload.use_cache:
        await cache_set(cache_key, result.model_dump())

    return result


@router.post("/stream")
async def query_stream(
    request: Request,
    payload: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Streaming version of the query endpoint (SSE)."""
    pipeline = RAGPipeline(
        embedding_service=request.app.state.embedding_service,
        vector_store=request.app.state.vector_store,
        keyword_store=request.app.state.keyword_store,
        db=db,
    )

    async def event_generator():
        async for token in pipeline.stream(
            query=payload.query,
            department=payload.department,
            top_k=payload.top_k or 10,
            conversation_history=payload.conversation_history or [],
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
