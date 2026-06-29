"""
Document Management — upload, view, delete documents.
"""
import streamlit as st
import httpx
import os
import pandas as pd

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Document Management", page_icon="📁", layout="wide")
st.title("📁 Document Management")
st.caption("Upload, monitor, and manage your indexed documents.")

# ── Upload Section ─────────────────────────────────────────────────────────
st.subheader("Upload New Document")
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["pdf", "docx", "pptx", "xlsx", "txt", "md"],
        help="PDF, Word, PowerPoint, Excel, or plain text",
    )
with col2:
    department = st.selectbox(
        "Department", ["general", "hr", "finance", "legal", "engineering", "operations"]
    )
with col3:
    tags_input = st.text_input("Tags (comma-separated)", placeholder="policy, 2024")

if st.button("📤 Upload & Index", disabled=uploaded_file is None, type="primary"):
    with st.spinner(f"Uploading {uploaded_file.name}…"):
        try:
            resp = httpx.post(
                f"{BACKEND_URL}/api/v1/documents/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
                params={"department": department, "tags": tags_input or None},
                timeout=60,
            )
            resp.raise_for_status()
            doc = resp.json()
            st.success(
                f"✅ **{doc['filename']}** uploaded (ID: `{doc['id']}`). "
                f"Indexing in background — status will update to **indexed** shortly."
            )
        except Exception as e:
            st.error(f"❌ Upload failed: {e}")

st.divider()

# ── Document List ─────────────────────────────────────────────────────────
st.subheader("Indexed Documents")
col1, col2 = st.columns(2)
with col1:
    filter_dept = st.selectbox(
        "Filter department",
        ["All", "general", "hr", "finance", "legal", "engineering", "operations"],
    )
with col2:
    filter_status = st.selectbox("Filter status", ["All", "indexed", "processing", "pending", "failed"])

try:
    params = {"page": 1, "page_size": 50}
    if filter_dept != "All":
        params["department"] = filter_dept
    if filter_status != "All":
        params["status"] = filter_status

    resp = httpx.get(f"{BACKEND_URL}/api/v1/documents/", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    docs = data["documents"]

    if not docs:
        st.info("No documents found. Upload some files to get started.")
    else:
        st.caption(f"Showing {len(docs)} of {data['total']} documents")
        df = pd.DataFrame([
            {
                "Filename": d["filename"],
                "Department": d["department"],
                "Status": d["status"],
                "Chunks": d["chunk_count"],
                "Tags": ", ".join(d.get("tags") or []),
                "Created": d["created_at"][:10],
                "ID": d["id"],
            }
            for d in docs
        ])

        status_colors = {
            "indexed": "🟢",
            "processing": "🟡",
            "pending": "⚪",
            "failed": "🔴",
            "deleted": "⚫",
        }
        df["Status"] = df["Status"].apply(lambda s: f"{status_colors.get(s, '')} {s}")

        st.dataframe(df.drop(columns=["ID"]), use_container_width=True, hide_index=True)

        # Delete section
        st.subheader("Delete Document")
        doc_options = {f"{d['filename']} ({d['id'][:8]}…)": d["id"] for d in docs}
        selected = st.selectbox("Select document to delete", list(doc_options.keys()))
        if st.button("🗑️ Delete", type="secondary"):
            doc_id = doc_options[selected]
            try:
                resp = httpx.delete(f"{BACKEND_URL}/api/v1/documents/{doc_id}", timeout=10)
                if resp.status_code == 204:
                    st.success("Document deleted from all indexes.")
                    st.rerun()
                else:
                    st.error(f"Delete failed: {resp.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

except Exception as e:
    st.error(f"Could not fetch documents: {e}")
