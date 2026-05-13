# crawler/run/run_selected_curated_ingestion.py

import argparse
import json
from pathlib import Path

from crawler.ingestion.chunker import DocumentChunker
from crawler.ingestion.embed_worker import EmbeddingWorker
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.storage.manifest_writer import ManifestWriter


RAW_DIR = Path("crawler/data/raw/documents")
CHUNK_DIR = Path("crawler/data/rag_ready/chunks")

manifest_writer = ManifestWriter()


def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_path(path_value: str) -> Path:
    path = Path(path_value)
    if path.exists():
        return path

    project_relative = Path.cwd() / path
    if project_relative.exists():
        return project_relative

    raise FileNotFoundError(f"file not found: {path_value}")


def chunk_curated_doc(doc: dict, chunker: DocumentChunker) -> tuple[Path | None, list[dict]]:
    source_type = doc.get("source_type", "unknown")
    doc_id = doc["doc_id"]

    body = doc.get("normalize", "")
    attachment = doc.get("attachment_text", "")
    image = doc.get("image_text", "")
    has_text = any(value and str(value).strip() for value in [body, attachment, image])
    if not has_text:
        manifest_writer.append_jsonl(
            "chunking.jsonl",
            {
                "doc_id": doc_id,
                "source_type": source_type,
                "version": doc.get("version"),
                "chunk_count": 0,
                "source_url": doc.get("source_url"),
                "status": "skipped",
                "reason": "no body, attachment, or image text",
                "mode": "selected_curated_ingestion",
            },
        )
        return None, []

    chunks = chunker.chunk_document(doc)
    chunk_path = CHUNK_DIR / source_type / f"{doc_id}.json"
    save_json(chunk_path, chunks)
    manifest_writer.append_jsonl(
        "chunking.jsonl",
        {
            "doc_id": doc_id,
            "source_type": source_type,
            "version": doc.get("version"),
            "chunk_count": len(chunks),
            "source_url": doc.get("source_url"),
            "mode": "selected_curated_ingestion",
        },
    )
    return chunk_path, chunks


def ingest_doc(doc: dict, chunks: list[dict], loader: PGVectorLoader, embed_worker: EmbeddingWorker) -> None:
    source_type = doc.get("source_type", "unknown")
    doc_id = doc["doc_id"]
    version = doc.get("version", 1)

    raw_path = RAW_DIR / source_type / f"{doc_id}.json"
    raw_doc = load_json(raw_path) if raw_path.exists() else {}

    loader.upsert_document(doc)
    change_type = doc.get("change_type") or doc.get("decision", "unknown")
    if change_type in ("new", "updated"):
        loader.insert_document_version(doc, change_type)

    asset_source_doc = {
        **doc,
        "downloaded_attachments": raw_doc.get("downloaded_attachments", []),
        "image_texts": raw_doc.get("image_texts", []),
    }
    loader.upsert_assets(asset_source_doc)
    loader.upsert_chunks(chunks, version)

    embedded_chunks = embed_worker.embed_chunks(chunks)
    loader.upsert_embeddings(embedded_chunks)

    manifest_writer.append_jsonl(
        "vector_ingestion.jsonl",
        {
            "source_type": source_type,
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "embedding_model": embedded_chunks[0].get("embedding_model") if embedded_chunks else None,
            "mode": "selected_curated_ingestion",
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk and vector-ingest selected curated documents.")
    parser.add_argument("curated_files", nargs="+", help="Curated JSON files to ingest.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    curated_files = [resolve_path(path_value) for path_value in args.curated_files]

    chunker = DocumentChunker(max_chars=900, overlap_chars=100)
    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader()
    loader.ensure_tables()

    try:
        for curated_file in curated_files:
            try:
                doc = load_json(curated_file)
                if not isinstance(doc, dict):
                    raise ValueError(f"curated file must contain an object: {curated_file}")

                chunk_path, chunks = chunk_curated_doc(doc, chunker)
                if not chunk_path or not chunks:
                    print(f"[SELECTED INGEST SKIP] {curated_file.as_posix()}")
                    continue

                ingest_doc(doc, chunks, loader, embed_worker)
                print(f"[SELECTED INGEST OK] doc_id={doc['doc_id']} chunks={len(chunks)}")

            except Exception as exc:
                loader.conn.rollback()
                print(f"[SELECTED INGEST ERROR] file={curated_file.as_posix()} error={exc}")
                raise
    finally:
        loader.close()


if __name__ == "__main__":
    main()
