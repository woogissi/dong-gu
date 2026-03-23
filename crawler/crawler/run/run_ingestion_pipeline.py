# crawler/run/run_ingestion_pipeline.py

import json
from pathlib import Path

from crawler.ingestion.document_version_manager import DocumentVersionManager
from crawler.ingestion.chunker import DocumentChunker
from crawler.storage.manifest_writer import ManifestWriter


CURATED_DIR = Path("crawler/data/curated/documents")
CHUNK_DIR = Path("crawler/data/rag_ready/chunks")
LOG_DIR = Path("crawler/data/logs")

for d in [CHUNK_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()
version_manager = DocumentVersionManager(curated_base_dir=str(CURATED_DIR))
chunker = DocumentChunker(max_chars=1200, overlap_chars=150)


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "ingestion_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def collect_curated_documents() -> list[Path]:
    doc_paths = []
    if not CURATED_DIR.exists():
        return doc_paths

    for source_type_dir in CURATED_DIR.iterdir():
        if not source_type_dir.is_dir():
            continue

        for file_path in source_type_dir.glob("*.json"):
            doc_paths.append(file_path)

    return sorted(doc_paths)


def save_chunks(source_type: str, doc_id: str, chunks: list[dict]) -> None:
    chunk_path = CHUNK_DIR / source_type / f"{doc_id}.json"
    save_json(chunk_path, chunks)


def run_ingestion():
    doc_paths = collect_curated_documents()
    print(f"[INFO] curated documents found: {len(doc_paths)}")

    for path in doc_paths:
        try:
            doc = load_json(path)
            source_type = doc.get("source_type", "unknown")
            doc_id = doc["doc_id"]

            version_result = version_manager.apply_version(source_type, dict(doc))
            versioned_doc = version_result["document"]
            decision = version_result["decision"]

            chunks = chunker.chunk_document(versioned_doc)
            save_chunks(source_type, doc_id, chunks)

            manifest_writer.append_jsonl("chunking.jsonl", {
                "doc_id": doc_id,
                "source_type": source_type,
                "decision": decision,
                "version": versioned_doc["version"],
                "chunk_count": len(chunks),
                "source_url": versioned_doc.get("source_url"),
            })

            print(f"[INGEST OK] {doc_id} decision={decision} chunks={len(chunks)}")

        except Exception as e:
            message = f"[INGEST ERROR] file={path.as_posix()} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="ingestion",
                message=message,
                extra={"file_path": path.as_posix()},
            )


if __name__ == "__main__":
    run_ingestion()