CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS response_logs CASCADE;
DROP TABLE IF EXISTS retrieval_logs CASCADE;
DROP TABLE IF EXISTS query_logs CASCADE;
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
    source_type TEXT NOT NULL,
    page_kind TEXT NOT NULL,
    department TEXT,
    title TEXT NOT NULL,
    source_url TEXT,
    published_at TIMESTAMP,
    updated_at TIMESTAMP,
    raw_text TEXT,
    clean_text TEXT,
    table_text TEXT,
    attachment_text TEXT,
    image_text TEXT,
    version INT DEFAULT 1,
    content_hash TEXT,
    collected_at TIMESTAMP NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
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
    section_index INT,
    section_type TEXT,
    section_title TEXT,
    content TEXT NOT NULL,
    content_length INT,
    content_hash TEXT,
    version INT DEFAULT 1,
    metadata JSONB DEFAULT '{}'::jsonb,
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
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT fk_embedding_chunk
        FOREIGN KEY (chunk_id)
        REFERENCES chunks(chunk_id)
        ON DELETE CASCADE
);

CREATE TABLE crawl_jobs (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL DEFAULT gen_random_uuid(),
    run_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    source_type TEXT,
    doc_id TEXT,
    url TEXT,
    file_url TEXT,
    file_path TEXT,
    error_type TEXT,
    error_message TEXT NOT NULL,
    traceback TEXT,

    context JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT NOW()
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

CREATE TABLE query_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE,
    user_id TEXT,
    question TEXT NOT NULL,
    intent_type TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at_kst TIMESTAMP
    GENERATED ALWAYS AS (created_at + INTERVAL '9 hours') STORED
);

CREATE TABLE retrieval_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE REFERENCES query_logs(request_id),

    original_query TEXT NOT NULL,
    normalized_query TEXT,
    rewritten_query TEXT,
    rewritten_queries TEXT[] DEFAULT '{}',

    keywords TEXT[] DEFAULT '{}',
    entities JSONB DEFAULT '{}'::jsonb,
    filters JSONB DEFAULT '{}'::jsonb,
    category TEXT,

    retrieval_strategy TEXT NOT NULL,
    retrieval_top_k INT NOT NULL,
    retrieval_strategy_log JSONB DEFAULT '{}'::jsonb,

    fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
    retrieved_doc_count INT NOT NULL DEFAULT 0,
    reranked_doc_count INT NOT NULL DEFAULT 0,
    selected_doc_count INT NOT NULL DEFAULT 0,
    selected_chunk_ids TEXT[] DEFAULT '{}',
    selected_documents JSONB DEFAULT '[]'::jsonb,
    context TEXT,

    success BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    created_at_kst TIMESTAMP
    GENERATED ALWAYS AS (created_at + INTERVAL '9 hours') STORED
);

CREATE TABLE response_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE REFERENCES query_logs(request_id),

    answer_text TEXT,
    success BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    response_time_ms INT,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    created_at_kst TIMESTAMP
    GENERATED ALWAYS AS (created_at + INTERVAL '9 hours') STORED
);

CREATE INDEX idx_documents_doc_id
ON documents(doc_id);

CREATE INDEX idx_documents_source_type
ON documents(source_type);

CREATE INDEX idx_documents_published_at
ON documents(published_at);

CREATE INDEX idx_documents_content_hash
ON documents(content_hash);

CREATE INDEX idx_chunks_doc_id
ON chunks(doc_id);

CREATE INDEX idx_chunks_chunk_id
ON chunks(chunk_id);

CREATE INDEX idx_chunks_section_type
ON chunks(section_type);

CREATE INDEX idx_chunk_embeddings_vector
ON chunk_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

CREATE INDEX idx_chunks_fts
ON chunks
USING GIN (to_tsvector('simple', content));

CREATE INDEX idx_assets_doc_id
ON document_assets(doc_id);

CREATE INDEX idx_assets_type
ON document_assets(asset_type);

CREATE INDEX idx_query_logs_created_at
ON query_logs(created_at);

CREATE INDEX idx_query_logs_user_id
ON query_logs(user_id);

CREATE INDEX idx_query_logs_intent_type
ON query_logs(intent_type);

CREATE INDEX idx_response_logs_created_at
ON response_logs(created_at);

CREATE INDEX idx_response_logs_success
ON response_logs(success);

CREATE INDEX idx_crawl_jobs_status
ON crawl_jobs(status);

CREATE INDEX idx_crawl_jobs_started_at
ON crawl_jobs(started_at);

CREATE INDEX idx_sync_doc_id
ON source_sync_history(doc_id);

CREATE INDEX idx_sync_change_type
ON source_sync_history(change_type);

CREATE INDEX idx_retrieval_created_at
ON retrieval_logs(created_at);

CREATE INDEX idx_retrieval_strategy
ON retrieval_logs(retrieval_strategy);

CREATE INDEX idx_retrieval_success
ON retrieval_logs(success);
