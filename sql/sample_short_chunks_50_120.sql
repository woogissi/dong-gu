-- Sample 50-120 character chunks for manual quality review.
-- Helps separate useful short facts from navigation/board shell noise.

SELECT
    d.source_type,
    c.doc_id,
    c.chunk_id,
    c.section_type::text AS section_type,
    c.section_title,
    length(c.content) AS content_length,
    c.content_hash,
    d.source_url,
    regexp_replace(c.content, '\s+', ' ', 'g') AS content_sample
FROM public.chunks c
JOIN public.documents d ON d.doc_id = c.doc_id
WHERE length(c.content) BETWEEN 50 AND 120
ORDER BY d.source_type, c.content_length ASC, c.updated_at DESC
LIMIT 200;
