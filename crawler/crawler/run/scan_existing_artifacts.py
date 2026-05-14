from __future__ import annotations

import argparse
import json
from pathlib import Path

from crawler.paths import CHUNK_DIR, CURATED_DOC_DIR, RAW_DOC_DIR, RAW_HTML_DIR
from crawler.state.crawler_state_store import CrawlerStateStore


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def infer_artifact_state(raw_path: Path, curated_path: Path, chunk_path: Path) -> str:
    if chunk_path.exists():
        return "CHUNKED"
    if curated_path.exists():
        return "PARSED"
    if raw_path.exists():
        return "CRAWLED"
    return "DISCOVERED"


def artifact_paths_for(source_type: str, doc_id: str) -> dict[str, str]:
    paths = {
        "raw_json": RAW_DOC_DIR / source_type / f"{doc_id}.json",
        "raw_html": RAW_HTML_DIR / source_type / f"{doc_id}.html",
        "curated_json": CURATED_DOC_DIR / source_type / f"{doc_id}.json",
        "chunks_json": CHUNK_DIR / source_type / f"{doc_id}.json",
    }
    return {key: path.as_posix() for key, path in paths.items() if path.exists()}


def collect_raw_documents() -> list[Path]:
    if not RAW_DOC_DIR.exists():
        return []
    return sorted(path for path in RAW_DOC_DIR.rglob("*.json") if path.is_file())


def sync_existing_artifacts(limit: int | None = None, dry_run: bool = False) -> int:
    raw_paths = collect_raw_documents()
    if limit is not None:
        raw_paths = raw_paths[:limit]

    state_store = None if dry_run else CrawlerStateStore()
    if state_store:
        state_store.ensure_tables()

    synced_count = 0
    try:
        for raw_path in raw_paths:
            raw_doc = load_json(raw_path)
            source_type = raw_doc.get("source_type") or raw_path.parent.name
            doc_id = raw_doc["doc_id"]
            url = raw_doc.get("source_url")
            if not url:
                print(f"[SKIP] missing source_url path={raw_path.as_posix()}")
                continue

            curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"
            chunk_path = CHUNK_DIR / source_type / f"{doc_id}.json"
            status = infer_artifact_state(raw_path, curated_path, chunk_path)
            artifact_paths = artifact_paths_for(source_type, doc_id)
            artifact_paths["legacy_doc_id"] = doc_id

            if dry_run:
                print(f"[DRY RUN] doc_id={doc_id} status={status} url={url}")
            else:
                state_store.upsert_document_state(
                    doc_id=doc_id,
                    url=url,
                    final_url=raw_doc.get("metadata", {}).get("fetch", {}).get("final_url"),
                    status=status,
                    source_type=source_type,
                    page_kind=raw_doc.get("page_kind"),
                    checksum=raw_doc.get("content_hash"),
                    artifact_paths=artifact_paths,
                    extractor_name=raw_doc.get("metadata", {}).get("fetch", {}).get("extractor_name"),
                    extractor_version=raw_doc.get("metadata", {}).get("fetch", {}).get("extractor_version"),
                )
            synced_count += 1
    finally:
        if state_store:
            state_store.close()

    return synced_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync existing crawler artifacts into Postgres state tables.")
    parser.add_argument("--dry-run", action="store_true", help="Print inferred states without writing to Postgres.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum raw documents to inspect.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    synced_count = sync_existing_artifacts(limit=args.limit, dry_run=args.dry_run)
    print(f"[DONE] artifacts inspected={synced_count} dry_run={args.dry_run}")


if __name__ == "__main__":
    main()
