"""
Hybrid RAG System — Main Chat Interface
"""
import streamlit as st
import httpx
import os
import time

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Hybrid RAG — Document Intelligence",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/search--v1.png", width=60)
    st.title("Hybrid RAG")
    st.caption("Internal Document Intelligence Platform")
    st.divider()

    department = st.selectbox(
        "Filter by Department",
        ["All", "HR", "Finance", "Legal", "Engineering", "Operations", "General"],
    )
    dept_filter = None if department == "All" else department.lower()

    top_k = st.slider("Max context chunks", min_value=3, max_value=15, value=8)
    use_cache = st.toggle("Use response cache", value=True)

    st.divider()
    if st.button("🗑️ Clear conversation"):
        st.session_state.messages = []
        st.session_state.citations = {}
        st.rerun()

    st.divider()
    # Health check
    try:
        r = httpx.get(f"{BACKEND_URL}/health", timeout=3)
        if r.status_code == 200:
            st.success("✅ Backend online")
        else:
            st.error("⚠️ Backend degraded")
    except Exception:
        st.error("❌ Backend unreachable")

# ── Main UI ──────────────────────────────────────────────────────────────────
st.title("🔍 Document Intelligence Chat")
st.caption(f"Powered by Qwen2.5 7B · Hybrid Search (BM25 + Vector) · BGE Reranker")

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "citations" not in st.session_state:
    st.session_state.citations = {}

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("meta"):
            meta = msg["meta"]
            cols = st.columns(3)
            cols[0].caption(f"⏱️ {meta.get('latency_ms', 0):.0f} ms")
            cols[1].caption(f"📄 {meta.get('retrieval_count', 0)} chunks retrieved")
            if meta.get("rewritten_query"):
                cols[2].caption(f"✏️ Rewritten: _{meta['rewritten_query']}_")

# ── Chat Input ────────────────────────────────────────────────────────────────
if prompt := st.chat_input("Ask a question about your documents…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Searching and generating answer…"):
            try:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[-6:]
                    if m["role"] in ("user", "assistant")
                ]

                resp = httpx.post(
                    f"{BACKEND_URL}/api/v1/query/",
                    json={
                        "query": prompt,
                        "department": dept_filter,
                        "top_k": top_k,
                        "use_cache": use_cache,
                        "conversation_history": history,
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()

                answer = data["answer"]
                st.markdown(answer)

                meta = {
                    "latency_ms": data.get("latency_ms", 0),
                    "retrieval_count": data.get("retrieval_count", 0),
                    "rewritten_query": data.get("rewritten_query"),
                }
                cols = st.columns(3)
                cols[0].caption(f"⏱️ {meta['latency_ms']:.0f} ms")
                cols[1].caption(f"📄 {meta['retrieval_count']} chunks retrieved")
                if meta.get("rewritten_query"):
                    cols[2].caption(f"✏️ Rewritten: _{meta['rewritten_query']}_")

                # Citations expander
                citations = data.get("citations", [])
                if citations:
                    with st.expander(f"📚 View {len(citations)} source(s)"):
                        for i, cite in enumerate(citations, 1):
                            st.markdown(
                                f"**{i}. {cite['filename']}** "
                                f"— Page {cite.get('page', '?')} | {cite.get('section', '')} "
                                f"(score: {cite['score']:.3f})"
                            )
                            st.caption(cite["chunk_text"][:300] + "…")
                            st.divider()

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "meta": meta,
                })

            except httpx.TimeoutException:
                st.error("⏳ Request timed out. The model may still be loading. Try again in 30 seconds.")
            except httpx.HTTPStatusError as e:
                st.error(f"❌ Backend error: {e.response.status_code}")
            except Exception as e:
                st.error(f"❌ Unexpected error: {str(e)}")
