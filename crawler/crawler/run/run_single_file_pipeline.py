# crawler/run/run_single_file_pipeline.py

import argparse
import json
import os
from pathlib import Path

from crawler.paths import CHUNK_DIR, CURATED_DOC_DIR, HF_CACHE_DIR, LOG_DIR, RAW_DOC_DIR

os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR.resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str((HF_CACHE_DIR / "hub").resolve()))

from crawler.storage.manifest_writer import ManifestWriter
from crawler.state.crawler_state_store import CrawlerStateStore
from crawler.utils.text_quality import document_quality_report, strip_nul_value, text_quality_report


RAW_DIR = RAW_DOC_DIR
CURATED_DIR = CURATED_DOC_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()


def record_document_state_safe(doc: dict, status: str, artifact_paths: dict | None = None, error: Exception | None = None) -> None:
    url = doc.get("source_url") or doc.get("url")
    if not url:
        return
    try:
        state_store = CrawlerStateStore()
        try:
            state_store.ensure_tables()
            state_store.upsert_document_state(
                url=url,
                doc_id=doc.get("doc_id"),
                status=status,
                source_type=doc.get("source_type"),
                page_kind=doc.get("page_kind"),
                checksum=doc.get("content_hash"),
                artifact_paths=artifact_paths or {},
                error=str(error) if error else None,
                error_stage=None if error is None else status.lower(),
            )
        finally:
            state_store.close()
    except Exception as exc:
        log_error(f"[STATE WRITE ERROR] doc_id={doc.get('doc_id')} status={status} error={exc}")


def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return strip_nul_value(json.load(f))


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_error(message: str, log_name: str = "single_file_pipeline_errors.log") -> None:
    print(message)
    with open(LOG_DIR / log_name, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.exists():
        return path

    project_relative = Path.cwd() / path
    if project_relative.exists():
        return project_relative

    raise FileNotFoundError(f"file not found: {path_value}")


def chunk_curated_file(curated_file: Path, chunker=None) -> Path | None:
    doc = load_json(curated_file)
    if not isinstance(doc, dict):
        raise ValueError(f"curated file must contain a JSON object: {curated_file}")

    source_type = doc.get("source_type", "unknown")
    doc_id = doc["doc_id"]

    body = doc.get("normalize", "")
    attachment = doc.get("attachment_text", "")
    image = doc.get("image_text", "")

    has_text = any(value and str(value).strip() for value in [body, attachment, image])
    if not has_text:
        manifest_writer.append_jsonl("chunking.jsonl", {
            "doc_id": doc_id,
            "source_type": source_type,
            "version": doc.get("version"),
            "chunk_count": 0,
            "source_url": doc.get("source_url"),
            "status": "skipped",
            "reason": "no body, attachment, or image text",
        })
        print(f"[INGEST SKIP] {doc_id} no body, attachment, or image text")
        return None

    quality = document_quality_report(doc)
    if quality["is_binary_like"]:
        manifest_writer.append_jsonl("chunking.jsonl", {
            "doc_id": doc_id,
            "source_type": source_type,
            "version": doc.get("version"),
            "chunk_count": 0,
            "source_url": doc.get("source_url"),
            "status": "skipped",
            "reason": "binary_like_text",
            "quality": quality,
            "mode": "single_file",
        })
        print(f"[INGEST SKIP] {doc_id} binary_like_text fields={quality['bad_fields']}")
        return None

    if chunker is None:
        from crawler.ingestion.chunker import DocumentChunker

        chunker = DocumentChunker(max_chars=900, overlap_chars=100)

    chunks = chunker.chunk_document(doc)
    chunk_path = CHUNK_DIR / source_type / f"{doc_id}.json"
    save_json(chunk_path, chunks)
    record_document_state_safe(
        doc,
        "CHUNKED",
        artifact_paths={
            "curated_json": curated_file.as_posix(),
            "chunks_json": chunk_path.as_posix(),
        },
    )

    manifest_writer.append_jsonl("chunking.jsonl", {
        "doc_id": doc_id,
        "source_type": source_type,
        "version": doc.get("version"),
        "chunk_count": len(chunks),
        "source_url": doc.get("source_url"),
        "mode": "single_file",
    })

    print(f"[INGEST OK] {doc_id} version={doc.get('version')} chunks={len(chunks)}")
    return chunk_path


def vector_ingest_chunk_file(chunk_file: Path, embed_worker=None, loader=None) -> None:
    chunks = load_json(chunk_file)
    if not isinstance(chunks, list):
        raise ValueError(f"chunk file must contain a JSON list: {chunk_file}")
    if not chunks:
        print(f"[VECTOR SKIP] empty chunk file: {chunk_file.as_posix()}")
        return

    bad_chunks = [
        chunk
        for chunk in chunks
        if text_quality_report(chunk.get("content"))["is_binary_like"]
    ]
    if bad_chunks:
        manifest_writer.append_jsonl("vector_ingestion.jsonl", {
            "chunk_file": chunk_file.as_posix(),
            "doc_id": chunks[0].get("doc_id"),
            "source_type": chunks[0].get("source_type"),
            "chunk_count": len(chunks),
            "status": "skipped",
            "reason": "binary_like_text",
            "bad_chunk_count": len(bad_chunks),
            "mode": "single_file",
        })
        print(f"[VECTOR SKIP] {chunk_file.as_posix()} binary_like_text bad_chunks={len(bad_chunks)}")
        return

    source_type = chunks[0]["source_type"]
    doc_id = chunks[0]["doc_id"]

    curated_path = CURATED_DIR / source_type / f"{doc_id}.json"
    raw_path = RAW_DIR / source_type / f"{doc_id}.json"

    if not curated_path.exists():
        raise FileNotFoundError(f"curated document not found: {curated_path}")

    curated_doc = load_json(curated_path)
    raw_doc = load_json(raw_path) if raw_path.exists() else {}
    version = curated_doc.get("version", 1)

    owns_loader = loader is None
    if embed_worker is None:
        from crawler.ingestion.embed_worker import EmbeddingWorker

        embed_worker = EmbeddingWorker()
    if loader is None:
        from crawler.ingestion.pgvector_loader import PGVectorLoader

        loader = PGVectorLoader()
        loader.ensure_tables()

    try:
        loader.upsert_document(curated_doc)

        change_type = curated_doc.get("change_type") or curated_doc.get("decision", "unknown")
        document_version_id = loader.insert_document_version(curated_doc, change_type)

        loader.upsert_document_contents(curated_doc, document_version_id)

        asset_source_doc = {
            **curated_doc,
            "downloaded_attachments": raw_doc.get("downloaded_attachments", []),
            "image_texts": raw_doc.get("image_texts", []),
        }

        loader.upsert_assets(asset_source_doc, document_version_id)
        loader.upsert_chunks(chunks, version)

        embedded_chunks = embed_worker.embed_chunks(chunks)
        loader.upsert_embeddings(embedded_chunks)
        record_document_state_safe(
            curated_doc,
            "EMBEDDED",
            artifact_paths={
                "curated_json": curated_path.as_posix(),
                "chunks_json": chunk_file.as_posix(),
                "raw_json": raw_path.as_posix() if raw_path.exists() else None,
            },
        )

        manifest_writer.append_jsonl("vector_ingestion.jsonl", {
            "chunk_file": chunk_file.as_posix(),
            "source_type": source_type,
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "embedding_model": embedded_chunks[0].get("embedding_model") if embedded_chunks else None,
            "mode": "single_file",
        })

        print(f"[VECTOR OK] doc_id={doc_id} chunks={len(chunks)}")

    except Exception:
        loader.conn.rollback()
        try:
            record_document_state_safe(curated_doc if "curated_doc" in locals() else {"doc_id": doc_id, "source_type": source_type}, "FAILED", error=Exception("vector_ingestion_failed"))
        except Exception:
            pass
        raise
    finally:
        if owns_loader:
            loader.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run chunking and/or vector ingestion for one selected JSON file."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--curated-file",
        nargs="+",
        help="Path to one curated document JSON. Creates crawler/data/rag_ready/chunks/<source_type>/<doc_id>.json.",
    )
    group.add_argument(
        "--chunk-file",
        nargs="+",
        help="Path to one chunk JSON. Runs only vector ingestion for that chunk file.",
    )
    parser.add_argument(
        "--skip-vector",
        action="store_true",
        help="Only create chunks when --curated-file is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        if args.curated_file:
            from crawler.ingestion.chunker import DocumentChunker

            chunker = DocumentChunker(max_chars=900, overlap_chars=100)
            chunk_files = []
            for curated_file_arg in args.curated_file:
                curated_file = resolve_path(curated_file_arg)
                chunk_file = chunk_curated_file(curated_file, chunker=chunker)
                if chunk_file:
                    chunk_files.append(chunk_file)

            if chunk_files and not args.skip_vector:
                from crawler.ingestion.embed_worker import EmbeddingWorker
                from crawler.ingestion.pgvector_loader import PGVectorLoader

                embed_worker = EmbeddingWorker()
                loader = PGVectorLoader(autocommit_writes=False)
                loader.ensure_tables()
                try:
                    for chunk_file in chunk_files:
                        vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
                        loader.commit()
                finally:
                    loader.close()
            return

        from crawler.ingestion.embed_worker import EmbeddingWorker
        from crawler.ingestion.pgvector_loader import PGVectorLoader

        embed_worker = EmbeddingWorker()
        loader = PGVectorLoader(autocommit_writes=False)
        loader.ensure_tables()
        try:
            for chunk_file_arg in args.chunk_file:
                chunk_file = resolve_path(chunk_file_arg)
                vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
                loader.commit()
        finally:
            loader.close()

    except Exception as e:
        message = f"[SINGLE FILE PIPELINE ERROR] error={e}"
        log_error(message)
        manifest_writer.write_error_record(
            stage="single_file_pipeline",
            message=message,
            extra={
                "curated_file": args.curated_file,
                "chunk_file": args.chunk_file,
                "skip_vector": args.skip_vector,
            },
        )
        raise


if __name__ == "__main__":
    main()
