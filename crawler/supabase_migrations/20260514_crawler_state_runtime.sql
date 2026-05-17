-- Idempotent crawler state runtime migration.
-- Apply only through the crawler's private DB connection. RLS is enabled below; REST/Data API
-- policies are intentionally not opened by default.

CREATE TABLE IF NOT EXISTS public.crawler_documents (
  id bigserial PRIMARY KEY,
  doc_id text,
  url text NOT NULL,
  canonical_url text NOT NULL UNIQUE,
  final_url text,
  status text NOT NULL,
  source_type text,
  page_kind text,
  checksum text,
  retry_count integer NOT NULL DEFAULT 0,
  artifact_paths jsonb NOT NULL DEFAULT '{}'::jsonb,
  extractor_name text,
  extractor_version text,
  last_error text,
  last_error_stage text,
  next_retry_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.crawler_dynamic_seeds (
  id bigserial PRIMARY KEY,
  url text NOT NULL,
  canonical_url text NOT NULL UNIQUE,
  confidence numeric NOT NULL,
  source_type text,
  source_group text,
  page_kind text NOT NULL,
  pattern_reason text,
  discovered_from text,
  status text NOT NULL DEFAULT 'candidate',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.crawler_retry_queue (
  id bigserial PRIMARY KEY,
  doc_id text,
  url text,
  source_type text,
  page_kind text,
  file_path text,
  stage text NOT NULL,
  task_type text,
  reason text NOT NULL,
  retry_count integer NOT NULL DEFAULT 0,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 3,
  next_retry_at timestamptz,
  status text NOT NULL DEFAULT 'pending',
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  last_attempt_at timestamptz,
  resolved_at timestamptz,
  dead_lettered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS task_type text;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS payload jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS last_error text;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS resolved_at timestamptz;
ALTER TABLE public.crawler_retry_queue ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;

UPDATE public.crawler_retry_queue
SET task_type = COALESCE(task_type, stage),
    attempts = GREATEST(attempts, retry_count)
WHERE task_type IS NULL
   OR attempts < retry_count;

CREATE INDEX IF NOT EXISTS idx_crawler_documents_status ON public.crawler_documents(status);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_updated_at ON public.crawler_documents(updated_at);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_source_type ON public.crawler_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_status ON public.crawler_dynamic_seeds(status);
CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_confidence ON public.crawler_dynamic_seeds(confidence);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_status ON public.crawler_retry_queue(status);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_stage ON public.crawler_retry_queue(stage);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_task_type ON public.crawler_retry_queue(task_type);

ALTER TABLE public.crawler_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crawler_dynamic_seeds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.crawler_retry_queue ENABLE ROW LEVEL SECURITY;

-- Optional REST/Data API policy example, not applied by default:
-- CREATE POLICY crawler_service_role_all ON public.crawler_retry_queue
--   FOR ALL TO service_role USING (true) WITH CHECK (true);
