DO $$ DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT schemaname, viewname
        FROM pg_views
        WHERE schemaname = 'public'
    ) LOOP
        EXECUTE 'DROP VIEW IF EXISTS public.' || quote_ident(r.viewname) || ' CASCADE';
    END LOOP;

    FOR r IN (
        SELECT schemaname, matviewname
        FROM pg_matviews
        WHERE schemaname = 'public'
    ) LOOP
        EXECUTE 'DROP MATERIALIZED VIEW IF EXISTS public.' || quote_ident(r.matviewname) || ' CASCADE';
    END LOOP;

    FOR r IN (
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    ) LOOP
        EXECUTE 'DROP TABLE IF EXISTS public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;

    FOR r IN (
        SELECT sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'public'
    ) LOOP
        EXECUTE 'DROP SEQUENCE IF EXISTS public.' || quote_ident(r.sequence_name) || ' CASCADE';
    END LOOP;

    FOR r IN (
        SELECT p.proname, pg_get_function_identity_arguments(p.oid) AS args
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public'
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend d
              WHERE d.objid = p.oid
                AND d.deptype = 'e'
          )
    ) LOOP
        EXECUTE 'DROP FUNCTION IF EXISTS public.' || quote_ident(r.proname) || '(' || r.args || ') CASCADE';
    END LOOP;

    FOR r IN (
        SELECT typname
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'public'
          AND t.typtype = 'e'
    ) LOOP
        EXECUTE 'DROP TYPE IF EXISTS public.' || quote_ident(r.typname) || ' CASCADE';
    END LOOP;
END $$;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        CREATE ROLE anon NOLOGIN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
END $$;

CREATE TYPE public.document_change_type AS ENUM ('created', 'updated', 'deleted');
CREATE TYPE public.document_content_type AS ENUM ('raw', 'clean', 'table', 'attachment', 'image', 'html');
CREATE TYPE public.document_asset_type AS ENUM ('attachment', 'image', 'file');
CREATE TYPE public.chunk_section_type AS ENUM ('title', 'body', 'table', 'attachment', 'image', 'html', 'other');
CREATE TYPE public.crawl_run_type AS ENUM ('scheduled', 'manual', 'retry', 'backfill');
CREATE TYPE public.retrieval_stage AS ENUM ('initial', 'fallback', 'retry', 'rerank');
CREATE TYPE public.retrieval_strategy AS ENUM ('vector', 'hybrid', 'keyword');
CREATE TYPE public.intent_type AS ENUM ('GENERAL', 'INFO', 'PROFANITY', 'OTHER');

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.set_db_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.db_updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE public.documents (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    page_kind TEXT,
    department TEXT,
    title TEXT NOT NULL,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    content_hash TEXT,
    collected_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    db_updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.document_versions (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES public.documents(doc_id) ON UPDATE CASCADE ON DELETE CASCADE,
    version INT NOT NULL,
    content_hash TEXT,
    change_type public.document_change_type NOT NULL,
    snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_versions_doc_id_version_key UNIQUE (doc_id, version)
);

CREATE TABLE public.document_assets (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES public.documents(doc_id) ON UPDATE CASCADE ON DELETE CASCADE,
    asset_type public.document_asset_type NOT NULL,
    asset_index INT NOT NULL DEFAULT 0,
    file_name TEXT,
    file_url TEXT,
    file_ext TEXT,
    saved_path TEXT,
    file_size BIGINT,
    content_type TEXT,
    parser_type TEXT,
    page_count INT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT document_assets_doc_assettype_assetindex_key UNIQUE (doc_id, asset_type, asset_index)
);

CREATE TABLE public.document_contents (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES public.documents(doc_id) ON UPDATE CASCADE ON DELETE CASCADE,
    asset_id BIGINT REFERENCES public.document_assets(id) ON UPDATE CASCADE ON DELETE SET NULL,
    document_version_id BIGINT REFERENCES public.document_versions(id) ON UPDATE CASCADE ON DELETE SET NULL,
    content_type public.document_content_type NOT NULL,
    content TEXT NOT NULL,
    parser_type TEXT,
    parser_version TEXT,
    language TEXT DEFAULT 'ko',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE,
    doc_id TEXT NOT NULL REFERENCES public.documents(doc_id) ON UPDATE CASCADE ON DELETE CASCADE,
    document_version_id BIGINT REFERENCES public.document_versions(id) ON UPDATE CASCADE ON DELETE SET NULL,
    content_id BIGINT REFERENCES public.document_contents(id) ON UPDATE CASCADE ON DELETE SET NULL,
    chunk_index INT NOT NULL,
    section_index INT,
    section_type public.chunk_section_type,
    section_title TEXT,
    content TEXT NOT NULL,
    content_length INT,
    content_hash TEXT,
    chunking_strategy TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chunks_doc_version_chunk_index_key UNIQUE (doc_id, document_version_id, chunk_index)
);

CREATE TABLE public.chunk_embeddings (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL REFERENCES public.chunks(chunk_id) ON UPDATE CASCADE ON DELETE CASCADE,
    embedding VECTOR(1024) NOT NULL,
    model_name TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chunk_embeddings_chunk_id_model_name_key UNIQUE (chunk_id, model_name)
);

CREATE TABLE public.crawl_logs (
    id BIGSERIAL PRIMARY KEY,
    job_id UUID NOT NULL DEFAULT gen_random_uuid(),
    run_type public.crawl_run_type NOT NULL DEFAULT 'manual',
    stage TEXT,
    source_type TEXT,
    doc_id TEXT,
    url TEXT,
    file_url TEXT,
    file_path TEXT,
    error_type TEXT,
    error_message TEXT,
    traceback TEXT,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.query_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    user_id TEXT,
    question TEXT NOT NULL,
    intent_type public.intent_type NOT NULL DEFAULT 'OTHER',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.response_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE REFERENCES public.query_logs(request_id) ON UPDATE CASCADE ON DELETE CASCADE,
    answer_text TEXT,
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    response_time_ms INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.retrieval_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL REFERENCES public.query_logs(request_id) ON UPDATE CASCADE ON DELETE CASCADE,
    attempt_no INT NOT NULL DEFAULT 1,
    stage public.retrieval_stage NOT NULL DEFAULT 'initial',
    original_query TEXT,
    normalized_query TEXT,
    rewritten_query TEXT,
    rewritten_queries TEXT[],
    keywords TEXT[],
    entities JSONB NOT NULL DEFAULT '{}'::jsonb,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    category TEXT,
    retrieval_strategy public.retrieval_strategy,
    retrieval_top_k INT,
    retrieval_strategy_log JSONB NOT NULL DEFAULT '{}'::jsonb,
    fallback_used BOOLEAN NOT NULL DEFAULT false,
    retrieved_doc_count INT,
    reranked_doc_count INT,
    selected_doc_count INT,
    context TEXT,
    success BOOLEAN NOT NULL DEFAULT true,
    error_message TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT retrieval_logs_request_attempt_stage_key UNIQUE (request_id, attempt_no, stage)
);

CREATE TABLE public.retrieval_selected_chunks (
    id BIGSERIAL PRIMARY KEY,
    retrieval_log_id BIGINT NOT NULL REFERENCES public.retrieval_logs(id) ON UPDATE CASCADE ON DELETE CASCADE,
    chunk_id TEXT REFERENCES public.chunks(chunk_id) ON UPDATE CASCADE ON DELETE SET NULL,
    raw_chunk_id TEXT,
    doc_id TEXT,
    rank INT NOT NULL,
    score DOUBLE PRECISION,
    rerank_score DOUBLE PRECISION,
    title_snapshot TEXT,
    source_snapshot TEXT,
    content_snapshot TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT retrieval_selected_chunks_log_rank_key UNIQUE (retrieval_log_id, rank)
);

CREATE TRIGGER trg_documents_set_db_updated_at
BEFORE UPDATE ON public.documents
FOR EACH ROW EXECUTE FUNCTION public.set_db_updated_at();

CREATE TRIGGER trg_chunks_set_updated_at
BEFORE UPDATE ON public.chunks
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_chunk_embeddings_set_updated_at
BEFORE UPDATE ON public.chunk_embeddings
FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE INDEX idx_documents_source_type ON public.documents(source_type);
CREATE INDEX idx_documents_department ON public.documents(department);
CREATE INDEX idx_documents_published_at ON public.documents(published_at DESC);
CREATE INDEX idx_documents_collected_at ON public.documents(collected_at DESC);
CREATE INDEX idx_documents_metadata_gin ON public.documents USING GIN (metadata);

CREATE INDEX idx_document_versions_doc_id ON public.document_versions(doc_id);
CREATE INDEX idx_document_versions_created_at ON public.document_versions(created_at DESC);

CREATE INDEX idx_document_assets_doc_id ON public.document_assets(doc_id);
CREATE INDEX idx_document_assets_asset_type ON public.document_assets(asset_type);
CREATE INDEX idx_document_assets_file_ext ON public.document_assets(file_ext);

CREATE INDEX idx_document_contents_doc_id ON public.document_contents(doc_id);
CREATE INDEX idx_document_contents_asset_id ON public.document_contents(asset_id);
CREATE INDEX idx_document_contents_document_version_id ON public.document_contents(document_version_id);
CREATE INDEX idx_document_contents_content_type ON public.document_contents(content_type);

CREATE INDEX idx_chunks_doc_id ON public.chunks(doc_id);
CREATE INDEX idx_chunks_document_version_id ON public.chunks(document_version_id);
CREATE INDEX idx_chunks_content_id ON public.chunks(content_id);
CREATE INDEX idx_chunks_section_type ON public.chunks(section_type);
CREATE INDEX idx_chunks_metadata_gin ON public.chunks USING GIN (metadata);

CREATE INDEX idx_chunk_embeddings_chunk_id ON public.chunk_embeddings(chunk_id);
CREATE INDEX idx_chunk_embeddings_embedding_hnsw ON public.chunk_embeddings
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_crawl_logs_job_id ON public.crawl_logs(job_id);
CREATE INDEX idx_crawl_logs_doc_id ON public.crawl_logs(doc_id);
CREATE INDEX idx_crawl_logs_created_at ON public.crawl_logs(created_at DESC);

CREATE INDEX idx_query_logs_user_id ON public.query_logs(user_id);
CREATE INDEX idx_query_logs_created_at ON public.query_logs(created_at DESC);

CREATE INDEX idx_retrieval_logs_request_id ON public.retrieval_logs(request_id);
CREATE INDEX idx_retrieval_logs_created_at ON public.retrieval_logs(created_at DESC);

CREATE INDEX idx_retrieval_selected_chunks_retrieval_log_id ON public.retrieval_selected_chunks(retrieval_log_id);
CREATE INDEX idx_retrieval_selected_chunks_chunk_id ON public.retrieval_selected_chunks(chunk_id);
CREATE INDEX idx_retrieval_selected_chunks_doc_id ON public.retrieval_selected_chunks(doc_id);

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_contents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chunk_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crawl_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.query_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.response_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.retrieval_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.retrieval_selected_chunks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "authenticated read documents"
ON public.documents FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated read document versions"
ON public.document_versions FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated read document assets"
ON public.document_assets FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated read document contents"
ON public.document_contents FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated read chunks"
ON public.chunks FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated read chunk embeddings"
ON public.chunk_embeddings FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated read crawl logs"
ON public.crawl_logs FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated insert query logs"
ON public.query_logs FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "authenticated read query logs"
ON public.query_logs FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated insert response logs"
ON public.response_logs FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "authenticated read response logs"
ON public.response_logs FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated insert retrieval logs"
ON public.retrieval_logs FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "authenticated read retrieval logs"
ON public.retrieval_logs FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "authenticated insert retrieval selected chunks"
ON public.retrieval_selected_chunks FOR INSERT
TO authenticated
WITH CHECK (true);

CREATE POLICY "authenticated read retrieval selected chunks"
ON public.retrieval_selected_chunks FOR SELECT
TO authenticated
USING (true);
