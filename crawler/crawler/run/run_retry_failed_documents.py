from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.paths import CHUNK_DIR, CURATED_DOC_DIR, HF_CACHE_DIR
from crawler.run.run_full_pipeline import process_static_seed, run_board_pipeline
from crawler.run.run_single_file_pipeline import chunk_curated_file, vector_ingest_chunk_file
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
    task_type: str
    source_type: str | None
    doc_id: str | None
    url: str | None
    error_type: str | None
    error_message: str | None
    reason: str | None = None
    file_path: str | None = None
    queue_id: int | None = None
    payload: dict[str, Any] | None = None
    attempts: int = 0
    max_attempts: int = 3

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "RetryTarget":
        return cls(
            id=row["id"],
            stage=row["stage"],
            task_type=row.get("task_type") or row["stage"],
            source_type=row.get("source_type"),
            doc_id=row.get("doc_id"),
            url=row.get("url"),
            error_type=row.get("error_type"),
            error_message=row.get("error_message"),
            reason=row.get("reason"),
            file_path=row.get("file_path"),
            queue_id=row.get("queue_id"),
            payload=row.get("payload") or row.get("context") or {},
            attempts=int(row.get("attempts") or row.get("retry_count") or 0),
            max_attempts=int(row.get("max_attempts") or 3),
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
                "task_type": row.get("task_type") or row["stage"],
                "source_type": row.get("source_type"),
                "doc_id": row.get("doc_id"),
                "url": row.get("url"),
                "error_type": row.get("reason"),
                "error_message": None,
                "reason": row.get("reason"),
                "file_path": row.get("file_path"),
                "payload": row.get("payload") or row.get("context") or {},
                "attempts": row.get("attempts") or row.get("retry_count") or 0,
                "max_attempts": row.get("max_attempts") or 3,
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
        f"id={target.id} task_type={target.task_type} stage={target.stage} source_type={target.source_type} "
        f"doc_id={target.doc_id} url={target.url} attempts={target.attempts}/{target.max_attempts} "
        f"reason={target.reason} error={target.error_type}"
    )


def payload_value(target: RetryTarget, key: str, default: Any = None) -> Any:
    payload = target.payload or {}
    return payload.get(key, default)


def recover_chunk_file_from_db(target: RetryTarget) -> Path:
    if not target.doc_id or not target.source_type:
        raise ValueError("missing doc_id/source_type for DB chunk recovery")

    loader = PGVectorLoader(autocommit_writes=False)
    try:
        with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                  chunk_id,
                  doc_id,
                  chunk_index,
                  section_index,
                  section_type,
                  section_title,
                  content,
                  content_length,
                  content_hash,
                  chunking_strategy,
                  metadata
                FROM chunks
                WHERE doc_id = %s
                ORDER BY chunk_index ASC;
                """,
                (target.doc_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    finally:
        loader.close()

    if not rows:
        raise FileNotFoundError(f"missing_chunk_file_and_db_chunks doc_id={target.doc_id}")

    chunk_path = CHUNK_DIR / target.source_type / f"{target.doc_id}.json"
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    chunk_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return chunk_path


def handle_vector_ingestion(target: RetryTarget) -> None:
    from crawler.ingestion.embed_worker import EmbeddingWorker

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader(autocommit_writes=False)
    loader.ensure_tables()
    try:
        chunk_file = Path(target.file_path) if target.file_path else chunk_file_for(target)
        if not chunk_file or not chunk_file.exists():
            chunk_file = recover_chunk_file_from_db(target)
        vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
        loader.commit()
    except Exception:
        loader.rollback()
        raise
    finally:
        loader.close()


def handle_static_page(target: RetryTarget) -> None:
    if not target.url:
        raise ValueError("missing url for static_page retry")
    process_static_seed(
        {
            "name": f"retry_{target.id}",
            "source_type": target.source_type or "webpage",
            "page_kind": "static_page",
            "url": target.url,
            "download_attachments": True,
        },
        raise_on_error=True,
    )


def handle_attachment_download(target: RetryTarget) -> None:
    if not target.source_type or not target.doc_id:
        raise ValueError("missing source_type/doc_id for attachment_download retry")
    file_url = payload_value(target, "file_url") or target.url
    if not file_url:
        raise ValueError("missing file_url for attachment_download retry")
    attachment = {
        "file_url": file_url,
        "file_name": payload_value(target, "file_name") or Path(file_url).name or "attachment",
        "attachment_index": int(payload_value(target, "attachment_index", 0) or 0),
    }
    from crawler.extractors.attachment_downloader import AttachmentDownloader

    AttachmentDownloader().download(target.source_type, target.doc_id, attachment)


def handle_file_parse(target: RetryTarget) -> None:
    file_path = target.file_path or payload_value(target, "saved_path")
    if not file_path:
        raise ValueError("missing file_path for file_parse retry")
    from crawler.parsers.file_text_router import FileTextRouter

    result = FileTextRouter().extract_text(file_path)
    if not result or not str(result.get("attachment_text") or "").strip():
        raise ValueError(f"file_parse produced no text: {file_path}")


def handle_board_detail(target: RetryTarget) -> None:
    if not target.url:
        raise ValueError("missing url for board_detail retry")
    from crawler.extractors.board_detail_extractor import BoardDetailExtractor

    raw_doc = BoardDetailExtractor().extract_detail(
        target.source_type or "webpage",
        target.url,
        title_hint=payload_value(target, "title_hint"),
    )
    from crawler.run.run_full_pipeline import save_document_bundle

    save_document_bundle(raw_doc, download_attachments=True)


def handle_board_list(target: RetryTarget) -> None:
    if not target.url:
        raise ValueError("missing url for board_list retry")
    run_board_pipeline(
        source_type=target.source_type or "webpage",
        list_url=target.url,
        pages=int(payload_value(target, "pages", payload_value(target, "page_no", 1)) or 1),
        max_detail_count=payload_value(target, "max_detail_count"),
    )


def handle_chunking(target: RetryTarget) -> None:
    if target.file_path:
        curated_file = Path(target.file_path)
    elif target.source_type and target.doc_id:
        curated_file = CURATED_DOC_DIR / target.source_type / f"{target.doc_id}.json"
    else:
        raise ValueError("missing curated file path for chunking retry")
    if not curated_file.exists():
        raise FileNotFoundError(f"curated file not found: {curated_file}")
    chunk_path = chunk_curated_file(curated_file)
    if not chunk_path:
        raise ValueError(f"chunking skipped without output: {curated_file}")


Handler = Callable[[RetryTarget], None]


HANDLER_REGISTRY: dict[str, Handler] = {
    "vector_ingestion": handle_vector_ingestion,
    "static_page": handle_static_page,
    "attachment_download": handle_attachment_download,
    "file_parse": handle_file_parse,
    "board_detail": handle_board_detail,
    "board_list": handle_board_list,
    "chunking": handle_chunking,
}


def process_retry_targets(
    targets: list[RetryTarget],
    execute: bool,
    state_store: CrawlerStateStore | None = None,
) -> None:
    for target in targets:
        handler = HANDLER_REGISTRY.get(target.task_type)
        if not handler:
            print(f"[UNKNOWN TASK TYPE] {describe_target(target)}")
            if execute and state_store and target.queue_id:
                state_store.mark_unknown_task_type(target.queue_id, target.task_type)
            continue

        if not execute:
            print(f"[DRY RUN RETRY] handler={target.task_type} {describe_target(target)} file_path={target.file_path}")
            continue

        try:
            handler(target)
            if state_store and target.queue_id:
                state_store.mark_retry_done(target.queue_id)
            print(f"[RETRY OK] {describe_target(target)}")
        except Exception as exc:
            if state_store and target.queue_id:
                state_store.mark_retry_failed(target.queue_id, exc)
            print(f"[RETRY ERROR] {describe_target(target)} error={exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="crawl_logs 또는 retry queue의 크롤러 실패 항목을 재처리합니다.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="도움말을 보여주고 종료합니다.")
    parser._optionals.title = "옵션"
    parser.add_argument("--execute", action="store_true", help="실제로 재처리를 실행합니다. 기본값은 dry-run입니다.")
    parser.add_argument("--limit", type=int, default=10, help="확인할 고유 실패 항목 최대 개수입니다.")
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
        help="재처리할 stage입니다. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument(
        "--from-retry-queue",
        action="store_true",
        help="crawl_logs 대신 crawler_retry_queue에서 대기 중인 대상을 읽습니다.",
    )
    parser.add_argument(
        "--allow-insecure-ssl",
        action="store_true",
        help="설정된 구형 DEU 호스트에 한해 SSL 검증 없이 재시도를 허용합니다.",
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
        if args.allow_insecure_ssl:
            os.environ["CRAWLER_ALLOW_INSECURE_SSL"] = "1"
        process_retry_targets(targets, execute=args.execute, state_store=state_store)
    finally:
        if state_store:
            state_store.close()


if __name__ == "__main__":
    main()
