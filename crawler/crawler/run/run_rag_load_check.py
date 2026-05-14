from __future__ import annotations

import argparse
from typing import Any

from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader


CHECK_SQL = """
WITH
summary AS (
  SELECT
    count(*) AS total_docs,
    count(*) FILTER (WHERE source_url ILIKE '%deu.ac.kr%') AS deu_docs,
    count(*) FILTER (
      WHERE page_kind = 'board_detail'
         OR source_type IN ('notice', 'academic_notice')
         OR source_url ILIKE '%articleNo=%'
    ) AS board_docs,
    count(*) FILTER (WHERE page_kind = 'static_page') AS static_docs
  FROM documents
),
contents AS (
  SELECT count(*) AS total_contents
  FROM document_contents
),
missing_contents AS (
  SELECT count(*) AS missing_count
  FROM documents d
  LEFT JOIN document_contents c ON d.doc_id = c.doc_id
  WHERE c.doc_id IS NULL
),
chunks_summary AS (
  SELECT count(*) AS total_chunks, count(DISTINCT doc_id) AS chunk_docs
  FROM chunks
),
embeddings_summary AS (
  SELECT count(*) AS total_embeddings
  FROM chunk_embeddings
),
missing_embeddings AS (
  SELECT count(*) AS missing_count
  FROM chunks c
  LEFT JOIN chunk_embeddings e ON c.chunk_id = e.chunk_id
  WHERE e.chunk_id IS NULL
),
assets_summary AS (
  SELECT
    count(*) AS total_assets,
    count(*) FILTER (WHERE asset_type = 'attachment') AS attachment_assets,
    count(*) FILTER (WHERE asset_type = 'attachment' AND parser_type IS NOT NULL) AS parsed_attachment_assets
  FROM document_assets
)
SELECT jsonb_build_object(
  'summary', (SELECT to_jsonb(summary) FROM summary),
  'contents', (SELECT to_jsonb(contents) FROM contents),
  'missing_contents', (SELECT to_jsonb(missing_contents) FROM missing_contents),
  'chunks', (SELECT to_jsonb(chunks_summary) FROM chunks_summary),
  'embeddings', (SELECT to_jsonb(embeddings_summary) FROM embeddings_summary),
  'missing_embeddings', (SELECT to_jsonb(missing_embeddings) FROM missing_embeddings),
  'assets', (SELECT to_jsonb(assets_summary) FROM assets_summary),
  'source_types', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT source_type, count(*) AS count
      FROM documents
      GROUP BY source_type
      ORDER BY count(*) DESC
      LIMIT 10
    ) t
  ),
  'content_types', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT content_type, count(*) AS count
      FROM document_contents
      GROUP BY content_type
      ORDER BY count(*) DESC
      LIMIT 10
    ) t
  ),
  'board_samples', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT title, source_url AS url
      FROM documents
      WHERE page_kind = 'board_detail'
         OR source_type IN ('notice', 'academic_notice')
         OR source_url ILIKE '%board%'
         OR source_url ILIKE '%articleNo=%'
      LIMIT 5
    ) t
  ),
  'missing_content_samples', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT d.id, d.title
      FROM documents d
      LEFT JOIN document_contents c ON d.doc_id = c.doc_id
      WHERE c.doc_id IS NULL
      LIMIT 5
    ) t
  ),
  'chunk_samples', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT doc_id AS document_id, length(content) AS content_length
      FROM chunks
      LIMIT 5
    ) t
  ),
  'asset_samples', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT file_name, file_url AS url, asset_type, parser_type
      FROM document_assets
      LIMIT 5
    ) t
  ),
  'crawl_log_samples', (
    SELECT coalesce(jsonb_agg(row_to_json(t)), '[]'::jsonb)
    FROM (
      SELECT
        id,
        created_at,
        run_type,
        stage,
        source_type,
        doc_id,
        url,
        file_url,
        error_type,
        left(error_message, 240) AS error_message
      FROM crawl_logs
      ORDER BY created_at DESC
      LIMIT 5
    ) t
  )
) AS rag_check;
"""


def fetch_check() -> dict[str, Any]:
    loader = PGVectorLoader()
    try:
        with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(CHECK_SQL)
            row = cur.fetchone()
            return dict(row["rag_check"])
    finally:
        loader.close()


def pct(part: int, total: int) -> float:
    return round((part / total) * 100, 2) if total else 0.0


def evaluate(result: dict[str, Any]) -> tuple[str, list[str]]:
    summary = result["summary"]
    contents = result["contents"]
    chunks = result["chunks"]
    embeddings = result["embeddings"]
    assets = result["assets"]
    missing_contents = result["missing_contents"]["missing_count"]
    missing_embeddings = result["missing_embeddings"]["missing_count"]
    recent_errors = [item for item in result["crawl_log_samples"] if item.get("error_type")]

    total_docs = summary["total_docs"]
    total_chunks = chunks["total_chunks"]
    deu_ratio = summary["deu_docs"] / total_docs if total_docs else 0.0
    missing_embedding_ratio = missing_embeddings / total_chunks if total_chunks else 0.0

    issues = []
    if total_docs == 0:
        issues.append("documents is empty")
    if deu_ratio < 0.7:
        issues.append(f"deu ratio below 70%: {pct(summary['deu_docs'], total_docs)}%")
    if summary["board_docs"] == 0:
        issues.append("board documents not found")
    if summary["static_docs"] == 0:
        issues.append("static pages not found")
    if assets["attachment_assets"] == 0:
        issues.append("attachments not found")
    if contents["total_contents"] == 0:
        issues.append("document_contents is empty")
    if missing_contents:
        issues.append(f"documents without contents: {missing_contents}")
    if total_chunks == 0:
        issues.append("chunks is empty")
    if missing_embedding_ratio >= 0.2:
        issues.append(f"embedding missing ratio above 20%: {pct(missing_embeddings, total_chunks)}%")
    if len(recent_errors) >= 3:
        issues.append(f"recent crawl log errors: {len(recent_errors)}/5")

    if total_docs == 0 or total_chunks == 0 or contents["total_contents"] == 0:
        return "비정상", issues
    if issues:
        return "부분정상", issues
    return "정상", issues


def print_rows(rows: list[dict[str, Any]], empty_message: str) -> None:
    if not rows:
        print(f"- {empty_message}")
        return
    for row in rows:
        print(f"- {row}")


def print_report(result: dict[str, Any]) -> None:
    verdict, issues = evaluate(result)
    summary = result["summary"]
    contents = result["contents"]
    chunks = result["chunks"]
    embeddings = result["embeddings"]
    assets = result["assets"]
    missing_embeddings = result["missing_embeddings"]["missing_count"]

    total_docs = summary["total_docs"]
    deu_docs = summary["deu_docs"]
    total_chunks = chunks["total_chunks"]

    print("# 동의대학교 RAG 적재 검증")
    print()
    print("## 결론")
    print(verdict)
    print()
    print("## 핵심 수치")
    print(f"- documents: {total_docs}")
    print(f"- contents: {contents['total_contents']}")
    print(f"- chunks: {total_chunks}")
    print(f"- embeddings: {embeddings['total_embeddings']}")
    print(f"- 첨부파일 수: {assets['attachment_assets']}")
    print(f"- deu 비율: {deu_docs}/{total_docs} ({pct(deu_docs, total_docs)}%)")
    print(f"- embedding 누락: {missing_embeddings}/{total_chunks} ({pct(missing_embeddings, total_chunks)}%)")
    print()
    print("## 게시판 상태")
    print(f"- board documents: {summary['board_docs']}")
    print_rows(result["board_samples"], "게시판 샘플 없음")
    print()
    print("## 정적 페이지 상태")
    print(f"- static pages: {summary['static_docs']}")
    print()
    print("## 첨부파일 상태")
    print(f"- attachment assets: {assets['attachment_assets']}")
    print(f"- parsed attachment assets: {assets['parsed_attachment_assets']}")
    print_rows(result["asset_samples"], "첨부파일 샘플 없음")
    print()
    print("## RAG 사용 가능성")
    print(f"- chunk-linked documents: {chunks['chunk_docs']}")
    print(f"- documents without contents: {result['missing_contents']['missing_count']}")
    print_rows(result["chunk_samples"], "chunk 샘플 없음")
    print()
    print("## 발견 문제")
    if issues:
        print_rows([{"issue": issue} for issue in issues], "문제 없음")
    else:
        print("- 문제 없음")
    print()
    print("## 최근 crawl_logs")
    print_rows(result["crawl_log_samples"], "최근 crawl log 없음")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded RAG load check for the DEU crawler tables."
    )
    parser.add_argument(
        "--fail-on-partial",
        action="store_true",
        help="Exit non-zero when the result is partial or abnormal.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = fetch_check()
    verdict, _ = evaluate(result)
    print_report(result)
    if args.fail_on_partial and verdict != "정상":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
