"""
Ollama LLM client for Qwen2.5 7B (GGUF, CPU inference).
"""
import json
import httpx
from typing import List, AsyncIterator, Optional
import structlog
from app.core.config import settings

logger = structlog.get_logger()

SYSTEM_PROMPT = """You are an internal company assistant. Answer ONLY using the context provided below.
If the answer is not found in the context, say: "I couldn't find that in the company documents."
Never fabricate information. Always cite the source document and page number when available.
Be concise, accurate, and professional."""


def build_prompt(query: str, context_chunks: List[dict], history: List[dict]) -> List[dict]:
    context_text = "\n\n---\n\n".join(
        f"[Source: {c['payload'].get('filename','?')} | Page: {c['payload'].get('page','?')} | Section: {c['payload'].get('section','?')}]\n{c['payload'].get('text','')}"
        for c in context_chunks
    )

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history
    for turn in history[-4:]:  # last 2 turns
        messages.append({"role": turn["role"], "content": turn["content"]})

    user_message = f"""CONTEXT:\n{context_text}\n\nQUESTION: {query}"""
    messages.append({"role": "user", "content": user_message})
    return messages


class OllamaLLMService:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    async def generate(
        self,
        query: str,
        context_chunks: List[dict],
        history: Optional[List[dict]] = None,
    ) -> str:
        messages = build_prompt(query, context_chunks, history or [])
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "top_p": 0.9,
                        "num_ctx": 4096,
                    },
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]

    async def stream(
        self,
        query: str,
        context_chunks: List[dict],
        history: Optional[List[dict]] = None,
    ) -> AsyncIterator[str]:
        messages = build_prompt(query, context_chunks, history or [])
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": True,
                    "options": {"temperature": 0.1, "num_ctx": 4096},
                },
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                        except json.JSONDecodeError:
                            continue
