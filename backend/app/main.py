"""
Hybrid RAG System — FastAPI Application Entry Point
"""
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.database import init_db
from app.services.retrieval.embedding_service import EmbeddingService
from app.services.retrieval.vector_store import VectorStoreService
from app.services.retrieval.keyword_store import KeywordStoreService

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    logger.info("Starting Hybrid RAG backend", env=settings.ENVIRONMENT)

    # Init DB schema
    await init_db()
    logger.info("Database initialized")

    # Warm up embedding model
    embed_svc = EmbeddingService()
    await embed_svc.initialize()
    app.state.embedding_service = embed_svc
    logger.info("Embedding model loaded", model=settings.EMBEDDING_MODEL)

    # Init vector store collection
    vs = VectorStoreService()
    await vs.initialize()
    app.state.vector_store = vs
    logger.info("Qdrant collection ready")

    # Init ES index
    ks = KeywordStoreService()
    await ks.initialize()
    app.state.keyword_store = ks
    logger.info("Elasticsearch index ready")

    logger.info("All services ready — backend online")
    yield

    # Shutdown
    logger.info("Shutting down backend")
    await embed_svc.close()
    await vs.close()
    await ks.close()


app = FastAPI(
    title="Hybrid RAG System",
    description="Production-grade internal document intelligence platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration,
    )
    return response


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "1.0.0", "env": settings.ENVIRONMENT}


app.include_router(api_v1_router, prefix="/api/v1")
