-- Hybrid RAG System — PostgreSQL Initialization
-- Tables are also created via SQLAlchemy on startup, this is for reference/backup

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Ensure the documents table (fallback if SQLAlchemy migration hasn't run)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(512) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    department VARCHAR(128) DEFAULT 'general',
    owner VARCHAR(256) DEFAULT 'system',
    status VARCHAR(32) DEFAULT 'pending',
    confidentiality VARCHAR(32) DEFAULT 'internal',
    tags TEXT[],
    file_path TEXT,
    content_hash VARCHAR(64),
    chunk_count INTEGER DEFAULT 0,
    version INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_department ON documents(department);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
