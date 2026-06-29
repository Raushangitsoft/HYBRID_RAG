from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    department: Optional[str] = None
    top_k: Optional[int] = Field(default=10, ge=1, le=20)
    use_cache: bool = True
    conversation_history: Optional[List[ConversationTurn]] = []


class Citation(BaseModel):
    document_id: str
    filename: str
    page: Optional[int] = None
    section: Optional[str] = None
    chunk_text: str
    score: float


class QueryResponse(BaseModel):
    answer: str
    citations: List[Citation]
    rewritten_query: Optional[str] = None
    retrieval_count: int
    latency_ms: float
    cached: bool = False
