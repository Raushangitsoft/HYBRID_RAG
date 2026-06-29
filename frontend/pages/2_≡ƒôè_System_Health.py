"""
System Health Dashboard
"""
import streamlit as st
import httpx
import os
import time

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="System Health", page_icon="📊", layout="wide")
st.title("📊 System Health Dashboard")

if st.button("🔄 Refresh"):
    st.rerun()

try:
    resp = httpx.get(f"{BACKEND_URL}/api/v1/health/detailed", timeout=15)
    data = resp.json()
except Exception as e:
    st.error(f"Cannot reach backend: {e}")
    st.stop()

# Overall status
overall = data.get("status", "unknown")
if overall == "ok":
    st.success("🟢 All systems operational")
elif overall == "degraded":
    st.warning("🟡 Some services degraded")
else:
    st.error("🔴 System issues detected")

st.divider()

# Service status cards
services = data.get("services", {})
cols = st.columns(4)
service_info = {
    "ollama": ("🤖", "Ollama LLM", "Qwen2.5 7B inference"),
    "qdrant": ("🔷", "Qdrant", "Vector database"),
    "elasticsearch": ("🔍", "Elasticsearch", "BM25 keyword search"),
    "redis": ("⚡", "Redis", "Cache layer"),
}

for i, (svc_key, (icon, name, desc)) in enumerate(service_info.items()):
    status = services.get(svc_key, "unknown")
    color = {"ok": "🟢", "degraded": "🟡", "down": "🔴"}.get(status, "⚪")
    with cols[i]:
        st.metric(label=f"{icon} {name}", value=f"{color} {status.upper()}")
        st.caption(desc)

st.divider()
st.caption(f"Last checked: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
st.info("💡 For detailed metrics and logs, connect Prometheus + Grafana (optional add-on).")
