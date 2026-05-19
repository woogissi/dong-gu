-- RAG log schema and join-path inspection.

SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.udt_name,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
WHERE c.table_schema = 'public'
  AND c.table_name IN (
      'query_logs',
      'response_logs',
      'retrieval_logs',
      'retrieval_selected_chunks',
      'documents',
      'chunks',
      'chunk_embeddings',
      'document_contents',
      'document_assets',
      'crawl_logs'
  )
ORDER BY c.table_name, c.ordinal_position;

SELECT
    tc.table_name,
    tc.constraint_type,
    tc.constraint_name,
    string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns,
    ccu.table_name AS foreign_table,
    string_agg(ccu.column_name, ', ' ORDER BY kcu.ordinal_position) AS foreign_columns
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
 AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name IN (
      'query_logs',
      'response_logs',
      'retrieval_logs',
      'retrieval_selected_chunks',
      'documents',
      'chunks'
  )
  AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
GROUP BY tc.table_name, tc.constraint_type, tc.constraint_name, ccu.table_name
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name;
