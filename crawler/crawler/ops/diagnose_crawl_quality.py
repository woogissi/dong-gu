from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader


DEFAULT_OUTPUT_DIR = Path("crawler/data/reports/quality")
DEFAULT_TOP_N = 10
DEFAULT_SAMPLE_CHARS = 320
DEFAULT_SHORT_DOC_CHARS = 80
OVERLAP_MIN_CHARS = 50


UI_PREVIEW_PATTERNS: dict[str, list[str]] = {
    "게시물 좌측으로 이동": ["게시물 좌측으로 이동"],
    "게시물 우측으로 이동": ["게시물 우측으로 이동"],
    "이전 정지 시작 다음": ["이전 정지 시작 다음"],
    "More": ["More"],
    "NOTICE": ["NOTICE"],
    "PROGRAM": ["PROGRAM"],
    "행사사진": ["행사사진"],
    "SNS": ["SNS", "페이스북", "트위터", "카카오톡", "카카오스토리", "인스타그램", "유튜브"],
    "로그인": ["로그인"],
    "회원가입": ["회원가입"],
    "PDF 다운로드": ["PDF 다운로드"],
    "HWP 다운로드": ["HWP 다운로드"],
    "전체화면 보기": ["전체화면 보기"],
    "웹진호수": ["웹진호수"],
}


RESIDUAL_NOISE_PATTERNS: dict[str, re.Pattern[str]] = {
    "html_tag_like": re.compile(r"<[A-Za-z][^>]{0,80}>"),
    "entity_like": re.compile(r"&(?:nbsp|amp|lt|gt|quot|apos);", re.IGNORECASE),
    "script_style": re.compile(r"script|stylesheet|function\s*\(|document\.|window\.", re.IGNORECASE),
    "nav_footer_login": re.compile(
        r"header|footer|breadcrumb|quick\s*menu|개인정보처리방침|사이트맵|찾아오시는길|로그인|회원가입",
        re.IGNORECASE,
    ),
}


SHORT_CHUNK_PATTERNS: dict[str, re.Pattern[str]] = {
    "download_stub": re.compile(r"PDF 다운로드|HWP 다운로드|전체화면 보기|다운로드"),
    "table_shell": re.compile(r"\[TABLE|웹진호수|성명\s*\*\s*제목|제목\s*내용"),
    "webzine_stub": re.compile(r"웹진호수|동의\s*(?:DREAM|NEWS|CAMPUS|PEOPLE)"),
}


LONG_DOC_KEYWORDS = (
    "첨부",
    "학칙",
    "규정",
    "모집요강",
    "수강신청",
    "교육과정",
    "입찰",
    "공고",
    "장학",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose loaded RAG crawl quality from document_contents.clean, chunks, "
            "and chunk_embeddings without modifying database rows."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for JSON/Markdown reports. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N, help="Top-N rows for sample tables.")
    parser.add_argument(
        "--sample-chars",
        type=int,
        default=DEFAULT_SAMPLE_CHARS,
        help="Maximum characters per sample excerpt.",
    )
    parser.add_argument(
        "--short-doc-chars",
        type=int,
        default=DEFAULT_SHORT_DOC_CHARS,
        help="Clean document length threshold for very short documents.",
    )
    return parser.parse_args()


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalized_hash(text: str | None) -> str:
    normalized = normalize_text(text).lower()
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def excerpt(text: str | None, limit: int) -> str:
    value = normalize_text(text)
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def pct(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 2)


def fetch_rows(loader: PGVectorLoader, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with loader.conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def fetch_scalar(loader: PGVectorLoader, sql: str, params: tuple[Any, ...] = ()) -> Any:
    with loader.conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None


def load_dataset(loader: PGVectorLoader) -> dict[str, list[dict[str, Any]]]:
    clean_contents = fetch_rows(
        loader,
        """
        SELECT
            dc.id AS content_id,
            dc.doc_id,
            dc.content,
            length(coalesce(dc.content, '')) AS content_length,
            d.title,
            d.source_url,
            d.source_type,
            d.page_kind
        FROM document_contents dc
        LEFT JOIN documents d ON d.doc_id = dc.doc_id
        WHERE dc.content_type::text = 'clean'
        ORDER BY dc.doc_id, dc.id;
        """,
    )
    raw_clean_pairs = fetch_rows(
        loader,
        """
        WITH raw_by_doc AS (
            SELECT doc_id, string_agg(coalesce(content, ''), E'\n\n' ORDER BY id) AS raw_content
            FROM document_contents
            WHERE content_type::text = 'raw'
            GROUP BY doc_id
        ),
        clean_by_doc AS (
            SELECT doc_id, string_agg(coalesce(content, ''), E'\n\n' ORDER BY id) AS clean_content
            FROM document_contents
            WHERE content_type::text = 'clean'
            GROUP BY doc_id
        )
        SELECT
            c.doc_id,
            c.clean_content,
            r.raw_content,
            d.title,
            d.source_url,
            d.source_type,
            d.page_kind
        FROM clean_by_doc c
        LEFT JOIN raw_by_doc r ON r.doc_id = c.doc_id
        LEFT JOIN documents d ON d.doc_id = c.doc_id
        ORDER BY c.doc_id;
        """,
    )
    chunks = fetch_rows(
        loader,
        """
        SELECT
            c.chunk_id,
            c.doc_id,
            c.content_id,
            c.chunk_index,
            c.section_index,
            c.section_type::text AS section_type,
            c.section_title,
            c.content,
            c.content_length,
            c.content_hash,
            c.metadata,
            d.title,
            d.source_url,
            d.source_type,
            d.page_kind
        FROM chunks c
        LEFT JOIN documents d ON d.doc_id = c.doc_id
        ORDER BY c.doc_id, c.chunk_index, c.id;
        """,
    )
    return {
        "clean_contents": clean_contents,
        "raw_clean_pairs": raw_clean_pairs,
        "chunks": chunks,
    }


def is_almost_same(raw_content: str | None, clean_content: str | None) -> bool:
    raw = normalize_text(raw_content)
    clean = normalize_text(clean_content)
    if not raw and not clean:
        return True
    if not raw or not clean:
        return False
    if raw == clean:
        return True
    shorter = min(len(raw), len(clean))
    longer = max(len(raw), len(clean))
    if longer == 0:
        return True
    if shorter / longer >= 0.98 and (raw in clean or clean in raw):
        return True
    return False


def summarize_clean_quality(
    clean_contents: list[dict[str, Any]],
    raw_clean_pairs: list[dict[str, Any]],
    sample_chars: int,
    short_doc_chars: int,
    top_n: int,
) -> dict[str, Any]:
    total_clean_rows = len(clean_contents)
    total_clean_docs = len({row["doc_id"] for row in clean_contents})

    almost_same_rows = [row for row in raw_clean_pairs if is_almost_same(row.get("raw_content"), row.get("clean_content"))]
    empty_or_short = [
        row
        for row in clean_contents
        if len(normalize_text(row.get("content"))) == 0 or len(normalize_text(row.get("content"))) < short_doc_chars
    ]

    residuals: dict[str, dict[str, Any]] = {}
    for name, pattern in RESIDUAL_NOISE_PATTERNS.items():
        hits = [row for row in clean_contents if pattern.search(row.get("content") or "")]
        residuals[name] = {
            "documents": len({row["doc_id"] for row in hits}),
            "rows": len(hits),
            "samples": sample_content_rows(hits, sample_chars, top_n),
        }

    return {
        "total_clean_rows": total_clean_rows,
        "total_clean_documents": total_clean_docs,
        "raw_clean_pairs": len(raw_clean_pairs),
        "raw_clean_almost_identical_documents": len(almost_same_rows),
        "raw_clean_almost_identical_ratio_percent": pct(len(almost_same_rows), len(raw_clean_pairs)),
        "empty_or_short_clean_rows": len(empty_or_short),
        "empty_or_short_clean_documents": len({row["doc_id"] for row in empty_or_short}),
        "short_doc_threshold_chars": short_doc_chars,
        "empty_or_short_samples": sample_content_rows(empty_or_short, sample_chars, top_n),
        "residual_noise": residuals,
    }


def sample_content_rows(rows: list[dict[str, Any]], sample_chars: int, top_n: int) -> list[dict[str, Any]]:
    samples = []
    for row in rows[:top_n]:
        samples.append(
            {
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "source_url": row.get("source_url"),
                "source_type": row.get("source_type"),
                "page_kind": row.get("page_kind"),
                "content_length": row.get("content_length") or len(row.get("content") or ""),
                "sample": excerpt(row.get("content"), sample_chars),
            }
        )
    return samples


def summarize_ui_preview_noise(
    clean_contents: list[dict[str, Any]], sample_chars: int, top_n: int
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for label, terms in UI_PREVIEW_PATTERNS.items():
        hits = [
            row
            for row in clean_contents
            if any(term in (row.get("content") or "") for term in terms)
        ]
        result[label] = {
            "documents": len({row["doc_id"] for row in hits}),
            "rows": len(hits),
            "samples": sample_content_rows(hits, sample_chars, top_n),
        }
    return result


def summarize_duplicates(
    clean_contents: list[dict[str, Any]], chunks: list[dict[str, Any]], sample_chars: int, top_n: int
) -> dict[str, Any]:
    clean_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in clean_contents:
        value = normalize_text(row.get("content"))
        if value:
            clean_by_hash[normalized_hash(value)].append(row)

    chunk_by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in chunks:
        value = normalize_text(row.get("content"))
        if value:
            chunk_by_hash[normalized_hash(value)].append(row)

    duplicate_clean_groups = {key: rows for key, rows in clean_by_hash.items() if len({r["doc_id"] for r in rows}) > 1}
    duplicate_chunk_groups = {key: rows for key, rows in chunk_by_hash.items() if len(rows) > 1}

    return {
        "duplicate_clean_hash_groups": len(duplicate_clean_groups),
        "duplicate_clean_documents": sum(len({row["doc_id"] for row in rows}) for rows in duplicate_clean_groups.values()),
        "duplicate_clean_top": duplicate_group_samples(duplicate_clean_groups, sample_chars, top_n),
        "duplicate_chunk_hash_groups": len(duplicate_chunk_groups),
        "duplicate_chunk_rows": sum(len(rows) for rows in duplicate_chunk_groups.values()),
        "duplicate_chunk_top": duplicate_group_samples(duplicate_chunk_groups, sample_chars, top_n, chunk_mode=True),
    }


def duplicate_group_samples(
    groups: dict[str, list[dict[str, Any]]],
    sample_chars: int,
    top_n: int,
    chunk_mode: bool = False,
) -> list[dict[str, Any]]:
    sorted_groups = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
    samples = []
    for content_hash, rows in sorted_groups[:top_n]:
        first = rows[0]
        item = {
            "normalized_hash": content_hash,
            "repeat_count": len(rows),
            "distinct_documents": len({row.get("doc_id") for row in rows}),
            "sample_doc_id": first.get("doc_id"),
            "title": first.get("title"),
            "source_url": first.get("source_url"),
            "sample": excerpt(first.get("content"), sample_chars),
        }
        if chunk_mode:
            item["sample_chunk_id"] = first.get("chunk_id")
        samples.append(item)
    return samples


def summarize_short_chunks(chunks: list[dict[str, Any]], sample_chars: int, top_n: int) -> dict[str, Any]:
    short_50 = [row for row in chunks if int(row.get("content_length") or len(row.get("content") or "")) <= 50]
    short_100 = [row for row in chunks if int(row.get("content_length") or len(row.get("content") or "")) <= 100]
    short_150 = [row for row in chunks if int(row.get("content_length") or len(row.get("content") or "")) <= 150]

    pattern_hits: dict[str, Any] = {}
    for name, pattern in SHORT_CHUNK_PATTERNS.items():
        hits = [row for row in short_150 if pattern.search(row.get("content") or "")]
        pattern_hits[name] = {
            "chunks": len(hits),
            "documents": len({row["doc_id"] for row in hits}),
            "samples": sample_chunk_rows(hits, sample_chars, top_n),
        }

    return {
        "chunks_lte_50": len(short_50),
        "chunks_lte_100": len(short_100),
        "chunks_lte_150": len(short_150),
        "samples_lte_100": sample_chunk_rows(short_100, sample_chars, top_n),
        "noise_patterns_lte_150": pattern_hits,
    }


def sample_chunk_rows(rows: list[dict[str, Any]], sample_chars: int, top_n: int) -> list[dict[str, Any]]:
    samples = []
    for row in rows[:top_n]:
        samples.append(
            {
                "chunk_id": row.get("chunk_id"),
                "doc_id": row.get("doc_id"),
                "chunk_index": row.get("chunk_index"),
                "section_type": row.get("section_type"),
                "content_length": row.get("content_length") or len(row.get("content") or ""),
                "title": row.get("title"),
                "source_url": row.get("source_url"),
                "sample": excerpt(row.get("content"), sample_chars),
            }
        )
    return samples


def suffix_prefix_overlap(left: str, right: str, max_len: int = 300) -> int:
    left = left or ""
    right = right or ""
    limit = min(len(left), len(right), max_len)
    for size in range(limit, 0, -1):
        if left[-size:] == right[:size]:
            return size
    return 0


def summarize_overlap(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in chunks:
        by_doc[row["doc_id"]].append(row)

    overlaps = []
    for rows in by_doc.values():
        rows = sorted(rows, key=lambda row: (row.get("chunk_index") or 0, row.get("chunk_id") or ""))
        for prev, current in zip(rows, rows[1:]):
            overlaps.append(suffix_prefix_overlap(prev.get("content") or "", current.get("content") or ""))

    buckets = Counter()
    for value in overlaps:
        if value == 0:
            buckets["0"] += 1
        elif value < 50:
            buckets["1-49"] += 1
        elif value < 80:
            buckets["50-79"] += 1
        elif value < 100:
            buckets["80-99"] += 1
        else:
            buckets["100+"] += 1

    sorted_values = sorted(overlaps)
    pair_count = len(overlaps)
    p50 = median(sorted_values) if sorted_values else 0
    p90 = sorted_values[int(pair_count * 0.90)] if sorted_values else 0
    p99 = sorted_values[min(pair_count - 1, int(pair_count * 0.99))] if sorted_values else 0
    overlap_ge_min = sum(1 for value in overlaps if value >= OVERLAP_MIN_CHARS)

    return {
        "consecutive_pairs": pair_count,
        "pairs_with_any_exact_overlap": sum(1 for value in overlaps if value > 0),
        f"pairs_with_overlap_gte_{OVERLAP_MIN_CHARS}": overlap_ge_min,
        f"overlap_gte_{OVERLAP_MIN_CHARS}_ratio_percent": pct(overlap_ge_min, pair_count),
        "overlap_length_distribution": dict(buckets),
        "overlap_length_p50": p50,
        "overlap_length_p90": p90,
        "overlap_length_p99": p99,
        "overlap_length_max": max(sorted_values) if sorted_values else 0,
        "general_paragraph_overlap_assessment": (
            "overlap is effectively absent in most consecutive chunks"
            if pct(overlap_ge_min, pair_count) < 5
            else "overlap appears in a meaningful share of consecutive chunks"
        ),
    }


def metadata_int(metadata: Any, key: str) -> int | None:
    if not isinstance(metadata, dict):
        return None
    value = metadata.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def metadata_bool(metadata: Any, key: str) -> bool:
    if not isinstance(metadata, dict):
        return False
    value = metadata.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def summarize_truncation(chunks: list[dict[str, Any]], sample_chars: int, top_n: int) -> dict[str, Any]:
    truncated = [row for row in chunks if metadata_bool(row.get("metadata"), "section_truncated")]
    by_doc = Counter(row["doc_id"] for row in truncated)

    section_outliers = sorted(
        [
            {
                "chunk_id": row.get("chunk_id"),
                "doc_id": row.get("doc_id"),
                "title": row.get("title"),
                "source_url": row.get("source_url"),
                "section_chunk_count": metadata_int(row.get("metadata"), "section_chunk_count"),
                "section_type": row.get("section_type"),
                "sample": excerpt(row.get("content"), sample_chars),
            }
            for row in chunks
            if metadata_int(row.get("metadata"), "section_chunk_count") is not None
        ],
        key=lambda item: item.get("section_chunk_count") or 0,
        reverse=True,
    )

    doc_lookup = {row["doc_id"]: row for row in chunks}
    truncated_docs = [
        {
            "doc_id": doc_id,
            "truncated_chunks": count,
            "title": doc_lookup.get(doc_id, {}).get("title"),
            "source_url": doc_lookup.get(doc_id, {}).get("source_url"),
            "source_type": doc_lookup.get(doc_id, {}).get("source_type"),
            "page_kind": doc_lookup.get(doc_id, {}).get("page_kind"),
        }
        for doc_id, count in by_doc.most_common(top_n)
    ]
    truncated_documents = [
        {
            "doc_id": doc_id,
            "truncated_chunks": count,
            "title": doc_lookup.get(doc_id, {}).get("title"),
            "source_url": doc_lookup.get(doc_id, {}).get("source_url"),
            "source_type": doc_lookup.get(doc_id, {}).get("source_type"),
            "page_kind": doc_lookup.get(doc_id, {}).get("page_kind"),
        }
        for doc_id, count in by_doc.most_common()
    ]

    long_candidates_counter: Counter[str] = Counter()
    for row in chunks:
        title = row.get("title") or ""
        text = row.get("content") or ""
        if any(keyword in title or keyword in text[:800] for keyword in LONG_DOC_KEYWORDS):
            long_candidates_counter[row["doc_id"]] += 1

    long_candidates = []
    for doc_id, count in long_candidates_counter.most_common(top_n):
        row = doc_lookup.get(doc_id, {})
        long_candidates.append(
            {
                "doc_id": doc_id,
                "matched_chunks": count,
                "title": row.get("title"),
                "source_url": row.get("source_url"),
                "source_type": row.get("source_type"),
                "page_kind": row.get("page_kind"),
            }
        )

    return {
        "section_truncated_chunks": len(truncated),
        "section_truncated_documents": len(by_doc),
        "truncated_documents": truncated_documents,
        "truncated_documents_top": truncated_docs,
        "section_chunk_count_outliers_top": section_outliers[:top_n],
        "long_attachment_rule_notice_candidates_top": long_candidates,
        "split_design_note": (
            "Long attachments, regulations, admissions guides, bids, and scholarship notices should be "
            "split before generic paragraph chunking by heading/article/table/table-of-contents anchors. "
            "This rollout only reports candidates and keeps existing data read-only."
        ),
    }


def summarize_embeddings(loader: PGVectorLoader) -> dict[str, Any]:
    coverage = fetch_rows(
        loader,
        """
        SELECT
            count(*) FILTER (WHERE e.chunk_id IS NOT NULL) AS embedded_chunks,
            count(*) FILTER (WHERE e.chunk_id IS NULL) AS missing_embeddings,
            count(*) AS total_chunks
        FROM chunks c
        LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id;
        """,
    )[0]
    models = fetch_rows(
        loader,
        """
        SELECT model_name, count(*) AS chunks
        FROM chunk_embeddings
        GROUP BY model_name
        ORDER BY chunks DESC, model_name;
        """,
    )
    total = int(coverage["total_chunks"] or 0)
    embedded = int(coverage["embedded_chunks"] or 0)
    return {
        "embedded_chunks": embedded,
        "missing_embeddings": int(coverage["missing_embeddings"] or 0),
        "total_chunks": total,
        "coverage_percent": pct(embedded, total),
        "models": models,
    }


def build_report(loader: PGVectorLoader, args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_dataset(loader)
    clean_contents = dataset["clean_contents"]
    chunks = dataset["chunks"]

    table_counts = fetch_rows(
        loader,
        """
        SELECT 'documents' AS table_name, count(*) AS rows FROM documents
        UNION ALL SELECT 'document_contents', count(*) FROM document_contents
        UNION ALL SELECT 'chunks', count(*) FROM chunks
        UNION ALL SELECT 'chunk_embeddings', count(*) FROM chunk_embeddings
        UNION ALL SELECT 'document_assets', count(*) FROM document_assets
        ORDER BY table_name;
        """,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "parameters": {
            "top_n": args.top_n,
            "sample_chars": args.sample_chars,
            "short_doc_chars": args.short_doc_chars,
            "overlap_min_chars": OVERLAP_MIN_CHARS,
        },
        "table_counts": table_counts,
        "document_contents_clean_quality": summarize_clean_quality(
            clean_contents,
            dataset["raw_clean_pairs"],
            args.sample_chars,
            args.short_doc_chars,
            args.top_n,
        ),
        "ui_preview_noise": summarize_ui_preview_noise(clean_contents, args.sample_chars, args.top_n),
        "duplicates": summarize_duplicates(clean_contents, chunks, args.sample_chars, args.top_n),
        "short_chunk_noise": summarize_short_chunks(chunks, args.sample_chars, args.top_n),
        "overlap": summarize_overlap(chunks),
        "truncation": summarize_truncation(chunks, args.sample_chars, args.top_n),
        "embeddings": summarize_embeddings(loader),
    }


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        values = []
        for column in columns:
            value = row.get(column, "")
            value = str(value).replace("\n", " ").replace("|", "\\|")
            values.append(value)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def build_markdown(report: dict[str, Any]) -> str:
    clean = report["document_contents_clean_quality"]
    dup = report["duplicates"]
    short = report["short_chunk_noise"]
    overlap = report["overlap"]
    truncation = report["truncation"]
    embeddings = report["embeddings"]

    lines = [
        "# Crawl Quality Diagnostics",
        "",
        f"- Generated at: `{report['generated_at']}`",
        "- Database mode: read-only queries only",
        "",
        "## Summary",
        "",
        markdown_table(report["table_counts"], ["table_name", "rows"]),
        "",
        "## document_contents.clean Quality",
        "",
        f"- Clean rows: {clean['total_clean_rows']}",
        f"- Clean documents: {clean['total_clean_documents']}",
        (
            "- Raw/clean almost identical documents: "
            f"{clean['raw_clean_almost_identical_documents']} "
            f"({clean['raw_clean_almost_identical_ratio_percent']}%)"
        ),
        (
            "- Empty or short clean documents: "
            f"{clean['empty_or_short_clean_documents']} "
            f"(threshold: < {clean['short_doc_threshold_chars']} chars)"
        ),
        "",
        "### Residual Noise",
        "",
    ]
    for name, item in clean["residual_noise"].items():
        lines.append(f"- `{name}`: {item['documents']} docs / {item['rows']} rows")

    lines.extend(["", "## UI/Preview Noise", ""])
    for name, item in report["ui_preview_noise"].items():
        lines.append(f"- `{name}`: {item['documents']} docs / {item['rows']} rows")

    lines.extend(
        [
            "",
            "## Duplicates",
            "",
            f"- Duplicate normalized clean hash groups: {dup['duplicate_clean_hash_groups']}",
            f"- Duplicate clean document rows in duplicate groups: {dup['duplicate_clean_documents']}",
            f"- Duplicate normalized chunk hash groups: {dup['duplicate_chunk_hash_groups']}",
            f"- Duplicate chunk rows in duplicate groups: {dup['duplicate_chunk_rows']}",
            "",
            "### Top Duplicate Chunks",
            "",
            markdown_table(
                dup["duplicate_chunk_top"],
                ["repeat_count", "distinct_documents", "sample_doc_id", "sample_chunk_id", "title", "sample"],
            ),
            "",
            "## Short Chunk Noise",
            "",
            f"- Chunks <= 50 chars: {short['chunks_lte_50']}",
            f"- Chunks <= 100 chars: {short['chunks_lte_100']}",
            f"- Chunks <= 150 chars: {short['chunks_lte_150']}",
            "",
            "### Short Chunk Samples",
            "",
            markdown_table(short["samples_lte_100"], ["chunk_id", "content_length", "title", "sample"]),
            "",
            "## Overlap",
            "",
            f"- Consecutive chunk pairs in same document: {overlap['consecutive_pairs']}",
            f"- Pairs with any exact overlap: {overlap['pairs_with_any_exact_overlap']}",
            f"- Pairs with overlap >= {OVERLAP_MIN_CHARS}: {overlap[f'pairs_with_overlap_gte_{OVERLAP_MIN_CHARS}']}",
            f"- Ratio >= {OVERLAP_MIN_CHARS}: {overlap[f'overlap_gte_{OVERLAP_MIN_CHARS}_ratio_percent']}%",
            f"- Assessment: {overlap['general_paragraph_overlap_assessment']}",
            "",
            "## Truncation",
            "",
            f"- section_truncated=true chunks: {truncation['section_truncated_chunks']}",
            f"- section_truncated documents: {truncation['section_truncated_documents']}",
            f"- Split design note: {truncation['split_design_note']}",
            "",
            "### Truncated Documents Top",
            "",
            markdown_table(
                truncation["truncated_documents_top"],
                ["truncated_chunks", "doc_id", "title", "source_url"],
            ),
            "",
            "### Long Document Candidates",
            "",
            markdown_table(
                truncation["long_attachment_rule_notice_candidates_top"],
                ["matched_chunks", "doc_id", "title", "source_url"],
            ),
            "",
            "### Section Chunk Count Outliers",
            "",
            markdown_table(
                truncation["section_chunk_count_outliers_top"],
                ["section_chunk_count", "chunk_id", "title", "source_url", "sample"],
            ),
            "",
            "## Embeddings",
            "",
            f"- Embedded chunks: {embeddings['embedded_chunks']}",
            f"- Missing embeddings: {embeddings['missing_embeddings']}",
            f"- Coverage: {embeddings['coverage_percent']}%",
        ]
    )
    return "\n".join(lines) + "\n"


def print_console_summary(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    clean = report["document_contents_clean_quality"]
    dup = report["duplicates"]
    short = report["short_chunk_noise"]
    overlap = report["overlap"]
    truncation = report["truncation"]
    embeddings = report["embeddings"]

    print("== Crawl quality diagnostics ==")
    for row in report["table_counts"]:
        print(f"{row['table_name']}: {row['rows']}")
    print("")
    print(f"clean documents: {clean['total_clean_documents']}")
    print(
        "raw/clean almost identical: "
        f"{clean['raw_clean_almost_identical_documents']} "
        f"({clean['raw_clean_almost_identical_ratio_percent']}%)"
    )
    print(f"empty/short clean documents: {clean['empty_or_short_clean_documents']}")
    print(f"duplicate clean hash groups: {dup['duplicate_clean_hash_groups']}")
    print(f"duplicate chunk hash groups: {dup['duplicate_chunk_hash_groups']}")
    print(f"chunks <= 50/100/150 chars: {short['chunks_lte_50']} / {short['chunks_lte_100']} / {short['chunks_lte_150']}")
    print(
        "overlap pairs >= "
        f"{OVERLAP_MIN_CHARS}: {overlap[f'pairs_with_overlap_gte_{OVERLAP_MIN_CHARS}']} "
        f"of {overlap['consecutive_pairs']} "
        f"({overlap[f'overlap_gte_{OVERLAP_MIN_CHARS}_ratio_percent']}%)"
    )
    print(f"section_truncated chunks/documents: {truncation['section_truncated_chunks']} / {truncation['section_truncated_documents']}")
    print(f"embedding coverage: {embeddings['coverage_percent']}% ({embeddings['embedded_chunks']}/{embeddings['total_chunks']})")
    print("")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    loader = PGVectorLoader()
    try:
        loader.conn.set_session(readonly=True, autocommit=True)
        report = build_report(loader, args)
    finally:
        loader.close()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"crawl_quality_{timestamp}.json"
    markdown_path = output_dir / f"crawl_quality_{timestamp}.md"

    json_path.write_text(json.dumps(report, ensure_ascii=False, default=json_default, indent=2), encoding="utf-8")
    markdown_path.write_text(build_markdown(report), encoding="utf-8")

    print_console_summary(report, json_path, markdown_path)


if __name__ == "__main__":
    main()
