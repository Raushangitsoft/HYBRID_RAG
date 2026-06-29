# 🔍 Hybrid RAG System
### Production-Grade Internal Document Intelligence Platform
**100% On-Premises · No Cloud LLM · CPU-Friendly**

---

## Architecture

```
User → Streamlit UI → FastAPI Backend → LangGraph Orchestrator
                                       ↓
              Query Rewrite → Hybrid Search (BM25 + Vector) → Reranker
                              ├── Elasticsearch (BM25)
                              └── Qdrant (Dense Vector)
                                       ↓
                              Context Assembly → Ollama (Qwen2.5 7B)
                                       ↓
                              Answer + Citations → User
```

## Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Streamlit | Chat UI, document management |
| Backend | FastAPI | REST API, orchestration |
| LLM | Qwen2.5 7B via Ollama | Answer generation (CPU/16GB RAM) |
| Embeddings | BAAI/bge-m3 | Dense vector generation |
| Reranker | BAAI/bge-reranker-large | Cross-encoder reranking |
| Vector DB | Qdrant | Semantic similarity search |
| Keyword Search | Elasticsearch | BM25 full-text search |
| Metadata DB | PostgreSQL | Document metadata & status |
| Cache | Redis | Query/embedding/response cache |
| Document Store | Local disk | Raw document storage |
| Parsing | Docling | Layout-aware PDF/DOCX/PPTX/Excel |

---

## Quick Start on AWS EC2

### Recommended EC2 Instance
- **Instance type**: `t3.2xlarge` or `m5.2xlarge` (8 vCPU, 16–32GB RAM)
- **Storage**: 100GB+ gp3 EBS
- **OS**: Ubuntu 22.04 LTS
- **Security Group**: Open ports 22, 8000, 8501

### 1. Launch & Connect
```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

### 2. Install Docker
```bash
git clone <your-repo> hybrid-rag
cd hybrid-rag
sudo bash scripts/manage.sh install-docker
# Log out and back in so docker group takes effect
exit
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

### 3. Initialize
```bash
cd hybrid-rag
bash scripts/manage.sh setup
# Edit .env if needed (e.g. change POSTGRES_PASSWORD)
nano .env
```

### 4. Build & Start
```bash
bash scripts/manage.sh build
bash scripts/manage.sh start
```
This builds images, starts all containers, and **automatically pulls Qwen2.5 7B** (~4.5GB GGUF).

### 5. Access
| Service | URL |
|---------|-----|
| Chat UI | `http://<EC2_IP>:8501` |
| API Docs | `http://<EC2_IP>:8000/docs` |
| Backend Health | `http://<EC2_IP>:8000/health` |

---

## Usage

### Upload Documents
1. Go to **📁 Documents** in the sidebar
2. Upload PDF, DOCX, PPTX, XLSX, or TXT files
3. Select department and tags
4. Status changes from `pending` → `processing` → `indexed`

### Chat
1. Go to **Home** page
2. Type your question
3. Get answers with citations showing source document, page, and section

### API
```bash
# Upload
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@report.pdf" \
  -F "department=finance"

# Query
curl -X POST http://localhost:8000/api/v1/query/ \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the leave policy?", "department": "hr"}'
```

---

## Management Commands

```bash
bash scripts/manage.sh status       # Check all services
bash scripts/manage.sh logs         # Tail all logs
bash scripts/manage.sh logs backend # Tail backend logs
bash scripts/manage.sh restart      # Restart all services
bash scripts/manage.sh pull-model   # Re-pull LLM model
bash scripts/manage.sh backup       # Backup PostgreSQL
bash scripts/manage.sh stop         # Stop everything
bash scripts/manage.sh reset        # Wipe all data (DESTRUCTIVE)
```

---

## Performance Notes (16GB RAM, CPU only)

| Component | RAM Usage | Notes |
|-----------|-----------|-------|
| Ollama + Qwen2.5 7B | ~6–8GB | GGUF quantized, CPU inference |
| Elasticsearch | 2GB | Configured with `-Xms1g -Xmx2g` |
| Qdrant | ~512MB | Depends on corpus size |
| Redis | 512MB | Capped with `maxmemory` |
| PostgreSQL | ~256MB | Lightweight |
| Backend (embeddings) | ~2GB | BGE-m3 loaded in process |

**Expected query latency (CPU):** 30–120 seconds depending on context size.
Use the **cache** (enabled by default) for repeated queries — cached responses return in <1s.

---

## Folder Structure

```
hybrid-rag/
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── api/v1/endpoints/ # REST endpoints
│   │   ├── core/             # Config, DB, cache, logging
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   └── services/
│   │       ├── ingestion/    # Document parsing & indexing
│   │       ├── retrieval/    # Hybrid search, reranker, embeddings
│   │       └── llm/          # Ollama client, RAG pipeline
│   └── Dockerfile
├── frontend/                 # Streamlit UI
│   ├── Home.py               # Main chat page
│   └── pages/
│       ├── 1_📁_Documents.py # Document management
│       └── 2_📊_System_Health.py
├── docker/                   # Service configs
│   ├── qdrant/config.yaml
│   ├── postgres/init.sql
│   └── redis/redis.conf
├── scripts/manage.sh         # Management CLI
├── data/                     # Persistent data (gitignored)
│   └── documents/            # Uploaded files on local disk
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Troubleshooting

**Ollama model not loading**
```bash
docker exec -it rag-ollama ollama list
bash scripts/manage.sh pull-model
```

**Elasticsearch won't start**
```bash
sudo sysctl -w vm.max_map_count=262144
docker compose restart elasticsearch
```

**Backend OOM (out of memory)**
- Reduce `ES_JAVA_OPTS` to `-Xms512m -Xmx1g` in docker-compose.yml
- Reduce Redis `maxmemory` to `256mb`
- Ensure you have at least 14GB free RAM before starting

**Slow first query**
The reranker model (BGE-reranker-large) loads lazily on the first query and takes ~60s on CPU. Subsequent queries are faster.
