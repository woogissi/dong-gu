-- Report duplicate chunk hashes by source_type.
-- Use this before/after crawler noise-filter changes to track duplicate reduction.

WITH chunk_sources AS (
    SELECT
        d.source_type,
        c.content_hash,
        c.chunk_id,
        c.doc_id,
        c.section_type::text AS section_type,
        c.section_title,
        left(regexp_replace(c.content, '\s+', ' ', 'g'), 240) AS sample
    FROM public.chunks c
    JOIN public.documents d ON d.doc_id = c.doc_id
    WHERE c.content_hash IS NOT NULL
),
duplicate_groups AS (
    SELECT
        source_type,
        content_hash,
        count(*) AS chunk_count,
        count(DISTINCT doc_id) AS document_count
    FROM chunk_sources
    GROUP BY source_type, content_hash
    HAVING count(*) > 1
)
SELECT
    g.source_type,
    g.content_hash,
    g.chunk_count,
    g.document_count,
    jsonb_agg(
        jsonb_build_object(
            'chunk_id', s.chunk_id,
            'doc_id', s.doc_id,
            'section_type', s.section_type,
            'section_title', s.section_title,
            'sample', s.sample
        )
        ORDER BY s.doc_id, s.chunk_id
    ) FILTER (WHERE s.chunk_id IS NOT NULL) AS samples
FROM duplicate_groups g
JOIN chunk_sources s
  ON s.source_type = g.source_type
 AND s.content_hash = g.content_hash
GROUP BY g.source_type, g.content_hash, g.chunk_count, g.document_count
ORDER BY g.chunk_count DESC, g.document_count DESC, g.source_type, g.content_hash
LIMIT 200;
