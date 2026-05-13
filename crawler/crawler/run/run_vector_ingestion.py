# crawler/run/run_vector_ingestion.py

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path("crawler/.hf_cache").resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path("crawler/.hf_cache/hub").resolve()))

from crawler.ingestion.embed_worker import EmbeddingWorker
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.storage.manifest_writer import ManifestWriter


RAW_DIR = Path("crawler/data/raw/documents")
CURATED_DIR = Path("crawler/data/curated/documents")
CHUNK_DIR = Path("crawler/data/rag_ready/chunks")
LOG_DIR = Path("crawler/data/logs")

LOG_DIR.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()


def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


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
    if change_type in ("new", "updated"):
        loader.insert_document_version(curated_doc, change_type)

    asset_source_doc = {
        **curated_doc,
        "downloaded_attachments": raw_doc.get("downloaded_attachments", []),
        "image_texts": raw_doc.get("image_texts", []),
    }
    loader.upsert_assets(asset_source_doc)
    loader.upsert_chunks(item["chunks"], item["version"])


def main() -> None:
    args = parse_args()
    chunk_files = collect_chunk_files()
    print(f"[INFO] chunk files found: {len(chunk_files)}")

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader(autocommit_writes=False)
    loader.ensure_tables()

    items = []
    all_chunks = []

    try:
        for chunk_file in chunk_files:
            item = {}
            try:
                item = load_ingestion_item(chunk_file)
                if not item["chunks"]:
                    continue

                upsert_document_side(loader, item)
                loader.commit()
                item["start_index"] = len(all_chunks)
                all_chunks.extend(item["chunks"])
                item["end_index"] = len(all_chunks)
                items.append(item)

                manifest_writer.append_jsonl(
                    "vector_ingestion.jsonl",
                    {
                        "chunk_file": chunk_file.as_posix(),
                        "source_type": item["source_type"],
                        "doc_id": item["doc_id"],
                        "chunk_count": len(item["chunks"]),
                        "embedding_model": embed_worker.model_name,
                        "status": "chunks_upserted",
                    },
                )
                print(f"[VECTOR QUEUED] doc_id={item['doc_id']} chunks={len(item['chunks'])}")

            except Exception as error:
                loader.conn.rollback()
                message = f"[VECTOR ERROR] file={chunk_file.as_posix()} error={error}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="vector_ingestion",
                    message=message,
                    extra={"file_path": chunk_file.as_posix()},
                )
                loader.insert_crawl_job_error(
                    run_type="vector_ingestion",
                    stage="vector_ingestion",
                    error=error,
                    source_type=item.get("source_type") if "item" in locals() else None,
                    doc_id=item.get("doc_id") if "item" in locals() else None,
                    file_path=chunk_file.as_posix(),
                    context={"chunk_file": chunk_file.as_posix()},
                )
                loader.commit()

        if not all_chunks:
            print("[INFO] no chunks to embed")
            return

        print(f"[EMBED] chunks={len(all_chunks)} batch_size={args.batch_size}")
        embedded_chunks = embed_worker.embed_chunks(all_chunks, batch_size=args.batch_size)
        loader.upsert_embeddings(embedded_chunks)
        loader.commit()

        for item in items:
            manifest_writer.append_jsonl(
                "vector_ingestion.jsonl",
                {
                    "chunk_file": item["chunk_file"].as_posix(),
                    "source_type": item["source_type"],
                    "doc_id": item["doc_id"],
                    "chunk_count": len(item["chunks"]),
                    "embedding_model": embed_worker.model_name,
                    "status": "embeddings_upserted",
                },
            )
            print(f"[VECTOR OK] doc_id={item['doc_id']} chunks={len(item['chunks'])}")

    finally:
        loader.close()


if __name__ == "__main__":
    main()
