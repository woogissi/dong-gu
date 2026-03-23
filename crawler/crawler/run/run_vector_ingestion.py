# crawler/run/run_vector_ingestion.py

import json
from pathlib import Path

from crawler.ingestion.embed_worker import EmbeddingWorker
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.storage.manifest_writer import ManifestWriter


CHUNK_DIR = Path("crawler/data/rag_ready/chunks")
LOG_DIR = Path("crawler/data/logs")

LOG_DIR.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "vector_ingestion_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def collect_chunk_files() -> list[Path]:
    paths = []
    if not CHUNK_DIR.exists():
        return paths

    for source_type_dir in CHUNK_DIR.iterdir():
        if not source_type_dir.is_dir():
            continue

        for file_path in source_type_dir.glob("*.json"):
            paths.append(file_path)

    return sorted(paths)


def main():
    chunk_files = collect_chunk_files()
    print(f"[INFO] chunk files found: {len(chunk_files)}")

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader()
    loader.ensure_tables()

    try:
        for chunk_file in chunk_files:
            try:
                chunks = load_json(chunk_file)
                if not chunks:
                    continue

                loader.upsert_chunks(chunks)
                embedded_chunks = embed_worker.embed_chunks(chunks)
                loader.upsert_embeddings(embedded_chunks)

                manifest_writer.append_jsonl("vector_ingestion.jsonl", {
                    "chunk_file": chunk_file.as_posix(),
                    "source_type": chunks[0].get("source_type"),
                    "doc_id": chunks[0].get("doc_id"),
                    "chunk_count": len(chunks),
                    "embedding_model": embedded_chunks[0].get("embedding_model"),
                })

                print(
                    f"[VECTOR OK] doc_id={chunks[0].get('doc_id')} "
                    f"chunks={len(chunks)}"
                )

            except Exception as e:
                message = f"[VECTOR ERROR] file={chunk_file.as_posix()} error={e}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="vector_ingestion",
                    message=message,
                    extra={"file_path": chunk_file.as_posix()},
                )

    finally:
        loader.close()


if __name__ == "__main__":
    main()