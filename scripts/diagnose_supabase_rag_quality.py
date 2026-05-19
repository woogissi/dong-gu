from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
TARGET_TABLES = (
    "query_logs",
    "response_logs",
    "retrieval_logs",
    "retrieval_selected_chunks",
    "documents",
    "chunks",
    "chunk_embeddings",
    "document_contents",
    "document_assets",
    "crawl_logs",
    "crawl_errors",
)
NEGATIVE_ANSWER_PATTERNS = (
    "확인할 수 없",
    "찾을 수 없",
    "알 수 없",
    "제공된 정보",
    "검색 결과",
    "근거가",
    "죄송",
    "오류",
)
GENERIC_TERMS = {
    "정보",
    "알려줘",
    "어디",
    "어떻게",
    "뭐야",
    "누구",
    "기간",
    "일정",
    "최근",
    "이번",
    "동의대",
    "동의대학교",
    "학교",
    "신청",
    "지원",
    "공지",
    "마감일",
    "시점",
    "이름",
    "한글",
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def normalize_database_url(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("postgresql+psycopg2://"):
        return normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    return normalized


def open_connection():
    load_env_file(ROOT / ".env")
    database_url = normalize_database_url(os.getenv("DATABASE_URL") or "")
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
    )


def fetch_all(cur, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, tuple(params))
    return [dict(row) for row in cur.fetchall()]


def fetch_one(cur, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
    cur.execute(sql, tuple(params))
    row = cur.fetchone()
    return dict(row) if row else None


def table_exists(cur, table_name: str) -> bool:
    row = fetch_one(
        cur,
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        ) AS exists
        """,
        (table_name,),
    )
    return bool(row and row["exists"])


def schema_summary(cur) -> dict[str, Any]:
    existing = [table for table in TARGET_TABLES if table_exists(cur, table)]
    columns = fetch_all(
        cur,
        """
        SELECT
            c.table_name,
            c.column_name,
            c.data_type,
            c.udt_name,
            c.is_nullable,
            c.column_default
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = ANY(%s)
        ORDER BY c.table_name, c.ordinal_position
        """,
        (existing,),
    )
    constraints = fetch_all(
        cur,
        """
        SELECT
            tc.table_name,
            tc.constraint_type,
            tc.constraint_name,
            string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns,
            ccu.table_name AS foreign_table,
            string_agg(ccu.column_name, ', ' ORDER BY kcu.ordinal_position) AS foreign_columns
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema = ccu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = ANY(%s)
          AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
        GROUP BY tc.table_name, tc.constraint_type, tc.constraint_name, ccu.table_name
        ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name
        """,
        (existing,),
    )
    counts = {}
    for table in existing:
        try:
            counts[table] = fetch_one(cur, f"SELECT count(*) AS count FROM public.{table}")["count"]
        except psycopg2.Error:
            cur.connection.rollback()
            counts[table] = None
    return {
        "existing_tables": existing,
        "columns": columns,
        "constraints": constraints,
        "row_counts": counts,
        "join_paths": {
            "query_logs_to_retrieval_logs": "query_logs.request_id = retrieval_logs.request_id",
            "retrieval_logs_to_selected_chunks": "retrieval_logs.id = retrieval_selected_chunks.retrieval_log_id",
            "query_logs_to_response_logs": "query_logs.request_id = response_logs.request_id",
            "selected_chunk_to_source": "retrieval_selected_chunks.chunk_id = chunks.chunk_id; chunks.doc_id = documents.doc_id",
        },
    }


def failure_cases(cur, limit: int) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        WITH latest_retrieval AS (
            SELECT DISTINCT ON (request_id)
                *
            FROM retrieval_logs
            ORDER BY request_id, created_at DESC, id DESC
        ),
        selected AS (
            SELECT
                retrieval_log_id,
                count(*) AS selected_rows,
                jsonb_agg(
                    jsonb_build_object(
                        'rank', rsc.rank,
                        'chunk_id', rsc.chunk_id,
                        'doc_id', rsc.doc_id,
                        'score', rsc.score,
                        'rerank_score', rsc.rerank_score,
                        'title', d.title,
                        'source_type', d.source_type,
                        'department', d.department,
                        'content_preview', left(c.content, 260),
                        'metadata', rsc.metadata
                    )
                    ORDER BY rsc.rank
                ) AS selected_chunks
            FROM retrieval_selected_chunks rsc
            LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
            LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id)
            GROUP BY retrieval_log_id
        )
        SELECT
            q.id AS query_id,
            q.request_id,
            q.question AS user_query,
            q.intent_type AS intent,
            q.created_at,
            rl.id AS retrieval_log_id,
            rl.normalized_query,
            rl.rewritten_query,
            rl.rewritten_queries,
            rl.keywords AS extracted_keywords,
            rl.category,
            rl.filters,
            rl.retrieval_strategy,
            rl.retrieval_top_k,
            rl.retrieval_strategy_log,
            rl.fallback_used,
            rl.retrieved_doc_count,
            rl.reranked_doc_count,
            rl.selected_doc_count,
            rl.success AS retrieval_success,
            rl.error_message AS retrieval_error,
            rl.metadata AS retrieval_metadata,
            coalesce(s.selected_rows, 0) AS selected_rows,
            coalesce(s.selected_chunks, '[]'::jsonb) AS selected_chunks,
            r.answer_text AS final_answer,
            r.success AS response_success,
            r.error_message AS response_error,
            r.response_time_ms,
            (
                coalesce(rl.selected_doc_count, 0) = 0
                OR coalesce(rl.retrieved_doc_count, 0) = 0
                OR rl.fallback_used
                OR rl.success = false
                OR r.success = false
                OR r.answer_text IS NULL
                OR r.answer_text ILIKE ANY(%s)
                OR (rl.metadata ? 'retrieval_quality' AND rl.metadata->'retrieval_quality'->>'ok' = 'false')
            ) AS suspicious
        FROM query_logs q
        LEFT JOIN latest_retrieval rl ON rl.request_id = q.request_id
        LEFT JOIN selected s ON s.retrieval_log_id = rl.id
        LEFT JOIN response_logs r ON r.request_id = q.request_id
        WHERE r.id IS NOT NULL OR rl.id IS NOT NULL
        ORDER BY suspicious DESC, q.created_at DESC
        LIMIT %s
        """,
        ([f"%{pattern}%" for pattern in NEGATIVE_ANSWER_PATTERNS], limit),
    )


def extract_terms(*values: Any) -> list[str]:
    terms: list[str] = []
    for value in values:
        if not value:
            continue
        if isinstance(value, list):
            terms.extend(str(item) for item in value if item)
            continue
        if isinstance(value, dict):
            terms.extend(str(item) for item in value.values() if item and not isinstance(item, (dict, list)))
            continue
        terms.extend(re.findall(r"[0-9A-Za-z가-힣]{2,}", str(value)))
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = term.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result[:12]


def lexical_probe(cur, terms: list[str], category: str | None, limit: int = 8) -> list[dict[str, Any]]:
    if not terms:
        return []
    patterns = [f"%{term}%" for term in terms]
    category_pattern = f"%{category}%" if category else None
    return fetch_all(
        cur,
        """
        SELECT
            d.doc_id,
            c.chunk_id,
            d.title,
            d.source_type,
            d.department,
            d.published_at,
            d.source_url,
            length(c.content) AS chunk_len,
            (
                SELECT count(*)
                FROM unnest(%s::text[]) AS p(pattern)
                WHERE c.content ILIKE p.pattern
                   OR d.title ILIKE p.pattern
            ) AS term_hits,
            CASE
                WHEN %s::text IS NULL THEN false
                WHEN d.source_type ILIKE %s OR d.department ILIKE %s OR d.title ILIKE %s THEN true
                ELSE false
            END AS category_matches,
            left(c.content, 360) AS content_preview
        FROM chunks c
        JOIN documents d ON d.doc_id = c.doc_id
        WHERE EXISTS (
            SELECT 1
            FROM unnest(%s::text[]) AS p(pattern)
            WHERE c.content ILIKE p.pattern
               OR d.title ILIKE p.pattern
        )
        ORDER BY term_hits DESC, category_matches DESC, d.published_at DESC NULLS LAST, length(c.content) DESC
        LIMIT %s
        """,
        (patterns, category, category_pattern, category_pattern, category_pattern, patterns, limit),
    )


def precise_terms(terms: list[str]) -> list[str]:
    result = []
    for term in terms:
        normalized = term.strip()
        if len(normalized) < 3 or normalized in GENERIC_TERMS:
            continue
        if normalized.isdigit():
            continue
        result.append(normalized)
    return result[:8]


def precise_probe(cur, terms: list[str], limit: int = 8) -> list[dict[str, Any]]:
    strong_terms = precise_terms(terms)
    if not strong_terms:
        return []
    patterns = [f"%{term}%" for term in strong_terms]
    return fetch_all(
        cur,
        """
        SELECT
            d.doc_id,
            c.chunk_id,
            d.title,
            d.source_type,
            d.department,
            d.published_at,
            d.source_url,
            length(c.content) AS chunk_len,
            (
                SELECT count(*)
                FROM unnest(%s::text[]) AS p(pattern)
                WHERE c.content ILIKE p.pattern
                   OR d.title ILIKE p.pattern
            ) AS strong_term_hits,
            left(c.content, 360) AS content_preview
        FROM chunks c
        JOIN documents d ON d.doc_id = c.doc_id
        WHERE EXISTS (
            SELECT 1
            FROM unnest(%s::text[]) AS p(pattern)
            WHERE c.content ILIKE p.pattern
               OR d.title ILIKE p.pattern
        )
        ORDER BY strong_term_hits DESC, d.published_at DESC NULLS LAST, length(c.content) DESC
        LIMIT %s
        """,
        (patterns, patterns, limit),
    )


def data_health_for_docs(cur, doc_ids: list[str]) -> list[dict[str, Any]]:
    if not doc_ids:
        return []
    return fetch_all(
        cur,
        """
        SELECT
            d.doc_id,
            d.title,
            d.source_type,
            d.department,
            d.source_url,
            count(DISTINCT c.chunk_id) AS chunks,
            coalesce(sum(length(c.content)), 0) AS chunk_chars,
            count(DISTINCT ce.chunk_id) AS embedded_chunks,
            count(DISTINCT dc.id) AS contents,
            coalesce(sum(length(dc.content)), 0) AS content_chars,
            count(DISTINCT da.id) AS assets,
            count(DISTINCT da.id) FILTER (WHERE dc_asset.id IS NULL) AS assets_without_content
        FROM documents d
        LEFT JOIN chunks c ON c.doc_id = d.doc_id
        LEFT JOIN chunk_embeddings ce ON ce.chunk_id = c.chunk_id
        LEFT JOIN document_contents dc ON dc.doc_id = d.doc_id
        LEFT JOIN document_assets da ON da.doc_id = d.doc_id
        LEFT JOIN document_contents dc_asset ON dc_asset.asset_id = da.id
        WHERE d.doc_id = ANY(%s)
        GROUP BY d.doc_id, d.title, d.source_type, d.department, d.source_url
        ORDER BY d.doc_id
        """,
        (doc_ids,),
    )


def selected_term_hits(case: dict[str, Any], terms: list[str]) -> int:
    selected_chunks = case.get("selected_chunks") or []
    selected_text = " ".join(
        " ".join(
            str(chunk.get(key) or "")
            for key in ("title", "content_preview", "source_type", "department")
        )
        for chunk in selected_chunks
        if isinstance(chunk, dict)
    ).lower()
    return sum(1 for term in terms if term.lower() in selected_text)


def classify_case(
    case: dict[str, Any],
    probes: list[dict[str, Any]],
    precise_probes: list[dict[str, Any]],
    health: list[dict[str, Any]],
    terms: list[str],
) -> dict[str, Any]:
    selected_chunks = case.get("selected_chunks") or []
    selected_chunk_ids = {chunk.get("chunk_id") for chunk in selected_chunks if isinstance(chunk, dict)}
    evidence_probes = precise_probes or probes
    probe_chunk_ids = {probe.get("chunk_id") for probe in evidence_probes}
    selected_has_probe_match = bool(selected_chunk_ids & probe_chunk_ids)
    selected_has_text = any((chunk.get("content_preview") or "").strip() for chunk in selected_chunks if isinstance(chunk, dict))
    answer = case.get("final_answer") or ""
    negative_answer = any(pattern in answer for pattern in NEGATIVE_ANSWER_PATTERNS)
    zero_selected = int(case.get("selected_doc_count") or 0) == 0 and int(case.get("selected_rows") or 0) == 0
    selected_hits = selected_term_hits(case, terms)

    if not case.get("retrieval_log_id"):
        if case.get("intent") == "PROFANITY":
            cause = "OUT_OF_SCOPE_POLICY_ROUTE"
            reason = "The request was classified as profanity and intentionally did not enter RAG retrieval."
        elif evidence_probes:
            cause = "D_INTENT_OR_ROUTING_GAP"
            reason = "No retrieval log exists, but DB contains evidence-like chunks; intent classification or route selection likely bypassed RAG."
        else:
            cause = "NO_RAG_ROUTE_NO_DB_EVIDENCE"
            reason = "No retrieval log exists and lexical probes did not find evidence-like DB chunks."
        return {
            "cause": cause,
            "reason": reason,
            "selected_has_lexical_evidence_overlap": False,
            "selected_term_hits": selected_hits,
            "negative_or_uncertain_answer": negative_answer,
            "data_issue_doc_count": 0,
        }

    data_issue_docs = [
        row
        for row in health
        if int(row.get("chunks") or 0) == 0
        or int(row.get("chunk_chars") or 0) < 300
        or int(row.get("embedded_chunks") or 0) < int(row.get("chunks") or 0)
        or int(row.get("assets_without_content") or 0) > 0
    ]

    if not evidence_probes:
        cause = "A_DATA_OR_CRAWLER_GAP"
        reason = "No precise evidence chunk was found in documents/chunks for query, rewrite, or extracted keywords."
    elif zero_selected:
        cause = "B_RETRIEVAL_SELECTION_GAP"
        reason = "Evidence-like chunks exist in DB, but retrieval selected no chunks."
    elif case.get("fallback_used") or case.get("retrieval_success") is False:
        cause = "B_RETRIEVAL_FALLBACK_OR_ERROR"
        reason = "Retrieval produced fallback/error even though evidence-like chunks may exist."
    elif (selected_has_probe_match or selected_hits >= 2) and negative_answer:
        cause = "C_GENERATION_GAP"
        reason = "Selected chunks contain query evidence, but final answer is negative, incomplete, or non-committal."
    elif evidence_probes and not selected_has_probe_match:
        cause = "B_RANKING_FILTER_OR_RERANK_GAP"
        reason = "Evidence-like chunks exist, but they are not among selected chunks."
    elif selected_chunks and not selected_has_text:
        cause = "A_DATA_SHAPE_GAP"
        reason = "Selected chunks have missing/blank content preview; inspect chunk/content ingestion."
    elif data_issue_docs:
        cause = "A_PARTIAL_DATA_QUALITY_RISK"
        reason = "Related documents show short/missing chunks, missing embeddings, or unextracted assets."
    else:
        cause = "NEEDS_HUMAN_REVIEW"
        reason = "Logs and lexical probes do not isolate a single failure stage."

    return {
        "cause": cause,
        "reason": reason,
        "selected_has_lexical_evidence_overlap": selected_has_probe_match,
        "selected_term_hits": selected_hits,
        "negative_or_uncertain_answer": negative_answer,
        "data_issue_doc_count": len(data_issue_docs),
    }


def analyze_cases(cur, cases: list[dict[str, Any]], per_case_probe_limit: int) -> list[dict[str, Any]]:
    analyzed = []
    for case in cases:
        terms = extract_terms(
            case.get("user_query"),
            case.get("rewritten_query"),
            case.get("rewritten_queries"),
            case.get("extracted_keywords"),
            case.get("category"),
        )
        probes = lexical_probe(cur, terms, case.get("category"), per_case_probe_limit)
        precise_probes = precise_probe(cur, terms, per_case_probe_limit)
        probe_doc_ids = [row["doc_id"] for row in (precise_probes or probes) if row.get("doc_id")]
        selected_doc_ids = [
            chunk.get("doc_id")
            for chunk in (case.get("selected_chunks") or [])
            if isinstance(chunk, dict) and chunk.get("doc_id")
        ]
        health = data_health_for_docs(cur, sorted(set(probe_doc_ids + selected_doc_ids)))
        analyzed.append(
            {
                **case,
                "probe_terms": terms,
                "precise_probe_terms": precise_terms(terms),
                "db_precise_probe_top": precise_probes,
                "db_lexical_probe_top": probes,
                "related_doc_health": health,
                "diagnosis": classify_case(case, probes, precise_probes, health, terms),
            }
        )
    return analyzed


def corpus_quality(cur) -> dict[str, Any]:
    queries = {
        "coverage_gaps": """
            SELECT 'documents_without_chunks' AS gap, count(*) AS count FROM documents d
            WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.doc_id = d.doc_id)
            UNION ALL
            SELECT 'chunks_without_embeddings', count(*) FROM chunks c
            WHERE NOT EXISTS (SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.chunk_id)
            UNION ALL
            SELECT 'documents_without_contents', count(*) FROM documents d
            WHERE NOT EXISTS (SELECT 1 FROM document_contents dc WHERE dc.doc_id = d.doc_id)
            UNION ALL
            SELECT 'assets_without_extracted_content', count(*) FROM document_assets a
            WHERE NOT EXISTS (SELECT 1 FROM document_contents dc WHERE dc.asset_id = a.id)
            UNION ALL
            SELECT 'very_short_chunks_lt_120', count(*) FROM chunks WHERE length(content) < 120
        """,
        "recent_crawl_errors": """
            SELECT created_at, stage, source_type, doc_id,
                   left(coalesce(url, file_url, file_path, ''), 180) AS target,
                   error_type,
                   left(error_message, 240) AS error_message
            FROM crawl_logs
            ORDER BY created_at DESC
            LIMIT 25
        """,
        "thin_recent_documents": """
            SELECT d.doc_id, d.source_type, d.department, d.title, d.published_at,
                   d.source_url, count(c.chunk_id) AS chunks, coalesce(sum(length(c.content)), 0) AS chars
            FROM documents d
            LEFT JOIN chunks c ON c.doc_id = d.doc_id
            WHERE d.published_at >= now() - interval '180 days'
            GROUP BY d.doc_id, d.source_type, d.department, d.title, d.published_at, d.source_url
            HAVING count(c.chunk_id) = 0 OR coalesce(sum(length(c.content)), 0) < 300
            ORDER BY d.published_at DESC NULLS LAST, chars ASC
            LIMIT 40
        """,
    }
    result: dict[str, Any] = {}
    for name, sql in queries.items():
        try:
            result[name] = fetch_all(cur, sql)
        except psycopg2.Error as exc:
            cur.connection.rollback()
            result[name] = {"error": str(exc)}
    return result


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Diagnose RAG quality loss from Supabase/PostgreSQL logs.")
    parser.add_argument("--limit", type=int, default=30, help="Number of recent/suspicious cases to analyze.")
    parser.add_argument("--probe-limit", type=int, default=8, help="Number of lexical DB probes per case.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args()

    with open_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            schema = schema_summary(cur)
            cases = failure_cases(cur, args.limit)
            analyzed = analyze_cases(cur, cases, args.probe_limit)
            output = {
                "schema": schema,
                "corpus_quality": corpus_quality(cur),
                "failure_cases": analyzed,
            }
    print(json.dumps(output, ensure_ascii=False, default=str, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
