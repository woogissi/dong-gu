from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urldefrag

from psycopg2.extras import Json, RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader


STATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crawler_documents (
  id bigserial PRIMARY KEY,
  doc_id text,
  url text NOT NULL,
  canonical_url text NOT NULL UNIQUE,
  final_url text,
  status text NOT NULL,
  source_type text,
  page_kind text,
  checksum text,
  retry_count integer NOT NULL DEFAULT 0,
  artifact_paths jsonb NOT NULL DEFAULT '{}'::jsonb,
  extractor_name text,
  extractor_version text,
  last_error text,
  last_error_stage text,
  next_retry_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawler_documents_status
ON crawler_documents(status);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_updated_at
ON crawler_documents(updated_at);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_source_type
ON crawler_documents(source_type);
CREATE INDEX IF NOT EXISTS idx_crawler_documents_next_retry_at
ON crawler_documents(next_retry_at);

CREATE TABLE IF NOT EXISTS crawler_dynamic_seeds (
  id bigserial PRIMARY KEY,
  url text NOT NULL,
  canonical_url text NOT NULL UNIQUE,
  confidence numeric NOT NULL,
  source_type text,
  source_group text,
  page_kind text NOT NULL,
  pattern_reason text,
  discovered_from text,
  status text NOT NULL DEFAULT 'candidate',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_status
ON crawler_dynamic_seeds(status);
CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_confidence
ON crawler_dynamic_seeds(confidence);
CREATE INDEX IF NOT EXISTS idx_crawler_dynamic_seeds_source_type
ON crawler_dynamic_seeds(source_type);

CREATE TABLE IF NOT EXISTS crawler_retry_queue (
  id bigserial PRIMARY KEY,
  doc_id text,
  url text,
  stage text NOT NULL,
  reason text NOT NULL,
  retry_count integer NOT NULL DEFAULT 0,
  next_retry_at timestamptz,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_status
ON crawler_retry_queue(status);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_next_retry_at
ON crawler_retry_queue(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_crawler_retry_queue_stage
ON crawler_retry_queue(stage);

ALTER TABLE crawler_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawler_dynamic_seeds ENABLE ROW LEVEL SECURITY;
ALTER TABLE crawler_retry_queue ENABLE ROW LEVEL SECURITY;
"""


def canonicalize_url(url: str) -> str:
    canonical, _fragment = urldefrag(url.strip())
    return canonical


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def confidence_for_reason(reason: str | None) -> float:
    if reason in {"board_list", "board_detail"}:
        return 0.9
    if reason == "board_mode_hint":
        return 0.85
    if reason == "board_path_hint":
        return 0.75
    if reason == "board_query_hint":
        return 0.6
    return 0.0


def dynamic_seed_row_to_seed(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": f"dynamic_seed_{row['id']}",
        "url": row["url"],
        "source_type": row.get("source_type") or row.get("source_group") or "webpage",
        "source_group": row.get("source_group") or row.get("source_type") or "webpage",
        "page_kind": row["page_kind"],
        "priority": "P1",
        "crawl_enabled": True,
        "discover_board_candidates": False,
        "dynamic_seed_id": row["id"],
        "confidence": float(row["confidence"]),
        "pattern_reason": row.get("pattern_reason"),
    }


class CrawlerStateStore:
    def __init__(self, loader: PGVectorLoader | None = None):
        self._owns_loader = loader is None
        self.loader = loader or PGVectorLoader(autocommit_writes=False)
        self.conn = self.loader.conn

    def close(self) -> None:
        if self._owns_loader:
            self.loader.close()

    def commit(self) -> None:
        self.loader.commit()

    def rollback(self) -> None:
        self.loader.rollback()

    def ensure_tables(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(STATE_SCHEMA_SQL)
        self.commit()

    def upsert_dynamic_seed(self, candidate: dict[str, Any]) -> dict[str, Any]:
        confidence = candidate.get("confidence")
        if confidence is None:
            confidence = confidence_for_reason(candidate.get("reason"))
        params = {
            "url": candidate["url"],
            "canonical_url": canonicalize_url(candidate["url"]),
            "confidence": confidence,
            "source_type": candidate.get("source_type") or candidate.get("source_type_hint"),
            "source_group": candidate.get("source_group"),
            "page_kind": candidate["page_kind"],
            "pattern_reason": candidate.get("reason") or candidate.get("pattern_reason"),
            "discovered_from": candidate.get("discovered_from"),
        }
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO crawler_dynamic_seeds (
                  url,
                  canonical_url,
                  confidence,
                  source_type,
                  source_group,
                  page_kind,
                  pattern_reason,
                  discovered_from,
                  status,
                  updated_at
                )
                VALUES (
                  %(url)s,
                  %(canonical_url)s,
                  %(confidence)s,
                  %(source_type)s,
                  %(source_group)s,
                  %(page_kind)s,
                  %(pattern_reason)s,
                  %(discovered_from)s,
                  'candidate',
                  now()
                )
                ON CONFLICT (canonical_url) DO UPDATE SET
                  url = EXCLUDED.url,
                  confidence = GREATEST(crawler_dynamic_seeds.confidence, EXCLUDED.confidence),
                  source_type = COALESCE(crawler_dynamic_seeds.source_type, EXCLUDED.source_type),
                  source_group = COALESCE(crawler_dynamic_seeds.source_group, EXCLUDED.source_group),
                  page_kind = EXCLUDED.page_kind,
                  pattern_reason = EXCLUDED.pattern_reason,
                  discovered_from = COALESCE(crawler_dynamic_seeds.discovered_from, EXCLUDED.discovered_from),
                  updated_at = now()
                RETURNING *;
                """,
                params,
            )
            row = dict(cur.fetchone())
        self.commit()
        return row

    def promote_dynamic_seeds(self, min_confidence: float = 0.8) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crawler_dynamic_seeds
                SET status = 'promoted',
                    updated_at = now()
                WHERE status = 'candidate'
                  AND confidence >= %s
                  AND page_kind = 'board_list';
                """,
                (min_confidence,),
            )
            count = cur.rowcount
        self.commit()
        return count

    def list_promoted_dynamic_seeds(self, min_confidence: float = 0.8) -> list[dict[str, Any]]:
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM crawler_dynamic_seeds
                WHERE status = 'promoted'
                  AND confidence >= %s
                  AND page_kind = 'board_list'
                ORDER BY confidence DESC, updated_at DESC;
                """,
                (min_confidence,),
            )
            return [dynamic_seed_row_to_seed(dict(row)) for row in cur.fetchall()]

    def upsert_document_state(
        self,
        *,
        url: str,
        status: str,
        doc_id: str | None = None,
        final_url: str | None = None,
        source_type: str | None = None,
        page_kind: str | None = None,
        checksum: str | None = None,
        artifact_paths: dict[str, Any] | None = None,
        extractor_name: str | None = None,
        extractor_version: str | None = None,
        error: str | None = None,
        error_stage: str | None = None,
    ) -> None:
        params = {
            "doc_id": doc_id,
            "url": url,
            "canonical_url": canonicalize_url(url),
            "final_url": final_url,
            "status": status,
            "source_type": source_type,
            "page_kind": page_kind,
            "checksum": checksum,
            "artifact_paths": Json(artifact_paths or {}),
            "extractor_name": extractor_name,
            "extractor_version": extractor_version,
            "last_error": error,
            "last_error_stage": error_stage,
        }
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crawler_documents (
                  doc_id,
                  url,
                  canonical_url,
                  final_url,
                  status,
                  source_type,
                  page_kind,
                  checksum,
                  artifact_paths,
                  extractor_name,
                  extractor_version,
                  last_error,
                  last_error_stage,
                  updated_at
                )
                VALUES (
                  %(doc_id)s,
                  %(url)s,
                  %(canonical_url)s,
                  %(final_url)s,
                  %(status)s,
                  %(source_type)s,
                  %(page_kind)s,
                  %(checksum)s,
                  %(artifact_paths)s::jsonb,
                  %(extractor_name)s,
                  %(extractor_version)s,
                  %(last_error)s,
                  %(last_error_stage)s,
                  now()
                )
                ON CONFLICT (canonical_url) DO UPDATE SET
                  doc_id = COALESCE(EXCLUDED.doc_id, crawler_documents.doc_id),
                  url = EXCLUDED.url,
                  final_url = COALESCE(EXCLUDED.final_url, crawler_documents.final_url),
                  status = EXCLUDED.status,
                  source_type = COALESCE(EXCLUDED.source_type, crawler_documents.source_type),
                  page_kind = COALESCE(EXCLUDED.page_kind, crawler_documents.page_kind),
                  checksum = COALESCE(EXCLUDED.checksum, crawler_documents.checksum),
                  artifact_paths = crawler_documents.artifact_paths || EXCLUDED.artifact_paths,
                  extractor_name = COALESCE(EXCLUDED.extractor_name, crawler_documents.extractor_name),
                  extractor_version = COALESCE(EXCLUDED.extractor_version, crawler_documents.extractor_version),
                  last_error = EXCLUDED.last_error,
                  last_error_stage = EXCLUDED.last_error_stage,
                  updated_at = now();
                """,
                params,
            )
        self.commit()
