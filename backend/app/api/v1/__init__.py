from fastapi import APIRouter
from app.api.v1.endpoints import documents, query, health

router = APIRouter()
router.include_router(documents.router, prefix="/documents", tags=["documents"])
router.include_router(query.router, prefix="/query", tags=["query"])
router.include_router(health.router, prefix="/health", tags=["health"])
