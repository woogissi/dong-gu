-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- documents
CREATE TABLE IF NOT EXISTS documents (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    category_main TEXT NOT NULL,
    category_sub TEXT,
    url TEXT,
    posted_at TIMESTAMP,
    collected_at TIMESTAMP NOT NULL,
    raw_text TEXT,
    keywords TEXT[],
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- chunks
CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE,
    doc_id TEXT NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    content_length INT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_chunks_doc
        FOREIGN KEY (doc_id)
        REFERENCES documents(doc_id)
        ON DELETE CASCADE
);

-- chunk_embeddings
CREATE TABLE IF NOT EXISTS chunk_embeddings (
    chunk_id TEXT PRIMARY KEY,
    embedding VECTOR(1536),
    model_name TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_embedding_chunk
        FOREIGN KEY (chunk_id)
        REFERENCES chunks(chunk_id)
        ON DELETE CASCADE
);

-- crawl_job
CREATE TABLE IF NOT EXISTS crawl_job (
    id BIGSERIAL PRIMARY KEY,
    job_name TEXT,
    source TEXT,
    status TEXT,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- source_sync_history
CREATE TABLE IF NOT EXISTS source_sync_history (
    id BIGSERIAL PRIMARY KEY,
    source TEXT,
    doc_id TEXT,
    change_type TEXT,
    synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
    crawl_job_id BIGINT,
    CONSTRAINT fk_sync_job
        FOREIGN KEY (crawl_job_id)
        REFERENCES crawl_job(id)
        ON DELETE SET NULL
);

-- qa_logs
CREATE TABLE IF NOT EXISTS qa_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT,
    question TEXT,
    answer TEXT,
    retrieved_chunks TEXT[],
    response_time FLOAT,
    intent_type TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- indexes
CREATE INDEX IF NOT EXISTS idx_documents_category_main
    ON documents(category_main);

CREATE INDEX IF NOT EXISTS idx_documents_doc_type
    ON documents(doc_type);

CREATE INDEX IF NOT EXISTS idx_documents_posted_at
    ON documents(posted_at);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
    ON chunks(doc_id);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id_chunk_index
    ON chunks(doc_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_vector
    ON chunk_embeddings
    USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_chunks_fts
    ON chunks
    USING GIN (to_tsvector('simple', content));