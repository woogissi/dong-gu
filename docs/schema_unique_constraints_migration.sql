BEGIN;

ALTER TABLE public.document_assets
DROP CONSTRAINT IF EXISTS document_assets_doc_id_asset_index_key;

ALTER TABLE public.document_assets
ADD CONSTRAINT document_assets_doc_assettype_assetindex_key
UNIQUE (doc_id, asset_type, asset_index);

ALTER TABLE public.chunks
DROP CONSTRAINT IF EXISTS chunks_doc_id_chunk_index_key;

ALTER TABLE public.chunks
ADD CONSTRAINT chunks_doc_version_chunk_index_key
UNIQUE (doc_id, document_version_id, chunk_index);

COMMIT;
