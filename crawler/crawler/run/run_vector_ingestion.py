# crawler/run/run_vector_ingestion.py

import argparse
import json
import os
import traceback
from pathlib import Path

from crawler.paths import CHUNK_DIR, CURATED_DOC_DIR, HF_CACHE_DIR, LOG_DIR, RAW_DOC_DIR

os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR.resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str((HF_CACHE_DIR / "hub").resolve()))

from crawler.ingestion.embed_worker import EmbeddingWorker
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.storage.manifest_writer import ManifestWriter
from crawler.utils.text_quality import document_quality_report, strip_nul_value, text_quality_report


RAW_DIR = RAW_DOC_DIR
CURATED_DIR = CURATED_DOC_DIR

LOG_DIR.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()


def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as file:
        return strip_nul_value(json.load(file))


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "vector_ingestion_errors.log", "a", encoding="utf-8") as file:
        file.write(message + "\n")


def collect_chunk_files() -> list[Path]:
    paths = []
    if not CHUNK_DIR.exists():
        return paths

    for source_type_dir in CHUNK_DIR.iterdir():
        if not source_type_dir.is_dir():
            continue
        paths.extend(source_type_dir.glob("*.json"))

    return sorted(paths)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load chunks into pgvector.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Embedding batch size passed to sentence-transformers.",
    )
    return parser.parse_args()


def write_vector_manifest(item: dict, status: str, embed_worker: EmbeddingWorker) -> None:
    manifest_writer.append_jsonl(
        "vector_ingestion.jsonl",
        {
            "chunk_file": item["chunk_file"].as_posix(),
            "source_type": item["source_type"],
            "doc_id": item["doc_id"],
            "chunk_count": len(item["chunks"]),
            "embedding_model": embed_worker.model_name,
            "status": status,
        },
    )


def load_ingestion_item(chunk_file: Path) -> dict:
    chunks = load_json(chunk_file)
    if not isinstance(chunks, list):
        raise ValueError(f"chunk file must contain a JSON list: {chunk_file}")
    if not chunks:
        return {"chunk_file": chunk_file, "chunks": []}

    source_type = chunks[0]["source_type"]
    doc_id = chunks[0]["doc_id"]
    curated_path = CURATED_DIR / source_type / f"{doc_id}.json"
    raw_path = RAW_DIR / source_type / f"{doc_id}.json"

    if not curated_path.exists():
        raise FileNotFoundError(f"curated document not found: {curated_path}")

    curated_doc = load_json(curated_path)
    raw_doc = load_json(raw_path) if raw_path.exists() else {}

    return {
        "chunk_file": chunk_file,
        "chunks": chunks,
        "source_type": source_type,
        "doc_id": doc_id,
        "curated_doc": curated_doc,
        "raw_doc": raw_doc,
        "version": curated_doc.get("version", 1),
    }


def upsert_document_side(loader: PGVectorLoader, item: dict) -> None:
    curated_doc = item["curated_doc"]
    raw_doc = item["raw_doc"]

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
    loader.upsert_chunks(item["chunks"], item["version"])


def ingestion_item_quality_report(item: dict) -> dict[str, object]:
    doc_quality = document_quality_report(item["curated_doc"])
    bad_chunks = []
    for chunk in item["chunks"]:
        report = text_quality_report(chunk.get("content"))
        if report["is_binary_like"]:
            bad_chunks.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "chunk_index": chunk.get("chunk_index"),
                    "quality": report,
                }
            )
    return {
        "is_binary_like": bool(doc_quality["is_binary_like"] or bad_chunks),
        "document": doc_quality,
        "bad_chunks": bad_chunks[:20],
        "bad_chunk_count": len(bad_chunks),
    }


def main() -> None:
    args = parse_args()
    chunk_files = collect_chunk_files()
    print(f"[INFO] chunk files found: {len(chunk_files)}", flush=True)

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader(autocommit_writes=False)
    loader.ensure_tables()

    processed_count = 0
    failed_count = 0
    embedded_chunk_count = 0

    try:
        for file_index, chunk_file in enumerate(chunk_files, start=1):
            item = {}
            try:
                item = load_ingestion_item(chunk_file)
                if not item["chunks"]:
                    continue

                quality = ingestion_item_quality_report(item)
                if quality["is_binary_like"]:
                    failed_count += 1
                    manifest_writer.append_jsonl(
                        "vector_ingestion.jsonl",
                        {
                            "chunk_file": chunk_file.as_posix(),
                            "source_type": item["source_type"],
                            "doc_id": item["doc_id"],
                            "chunk_count": len(item["chunks"]),
                            "status": "skipped",
                            "reason": "binary_like_text",
                            "quality": quality,
                        },
                    )
                    print(
                        "[VECTOR SKIP] "
                        f"doc_id={item['doc_id']} reason=binary_like_text "
                        f"bad_chunks={quality['bad_chunk_count']}",
                        flush=True,
                    )
                    continue

                print(
                    "[VECTOR START] "
                    f"file={file_index}/{len(chunk_files)} "
                    f"doc_id={item['doc_id']} chunks={len(item['chunks'])}",
                    flush=True,
                )
                upsert_document_side(loader, item)
                loader.commit()
                write_vector_manifest(item, "chunks_upserted", embed_worker)
                print(f"[CHUNKS OK] doc_id={item['doc_id']} chunks={len(item['chunks'])}", flush=True)

                for start in range(0, len(item["chunks"]), args.batch_size):
                    end = min(start + args.batch_size, len(item["chunks"]))
                    batch = item["chunks"][start:end]
                    print(
                        "[EMBED BATCH] "
                        f"doc_id={item['doc_id']} "
                        f"chunks={start + 1}-{end}/{len(item['chunks'])} "
                        f"batch_size={args.batch_size}",
                        flush=True,
                    )
                    embedded_chunks = embed_worker.embed_chunks(batch, batch_size=args.batch_size)
                    loader.upsert_embeddings(embedded_chunks)
                    loader.commit()
                    embedded_chunk_count += len(embedded_chunks)

                write_vector_manifest(item, "embeddings_upserted", embed_worker)
                processed_count += 1
                print(
                    "[VECTOR OK] "
                    f"doc_id={item['doc_id']} chunks={len(item['chunks'])} "
                    f"processed_docs={processed_count} embedded_chunks={embedded_chunk_count}",
                    flush=True,
                )

            except Exception as error:
                failed_count += 1
                loader.rollback()
                stack_trace = traceback.format_exc()
                message = f"[VECTOR ERROR] file={chunk_file.as_posix()} error={error}"
                log_error(message)
                log_error(stack_trace.rstrip())
                manifest_writer.write_error_record(
                    stage="vector_ingestion",
                    message=message,
                    extra={"file_path": chunk_file.as_posix()},
                )
                try:
                    loader.insert_crawl_job_error(
                        run_type="vector_ingestion",
                        stage="vector_ingestion",
                        error=error,
                        source_type=item.get("source_type"),
                        doc_id=item.get("doc_id"),
                        file_path=chunk_file.as_posix(),
                        context={"chunk_file": chunk_file.as_posix()},
                    )
                    loader.commit()
                except Exception as logging_error:
                    loader.rollback()
                    log_error(
                        "[VECTOR ERROR LOGGING FAILED] "
                        f"file={chunk_file.as_posix()} error={logging_error}"
                    )

        print(
            "[SUMMARY] "
            f"processed_docs={processed_count} failed_docs={failed_count} "
            f"embedded_chunks={embedded_chunk_count}",
            flush=True,
        )

    except KeyboardInterrupt:
        loader.rollback()
        print(
            "[INTERRUPTED] vector ingestion stopped; rolled back open transaction",
            flush=True,
        )
        raise
    finally:
        loader.close()


if __name__ == "__main__":
    main()
