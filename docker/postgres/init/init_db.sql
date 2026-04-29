CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS retrieval_logs CASCADE;
DROP TABLE IF EXISTS qa_logs CASCADE;
DROP TABLE IF EXISTS source_sync_history CASCADE;
DROP TABLE IF EXISTS crawl_jobs CASCADE;
DROP TABLE IF EXISTS chunk_embeddings CASCADE;
DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS document_assets CASCADE;
DROP TABLE IF EXISTS document_versions CASCADE;
DROP TABLE IF EXISTS documents CASCADE;

CREATE TABLE documents (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL UNIQUE,
    parent_doc_id TEXT,
    source_type TEXT NOT NULL,
    page_kind TEXT NOT NULL,
    category_lv1 TEXT,
    category_lv2 TEXT,
    department TEXT,
    title TEXT NOT NULL,
    summary TEXT,
    source_url TEXT,
    published_at TIMESTAMP,
    updated_at TIMESTAMP,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    target_audience TEXT[] DEFAULT '{}',
    keywords TEXT[] DEFAULT '{}',
    raw_text TEXT,
    clean_text TEXT,
    table_text TEXT,
    attachment_text TEXT,
    image_text TEXT,
    language TEXT DEFAULT 'ko',
    status TEXT DEFAULT 'active',
    version INT DEFAULT 1,
    content_hash TEXT,
    collected_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    db_updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE document_versions (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL,
    version INT NOT NULL,
    content_hash TEXT,
    change_type TEXT NOT NULL,
    snapshot JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_document_versions_doc
        FOREIGN KEY (doc_id)
        REFERENCES documents(doc_id)
        ON DELETE CASCADE,
    CONSTRAINT uq_document_version
        UNIQUE (doc_id, version)
);

CREATE TABLE document_assets (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    asset_index INT,
    file_name TEXT,
    file_url TEXT,
    file_ext TEXT,
    saved_path TEXT,
    content_type TEXT,
    file_size BIGINT,
    parser_type TEXT,
    extracted_text TEXT,
    page_count INT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_document_assets_doc
        FOREIGN KEY (doc_id)
        REFERENCES documents(doc_id)
        ON DELETE CASCADE
);

CREATE TABLE chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE,
    doc_id TEXT NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    content_length INT,
    content_hash TEXT,
    version INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_chunks_doc
        FOREIGN KEY (doc_id)
        REFERENCES documents(doc_id)
        ON DELETE CASCADE
);

CREATE TABLE chunk_embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding VECTOR(1024),
    model_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_embedding_chunk
        FOREIGN KEY (chunk_id)
        REFERENCES chunks(chunk_id)
        ON DELETE CASCADE
);

CREATE TABLE crawl_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_name TEXT,
    source_type TEXT,
    status TEXT DEFAULT 'pending',
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    total_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    error_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE source_sync_history (
    id BIGSERIAL PRIMARY KEY,
    crawl_job_id BIGINT,
    source_type TEXT,
    doc_id TEXT,
    change_type TEXT NOT NULL,
    old_hash TEXT,
    new_hash TEXT,
    old_version INT,
    new_version INT,
    message TEXT,
    synced_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_sync_job
        FOREIGN KEY (crawl_job_id)
        REFERENCES crawl_jobs(id)
        ON DELETE SET NULL
);

CREATE TABLE qa_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    question TEXT NOT NULL,
    normalized_question TEXT,
    rewritten_question TEXT,
    answer TEXT,
    retrieved_chunks TEXT[] DEFAULT '{}',
    source_doc_ids TEXT[] DEFAULT '{}',
    response_time FLOAT,
    intent_type TEXT,
    fallback_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE retrieval_logs (
    id BIGSERIAL PRIMARY KEY,
    qa_log_id BIGINT,
    query TEXT,
    retrieval_strategy TEXT,
    chunk_id TEXT,
    doc_id TEXT,
    vector_score FLOAT,
    keyword_score FLOAT,
    final_score FLOAT,
    rank INT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_retrieval_qa
        FOREIGN KEY (qa_log_id)
        REFERENCES qa_logs(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_documents_doc_id
ON documents(doc_id);

CREATE INDEX idx_documents_source_type
ON documents(source_type);

CREATE INDEX idx_documents_category
ON documents(category_lv1, category_lv2);

CREATE INDEX idx_documents_published_at
ON documents(published_at);

CREATE INDEX idx_documents_content_hash
ON documents(content_hash);

CREATE INDEX idx_chunks_doc_id
ON chunks(doc_id);

CREATE INDEX idx_chunks_chunk_id
ON chunks(chunk_id);

CREATE INDEX idx_chunk_embeddings_vector
ON chunk_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX idx_chunks_fts
ON chunks
USING GIN (to_tsvector('simple' content));

CREATE INDEX idx_assets_doc_id
ON document_assets(doc_id);

CREATE INDEX idx_assets_type
ON document_assets(asset_type);

CREATE INDEX idx_sync_doc_id
ON source_sync_history(doc_id);

CREATE INDEX idx_sync_change_type
ON source_sync_history(change_type);