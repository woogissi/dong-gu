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
from crawler.state.crawler_state_store import CrawlerStateStore


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
    reason: str | None = None
    file_path: str | None = None
    queue_id: int | None = None

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
            reason=row.get("reason"),
            file_path=row.get("file_path"),
            queue_id=row.get("queue_id"),
        )


def fetch_retry_targets(stages: list[str], limit: int) -> list[RetryTarget]:
    loader = PGVectorLoader()
    try:
        with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(FAILURE_SQL, (stages, limit))
            return [RetryTarget.from_row(dict(row)) for row in cur.fetchall()]
    finally:
        loader.close()


def fetch_retry_targets_from_queue(stages: list[str], limit: int) -> tuple[list[RetryTarget], CrawlerStateStore]:
    state_store = CrawlerStateStore()
    state_store.ensure_tables()
    rows = state_store.list_retry_targets(stages=stages, limit=limit)
    targets = [
        RetryTarget.from_row(
            {
                "id": row["id"],
                "queue_id": row["id"],
                "stage": row["stage"],
                "source_type": row.get("source_type"),
                "doc_id": row.get("doc_id"),
                "url": row.get("url"),
                "error_type": row.get("reason"),
                "error_message": None,
                "reason": row.get("reason"),
                "file_path": row.get("file_path"),
            }
        )
        for row in rows
    ]
    return targets, state_store


def chunk_file_for(target: RetryTarget) -> Path | None:
    if not target.source_type or not target.doc_id:
        return None
    return CHUNK_DIR / target.source_type / f"{target.doc_id}.json"


def describe_target(target: RetryTarget) -> str:
    return (
        f"id={target.id} stage={target.stage} source_type={target.source_type} "
        f"doc_id={target.doc_id} url={target.url} reason={target.reason} error={target.error_type}"
    )


def retry_vector_targets(
    targets: list[RetryTarget],
    execute: bool,
    state_store: CrawlerStateStore | None = None,
) -> None:
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
            try:
                vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
                loader.commit()
                if state_store and target.queue_id:
                    state_store.mark_retry_done(target.queue_id)
                print(f"[VECTOR RETRY OK] {describe_target(target)}")
            except Exception as exc:
                loader.rollback()
                if state_store and target.queue_id:
                    state_store.mark_retry_failed(target.queue_id, exc)
                print(f"[VECTOR RETRY ERROR] {describe_target(target)} error={exc}")
    finally:
        loader.close()


def retry_static_targets(
    targets: list[RetryTarget],
    execute: bool,
    allow_insecure_ssl: bool,
    state_store: CrawlerStateStore | None = None,
) -> None:
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
        if state_store and target.queue_id:
            state_store.mark_retry_done(target.queue_id)
        print(f"[STATIC RETRY OK] {describe_target(target)}")


def print_unsupported_targets(targets: list[RetryTarget]) -> None:
    supported = {"vector_ingestion", "static_page"}
    for target in targets:
        if target.stage not in supported:
            print(f"[UNSUPPORTED RETRY STAGE] {describe_target(target)} file_path={target.file_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry selected crawler failures from crawl_logs.")
    parser.add_argument("--execute", action="store_true", help="Run retries. Default is dry-run.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum distinct failures to inspect.")
    parser.add_argument(
        "--stage",
        action="append",
        choices=[
            "vector_ingestion",
            "static_page",
            "crawl",
            "parse",
            "chunking",
            "file_parse",
            "attachment_download",
            "board_detail",
            "board_list",
            "discovery",
        ],
        help="Retry stage to include. Can be passed multiple times.",
    )
    parser.add_argument(
        "--from-retry-queue",
        action="store_true",
        help="Read pending targets from crawler_retry_queue instead of crawl_logs.",
    )
    parser.add_argument(
        "--allow-insecure-ssl",
        action="store_true",
        help="Allow configured legacy DEU hosts to retry without SSL verification.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    default_queue_stages = [
        "vector_ingestion",
        "static_page",
        "crawl",
        "parse",
        "chunking",
        "file_parse",
        "attachment_download",
        "board_detail",
        "board_list",
        "discovery",
    ]
    stages = args.stage or (default_queue_stages if args.from_retry_queue else ["vector_ingestion", "static_page"])
    state_store = None
    try:
        if args.from_retry_queue:
            targets, state_store = fetch_retry_targets_from_queue(stages=stages, limit=args.limit)
        else:
            targets = fetch_retry_targets(stages=stages, limit=args.limit)
        if not targets:
            print("[INFO] no retry targets found")
            return

        print(f"[INFO] retry targets found: {len(targets)} execute={args.execute}")
        retry_vector_targets(targets, execute=args.execute, state_store=state_store)
        retry_static_targets(
            targets,
            execute=args.execute,
            allow_insecure_ssl=args.allow_insecure_ssl,
            state_store=state_store,
        )
        print_unsupported_targets(targets)
    finally:
        if state_store:
            state_store.close()


if __name__ == "__main__":
    main()
