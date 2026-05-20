-- sub03_01 attachment regression checks.
-- Expected after recrawl + ingestion + vector ingestion:
-- 1) no duplicate attachment rows for the same doc/content hash
-- 2) no duplicate attachment asset rows for the same doc/file_url
-- 3) attachment document_contents are linked to chunks

SELECT dc.doc_id, d.source_url, md5(dc.content) AS content_md5, count(*) AS duplicate_rows
FROM document_contents dc
JOIN documents d ON d.doc_id = dc.doc_id
WHERE d.source_url LIKE '%sub03_01%'
  AND dc.content_type::text = 'attachment'
GROUP BY dc.doc_id, d.source_url, md5(dc.content)
HAVING count(*) > 1
ORDER BY duplicate_rows DESC, d.source_url;

SELECT da.doc_id, d.source_url, da.file_url, count(*) AS duplicate_rows
FROM document_assets da
JOIN documents d ON d.doc_id = da.doc_id
WHERE d.source_url LIKE '%sub03_01%'
  AND da.asset_type::text = 'attachment'
GROUP BY da.doc_id, d.source_url, da.file_url
HAVING count(*) > 1
ORDER BY duplicate_rows DESC, d.source_url;

SELECT dc.doc_id, d.source_url, dc.id AS content_id, count(c.id) AS linked_chunks
FROM document_contents dc
JOIN documents d ON d.doc_id = dc.doc_id
LEFT JOIN chunks c ON c.content_id = dc.id
WHERE d.source_url LIKE '%sub03_01%'
  AND dc.content_type::text = 'attachment'
GROUP BY dc.doc_id, d.source_url, dc.id
HAVING count(c.id) = 0
ORDER BY d.source_url, dc.id;

SELECT da.doc_id, d.source_url, da.file_name, da.file_url,
       da.metadata->>'file_hash_sha256' AS file_hash_sha256,
       jsonb_array_length(coalesce(da.metadata->'tables', '[]'::jsonb)) AS table_count
FROM document_assets da
JOIN documents d ON d.doc_id = da.doc_id
WHERE d.source_url LIKE '%sub03_01%'
  AND da.asset_type::text = 'attachment'
ORDER BY d.source_url, da.asset_index;
