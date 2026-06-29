from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    ENVIRONMENT: str = "production"
    SECRET_KEY: str = "changeme"
    LOG_LEVEL: str = "INFO"

    # Ollama
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_TIMEOUT: int = 300

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "documents"

    # Elasticsearch
    ELASTICSEARCH_URL: str = "http://elasticsearch:9200"
    ELASTICSEARCH_INDEX: str = "documents"

    # PostgreSQL
    POSTGRES_URL: str = "postgresql+asyncpg://raguser:ragpassword@postgres:5432/ragdb"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_TTL: int = 3600

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIMENSION: int = 1024

    # Reranker
    RERANKER_MODEL: str = "BAAI/bge-reranker-large"

    # Storage
    DOCUMENTS_PATH: str = "/app/data/documents"

    # Retrieval
    HYBRID_BM25_WEIGHT: float = 0.45
    HYBRID_VECTOR_WEIGHT: float = 0.55
    RETRIEVAL_TOP_K: int = 50
    RERANKER_TOP_K: int = 10

    # Chunking
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
