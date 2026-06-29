from fastapi import APIRouter, Request
import httpx
from app.core.config import settings
from app.core.cache import get_redis

router = APIRouter()


@router.get("/detailed")
async def detailed_health(request: Request):
    """Check health of all downstream services."""
    checks = {}

    # Ollama
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            checks["ollama"] = "ok" if r.status_code == 200 else "degraded"
    except Exception:
        checks["ollama"] = "down"

    # Qdrant
    try:
        vstore = request.app.state.vector_store
        checks["qdrant"] = "ok" if await vstore.ping() else "degraded"
    except Exception:
        checks["qdrant"] = "down"

    # Elasticsearch
    try:
        kstore = request.app.state.keyword_store
        checks["elasticsearch"] = "ok" if await kstore.ping() else "degraded"
    except Exception:
        checks["elasticsearch"] = "down"

    # Redis
    try:
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "down"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "services": checks}
