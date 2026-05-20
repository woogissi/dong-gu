-- Recent likely-low-quality RAG responses.

WITH latest_retrieval AS (
    SELECT DISTINCT ON (request_id)
        *
    FROM retrieval_logs
    ORDER BY request_id, created_at DESC, id DESC
),
selected AS (
    SELECT
        retrieval_log_id,
        count(*) AS selected_rows,
        jsonb_agg(
            jsonb_build_object(
                'rank', rsc.rank,
                'chunk_id', rsc.chunk_id,
                'raw_chunk_id', rsc.raw_chunk_id,
                'doc_id', rsc.doc_id,
                'score', rsc.score,
                'rerank_score', rsc.rerank_score,
                'title', coalesce(d.title, rsc.title_snapshot),
                'source_type', d.source_type,
                'department', d.department,
                'content_preview', left(coalesce(c.content, rsc.content_snapshot), 260),
                'metadata', rsc.metadata
            )
            ORDER BY rsc.rank
        ) AS selected_chunks
    FROM retrieval_selected_chunks rsc
    LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
    LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id)
    GROUP BY retrieval_log_id
)
SELECT
    q.id AS query_id,
    q.request_id,
    q.question AS user_query,
    q.intent_type AS intent,
    rl.rewritten_query,
    rl.keywords,
    rl.category,
    rl.filters,
    rl.retrieval_strategy,
    rl.fallback_used,
    rl.retrieved_doc_count,
    rl.reranked_doc_count,
    rl.selected_doc_count,
    coalesce(s.selected_rows, 0) AS selected_rows,
    r.success AS response_success,
    left(r.answer_text, 500) AS final_answer,
    q.created_at,
    coalesce(s.selected_chunks, '[]'::jsonb) AS selected_chunks
FROM query_logs q
LEFT JOIN latest_retrieval rl ON rl.request_id = q.request_id
LEFT JOIN selected s ON s.retrieval_log_id = rl.id
LEFT JOIN response_logs r ON r.request_id = q.request_id
WHERE coalesce(rl.selected_doc_count, 0) = 0
   OR coalesce(rl.retrieved_doc_count, 0) = 0
   OR rl.fallback_used
   OR rl.success = false
   OR r.success = false
   OR r.answer_text ILIKE ANY(ARRAY[
        '%확인할 수 없%',
        '%찾을 수 없%',
        '%알 수 없%',
        '%제공된 정보%',
        '%관련 정보를 찾을 수%',
        '%죄송%'
   ])
ORDER BY q.created_at DESC
LIMIT 100;
