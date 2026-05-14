from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.paths import CHUNK_DIR, HF_CACHE_DIR
from crawler.run.run_full_pipeline import process_static_seed
from crawler.run.run_single_file_pipeline import vector_ingest_chunk_file


os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR.resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str((HF_CACHE_DIR / "hub").resolve()))


FAILURE_SQL = """
SELECT DISTINCT ON (coalesce(doc_id, url), stage)
  id,
  created_at,
  stage,
  source_type,
  doc_id,
  url,
  error_type,
  left(error_message, 240) AS error_message
FROM crawl_logs
WHERE error_type IS NOT NULL
  AND stage = ANY(%s)
ORDER BY coalesce(doc_id, url), stage, created_at DESC
LIMIT %s;
"""


@dataclass
class RetryTarget:
    id: int
    stage: str
    source_type: str | None
    doc_id: str | None
    url: str | None
    error_type: str | None
    error_message: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "RetryTarget":
        return cls(
            id=row["id"],
            stage=row["stage"],
            source_type=row.get("source_type"),
            doc_id=row.get("doc_id"),
            url=row.get("url"),
            error_type=row.get("error_type"),
            error_message=row.get("error_message"),
        )


def fetch_retry_targets(stages: list[str], limit: int) -> list[RetryTarget]:
    loader = PGVectorLoader()
    try:
        with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(FAILURE_SQL, (stages, limit))
            return [RetryTarget.from_row(dict(row)) for row in cur.fetchall()]
    finally:
        loader.close()


def chunk_file_for(target: RetryTarget) -> Path | None:
    if not target.source_type or not target.doc_id:
        return None
    return CHUNK_DIR / target.source_type / f"{target.doc_id}.json"


def describe_target(target: RetryTarget) -> str:
    return (
        f"id={target.id} stage={target.stage} source_type={target.source_type} "
        f"doc_id={target.doc_id} url={target.url} error={target.error_type}"
    )


def retry_vector_targets(targets: list[RetryTarget], execute: bool) -> None:
    vector_targets = [target for target in targets if target.stage == "vector_ingestion"]
    if not vector_targets:
        return

    if not execute:
        for target in vector_targets:
            chunk_file = chunk_file_for(target)
            status = "ready" if chunk_file and chunk_file.exists() else "missing_chunk_file"
            print(f"[DRY RUN VECTOR] {describe_target(target)} chunk_file={chunk_file} status={status}")
        return

    from crawler.ingestion.embed_worker import EmbeddingWorker

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader(autocommit_writes=False)
    loader.ensure_tables()
    try:
        for target in vector_targets:
            chunk_file = chunk_file_for(target)
            if not chunk_file or not chunk_file.exists():
                print(f"[VECTOR SKIP] {describe_target(target)} chunk_file_missing={chunk_file}")
                continue
            vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
            loader.commit()
            print(f"[VECTOR RETRY OK] {describe_target(target)}")
    finally:
        loader.close()


def retry_static_targets(targets: list[RetryTarget], execute: bool, allow_insecure_ssl: bool) -> None:
    static_targets = [target for target in targets if target.stage == "static_page" and target.url]
    if not static_targets:
        return

    if allow_insecure_ssl:
        os.environ["CRAWLER_ALLOW_INSECURE_SSL"] = "1"

    for target in static_targets:
        if not execute:
            print(f"[DRY RUN STATIC] {describe_target(target)} allow_insecure_ssl={allow_insecure_ssl}")
            continue
        process_static_seed(
            {
                "name": f"retry_log_{target.id}",
                "source_type": target.source_type or "webpage",
                "page_kind": "static_page",
                "url": target.url,
            }
        )
        print(f"[STATIC RETRY OK] {describe_target(target)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry selected crawler failures from crawl_logs.")
    parser.add_argument("--execute", action="store_true", help="Run retries. Default is dry-run.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum distinct failures to inspect.")
    parser.add_argument(
        "--stage",
        action="append",
        choices=["vector_ingestion", "static_page"],
        help="Retry stage to include. Can be passed multiple times.",
    )
    parser.add_argument(
        "--allow-insecure-ssl",
        action="store_true",
        help="Allow configured legacy DEU hosts to retry without SSL verification.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stages = args.stage or ["vector_ingestion", "static_page"]
    targets = fetch_retry_targets(stages=stages, limit=args.limit)
    if not targets:
        print("[INFO] no retry targets found")
        return

    print(f"[INFO] retry targets found: {len(targets)} execute={args.execute}")
    retry_vector_targets(targets, execute=args.execute)
    retry_static_targets(
        targets,
        execute=args.execute,
        allow_insecure_ssl=args.allow_insecure_ssl,
    )


if __name__ == "__main__":
    main()
