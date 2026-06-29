"""
Elasticsearch BM25 keyword search service.
"""
from typing import List, Optional, Dict, Any
from elasticsearch import AsyncElasticsearch
import structlog
from app.core.config import settings

logger = structlog.get_logger()

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "document_id": {"type": "keyword"},
            "text": {"type": "text", "analyzer": "english"},
            "filename": {"type": "keyword"},
            "department": {"type": "keyword"},
            "page": {"type": "integer"},
            "section": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "created_at": {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}


class KeywordStoreService:
    def __init__(self):
        self._client: AsyncElasticsearch | None = None

    async def initialize(self):
        self._client = AsyncElasticsearch([settings.ELASTICSEARCH_URL])
        exists = await self._client.indices.exists(index=settings.ELASTICSEARCH_INDEX)
        if not exists:
            await self._client.indices.create(index=settings.ELASTICSEARCH_INDEX, body=INDEX_MAPPING)
            logger.info("es_index_created", index=settings.ELASTICSEARCH_INDEX)

    async def ping(self) -> bool:
        try:
            return await self._client.ping()
        except Exception:
            return False

    async def index_chunks(self, chunks: List[Dict[str, Any]]):
        """Bulk index chunks."""
        actions = []
        for chunk in chunks:
            actions.append({"index": {"_index": settings.ELASTICSEARCH_INDEX, "_id": chunk["chunk_id"]}})
            actions.append(chunk)
        if actions:
            await self._client.bulk(body=actions, refresh=True)

    async def search(
        self,
        query: str,
        top_k: int = 50,
        department: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        must = [{"match": {"text": {"query": query, "operator": "or", "fuzziness": "AUTO"}}}]
        filter_ = []
        if department:
            filter_.append({"term": {"department": department}})

        body = {
            "query": {"bool": {"must": must, "filter": filter_}},
            "size": top_k,
        }
        resp = await self._client.search(index=settings.ELASTICSEARCH_INDEX, body=body)
        return [
            {
                "id": hit["_id"],
                "score": hit["_score"],
                "payload": hit["_source"],
            }
            for hit in resp["hits"]["hits"]
        ]

    async def delete_by_document_id(self, document_id: str):
        await self._client.delete_by_query(
            index=settings.ELASTICSEARCH_INDEX,
            body={"query": {"term": {"document_id": document_id}}},
            refresh=True,
        )

    async def close(self):
        if self._client:
            await self._client.close()
