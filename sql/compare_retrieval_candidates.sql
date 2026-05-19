-- Manual DB evidence probe for one query.
-- Replace the terms array with strong terms from user_query/rewrite/keywords.

WITH params AS (
    SELECT ARRAY[
        '%셔틀버스%',
        '%통학버스%',
        '%버스%'
    ]::text[] AS patterns
)
SELECT
    d.doc_id,
    c.chunk_id,
    d.title,
    d.source_type,
    d.department,
    d.published_at,
    d.source_url,
    length(c.content) AS chunk_len,
    (
        SELECT count(*)
        FROM params, unnest(params.patterns) AS p(pattern)
        WHERE c.content ILIKE p.pattern
           OR d.title ILIKE p.pattern
    ) AS term_hits,
    left(c.content, 500) AS content_preview
FROM chunks c
JOIN documents d ON d.doc_id = c.doc_id
WHERE EXISTS (
    SELECT 1
    FROM params, unnest(params.patterns) AS p(pattern)
    WHERE c.content ILIKE p.pattern
       OR d.title ILIKE p.pattern
)
ORDER BY term_hits DESC, d.published_at DESC NULLS LAST, length(c.content) DESC
LIMIT 50;
