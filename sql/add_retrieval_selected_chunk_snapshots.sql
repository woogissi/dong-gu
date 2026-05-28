-- Preserve selected RAG evidence even when the chunk FK cannot be resolved.

ALTER TABLE public.retrieval_selected_chunks
    ADD COLUMN IF NOT EXISTS raw_chunk_id TEXT,
    ADD COLUMN IF NOT EXISTS title_snapshot TEXT,
    ADD COLUMN IF NOT EXISTS source_snapshot TEXT,
    ADD COLUMN IF NOT EXISTS content_snapshot TEXT;

CREATE INDEX IF NOT EXISTS idx_retrieval_selected_chunks_raw_chunk_id
ON public.retrieval_selected_chunks(raw_chunk_id);

UPDATE public.retrieval_selected_chunks rsc
SET
    raw_chunk_id = coalesce(rsc.raw_chunk_id, rsc.chunk_id),
    title_snapshot = coalesce(rsc.title_snapshot, d.title),
    source_snapshot = coalesce(rsc.source_snapshot, d.source_url),
    content_snapshot = coalesce(rsc.content_snapshot, c.content)
FROM public.chunks c
JOIN public.documents d ON d.doc_id = c.doc_id
WHERE rsc.chunk_id = c.chunk_id
  AND (
    rsc.raw_chunk_id IS NULL
    OR rsc.title_snapshot IS NULL
    OR rsc.source_snapshot IS NULL
    OR rsc.content_snapshot IS NULL
  );
