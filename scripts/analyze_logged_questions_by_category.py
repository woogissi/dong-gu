from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"

GENERIC_TERMS = {
    "알려줘",
    "알려",
    "궁금",
    "문의",
    "정보",
    "확인",
    "해주세요",
    "어떻게",
    "무엇",
    "있어",
    "있는",
    "관련",
    "대한",
    "동의대",
    "동의대학교",
}

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("수강/학사일정", ("수강신청", "계절학기", "학사일정", "개강", "종강", "강의시간표")),
    ("등록/장학", ("등록금", "납부", "장학", "국가장학", "학자금")),
    ("휴복학/증명", ("휴학", "복학", "증명서", "제증명", "졸업", "성적")),
    ("기숙사/학생생활", ("기숙사", "생활관", "동아리", "학생생활", "식당", "학생회")),
    ("시설/위치", ("건물", "위치", "어디", "호관", "캠퍼스", "도서관", "식당")),
    ("교통/버스", ("버스", "통학버스", "셔틀", "지하철", "교통")),
    ("입학", ("입학", "입시", "모집", "전형", "합격")),
    ("취업/채용", ("취업", "채용", "현장실습", "인턴", "커리어")),
    ("기관/인물", ("총장", "학과장", "교수", "역대", "조직")),
]

SOURCE_TYPE_LABELS = {
    "academic_notice": "학사공지",
    "academic_support": "학사지원",
    "scholarship": "장학",
    "dormitory": "기숙사",
    "institution": "기관/정적페이지",
    "notice": "일반공지",
    "department": "학과",
    "job": "취업/채용",
    "bids": "입찰",
    "external_notice": "외부공지",
    "facility": "시설",
    "library": "도서관",
    "static": "정적페이지",
}

PREFERRED_SOURCE_TYPES = {
    "department": ("department", "static"),
    "faculty": ("department", "static", "institution"),
    "course": ("academic_notice", "academic_support", "department", "academic"),
    "academic": ("academic_notice", "academic_support", "academic", "institution"),
    "tuition": ("academic_notice", "academic_support", "institution", "notice"),
    "scholarship": ("scholarship", "notice", "academic_notice"),
    "dormitory": ("dormitory",),
    "shuttle": ("notice", "institution", "static"),
    "facility": ("facility", "static", "institution", "department"),
    "cafeteria": ("facility", "static", "institution"),
    "library": ("library", "institution", "static"),
    "career": ("job", "department"),
    "person_title": ("institution", "static"),
    "club_activity": ("student_life", "institution", "static"),
}


@dataclass(frozen=True)
class EvidenceDoc:
    doc_id: str | None
    chunk_id: str | None
    title: str | None
    source_url: str | None
    source_type: str | None
    department: str | None
    term_hits: int
    content_preview: str | None


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def database_url() -> str:
    load_env()
    url = (os.getenv("DATABASE_URL") or os.getenv("CRAWLER_DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL or CRAWLER_DATABASE_URL is required.")
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    if "@postgres:" in url:
        url = url.replace("@postgres:", "@127.0.0.1:")
    return url


def clean(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    return value


def fetch_all(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [clean(dict(row)) for row in cur.fetchall()]


def normalize_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def terms_from(*values: Any) -> list[str]:
    raw: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            raw.extend(str(item) for item in value if item)
            continue
        if isinstance(value, dict):
            raw.extend(str(item) for item in value.values() if isinstance(item, (str, int)))
            continue
        raw.extend(re.findall(r"[0-9A-Za-z가-힣]{2,}", str(value)))

    seen: set[str] = set()
    terms: list[str] = []
    for term in raw:
        term = term.strip()
        if not term or term in GENERIC_TERMS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms[:12]


def category_from_case(case: dict[str, Any]) -> str:
    logged = normalize_space(case.get("category"))
    if logged:
        return logged

    metadata = case.get("metadata") or {}
    query_features = (
        metadata.get("query_understanding", {}).get("query_features", {})
        if isinstance(metadata, dict)
        else {}
    )
    family = normalize_space(query_features.get("family") if isinstance(query_features, dict) else "")
    if family:
        return family

    question = normalize_space(case.get("question"))
    for label, needles in CATEGORY_RULES:
        if any(needle in question for needle in needles):
            return label
    return "기타/미분류"


def query_cases(cur: Any, limit: int) -> list[dict[str, Any]]:
    return fetch_all(
        cur,
        """
        WITH latest_retrieval AS (
            SELECT DISTINCT ON (request_id) *
            FROM retrieval_logs
            ORDER BY request_id, created_at DESC, id DESC
        ),
        selected AS (
            SELECT
                rsc.retrieval_log_id,
                jsonb_agg(
                    jsonb_build_object(
                        'rank', rsc.rank,
                        'chunk_id', rsc.chunk_id,
                        'raw_chunk_id', rsc.raw_chunk_id,
                        'doc_id', coalesce(c.doc_id, rsc.doc_id),
                        'title', coalesce(d.title, rsc.title_snapshot),
                        'source_url', coalesce(d.source_url, rsc.source_snapshot),
                        'source_type', d.source_type,
                        'department', d.department,
                        'score', rsc.score,
                        'rerank_score', rsc.rerank_score,
                        'content_preview', left(coalesce(c.content, rsc.content_snapshot), 420)
                    )
                    ORDER BY rsc.rank
                ) AS selected_chunks
            FROM retrieval_selected_chunks rsc
            LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
            LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id)
            GROUP BY rsc.retrieval_log_id
        )
        SELECT
            q.id AS query_id,
            q.request_id,
            q.created_at,
            q.user_id,
            q.question,
            q.intent_type,
            resp.answer_text,
            resp.success AS response_success,
            resp.error_message AS response_error,
            lr.id AS retrieval_log_id,
            lr.normalized_query,
            lr.rewritten_query,
            lr.rewritten_queries,
            lr.keywords,
            lr.entities,
            lr.filters,
            lr.category,
            lr.retrieval_strategy,
            lr.fallback_used,
            lr.retrieved_doc_count,
            lr.reranked_doc_count,
            lr.selected_doc_count,
            lr.success AS retrieval_success,
            lr.error_message AS retrieval_error,
            lr.metadata,
            coalesce(s.selected_chunks, '[]'::jsonb) AS selected_chunks
        FROM query_logs q
        LEFT JOIN response_logs resp ON resp.request_id = q.request_id
        LEFT JOIN latest_retrieval lr ON lr.request_id = q.request_id
        LEFT JOIN selected s ON s.retrieval_log_id = lr.id
        WHERE q.intent_type = 'INFO'
        ORDER BY q.created_at DESC, q.id DESC
        LIMIT %s;
        """,
        (limit,),
    )


def preferred_source_types(category: str) -> tuple[str, ...]:
    if category in PREFERRED_SOURCE_TYPES:
        return PREFERRED_SOURCE_TYPES[category]
    for label, values in PREFERRED_SOURCE_TYPES.items():
        if label in category:
            return values
    return ()


def evidence_docs(cur: Any, terms: list[str], preferred_sources: tuple[str, ...], limit: int) -> list[EvidenceDoc]:
    if not terms:
        return []
    patterns = [f"%{term}%" for term in terms[:10]]
    rows = fetch_all(
        cur,
        """
        SELECT
            d.doc_id,
            c.chunk_id,
            d.title,
            d.source_url,
            d.source_type,
            d.department,
            CASE WHEN d.source_type = ANY(%s::text[]) THEN 1 ELSE 0 END AS preferred_source,
            (
                SELECT count(*)
                FROM unnest(%s::text[]) AS p(pattern)
                WHERE d.title ILIKE p.pattern
                   OR coalesce(c.section_title, '') ILIKE p.pattern
                   OR c.content ILIKE p.pattern
            )::int AS term_hits,
            left(c.content, 420) AS content_preview
        FROM chunks c
        JOIN documents d ON d.doc_id = c.doc_id
        WHERE EXISTS (
            SELECT 1
            FROM unnest(%s::text[]) AS p(pattern)
            WHERE d.title ILIKE p.pattern
               OR coalesce(c.section_title, '') ILIKE p.pattern
               OR c.content ILIKE p.pattern
        )
        ORDER BY preferred_source DESC, term_hits DESC, d.published_at DESC NULLS LAST, length(c.content) DESC
        LIMIT %s;
        """,
        (list(preferred_sources), patterns, patterns, limit),
    )
    return [
        EvidenceDoc(
            doc_id=row.get("doc_id"),
            chunk_id=row.get("chunk_id"),
            title=row.get("title"),
            source_url=row.get("source_url"),
            source_type=row.get("source_type"),
            department=row.get("department"),
            term_hits=int(row.get("term_hits") or 0),
            content_preview=row.get("content_preview"),
        )
        for row in rows
    ]


def compact_doc(doc: EvidenceDoc | dict[str, Any]) -> dict[str, Any]:
    if isinstance(doc, EvidenceDoc):
        return {
            "doc_id": doc.doc_id,
            "chunk_id": doc.chunk_id,
            "title": doc.title,
            "source_url": doc.source_url,
            "source_type": doc.source_type,
            "source_type_label": SOURCE_TYPE_LABELS.get(str(doc.source_type), doc.source_type),
            "department": doc.department,
            "term_hits": doc.term_hits,
            "content_preview": normalize_space(doc.content_preview)[:240],
        }
    return {
        "rank": doc.get("rank"),
        "doc_id": doc.get("doc_id"),
        "chunk_id": doc.get("chunk_id"),
        "title": doc.get("title"),
        "source_url": doc.get("source_url"),
        "source_type": doc.get("source_type"),
        "source_type_label": SOURCE_TYPE_LABELS.get(str(doc.get("source_type")), doc.get("source_type")),
        "department": doc.get("department"),
        "score": doc.get("score"),
        "rerank_score": doc.get("rerank_score"),
        "content_preview": normalize_space(doc.get("content_preview"))[:240],
    }


def compare(expected: list[EvidenceDoc], selected: list[dict[str, Any]]) -> dict[str, Any]:
    expected_doc_ids = {doc.doc_id for doc in expected if doc.doc_id}
    expected_chunk_ids = {doc.chunk_id for doc in expected if doc.chunk_id}
    selected_doc_ids = {doc.get("doc_id") for doc in selected if doc.get("doc_id")}
    selected_chunk_ids = {doc.get("chunk_id") for doc in selected if doc.get("chunk_id")}
    doc_overlap = sorted(str(item) for item in (expected_doc_ids & selected_doc_ids))
    chunk_overlap = sorted(str(item) for item in (expected_chunk_ids & selected_chunk_ids))

    if chunk_overlap:
        status = "chunk_match"
    elif doc_overlap:
        status = "same_document"
    elif expected and selected:
        status = "different_document"
    elif expected and not selected:
        status = "not_retrieved"
    elif not expected and selected:
        status = "no_ground_truth_candidate"
    else:
        status = "no_evidence"

    return {
        "status": status,
        "doc_overlap": doc_overlap,
        "chunk_overlap": chunk_overlap,
        "expected_doc_ids": sorted(str(item) for item in expected_doc_ids),
        "selected_doc_ids": sorted(str(item) for item in selected_doc_ids),
    }


def analyze(limit: int, evidence_limit: int) -> dict[str, Any]:
    with psycopg2.connect(database_url(), cursor_factory=psycopg2.extras.RealDictCursor) as conn:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = '45s';")
            cases = query_cases(cur, limit)
            analyzed: list[dict[str, Any]] = []
            for case in cases:
                category = category_from_case(case)
                selected = [item for item in (case.get("selected_chunks") or []) if isinstance(item, dict)]
                terms = terms_from(case.get("question"), case.get("keywords"))
                expected = evidence_docs(cur, terms, preferred_source_types(category), evidence_limit)
                comparison = compare(expected, selected)
                analyzed.append(
                    {
                        "query_id": case.get("query_id"),
                        "request_id": str(case.get("request_id")),
                        "created_at": case.get("created_at"),
                        "question": case.get("question"),
                        "category": category,
                        "logged_category": case.get("category"),
                        "keywords": case.get("keywords"),
                        "probe_terms": terms,
                        "answer_preview": normalize_space(case.get("answer_text"))[:360],
                        "retrieval": {
                            "strategy": case.get("retrieval_strategy"),
                            "fallback_used": case.get("fallback_used"),
                            "retrieved_doc_count": case.get("retrieved_doc_count"),
                            "reranked_doc_count": case.get("reranked_doc_count"),
                            "selected_doc_count": case.get("selected_doc_count"),
                            "success": case.get("retrieval_success"),
                            "error": case.get("retrieval_error"),
                        },
                        "expected_answer_documents": [compact_doc(doc) for doc in expected],
                        "actual_selected_documents": [compact_doc(doc) for doc in selected],
                        "comparison": comparison,
                    }
                )

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in analyzed:
        by_category[case["category"]].append(case)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": {
            "intent_type": "INFO",
            "recent_query_limit": limit,
            "evidence_limit_per_query": evidence_limit,
        },
        "summary": {
            "total_questions": len(analyzed),
            "category_counts": dict(Counter(case["category"] for case in analyzed)),
            "comparison_counts": dict(Counter(case["comparison"]["status"] for case in analyzed)),
        },
        "categories": {
            category: {
                "count": len(items),
                "comparison_counts": dict(Counter(item["comparison"]["status"] for item in items)),
                "questions": items,
            }
            for category, items in sorted(by_category.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        },
    }


def md_doc_line(doc: dict[str, Any], rank: int | None = None) -> str:
    prefix = f"{rank}. " if rank else ""
    source_type = doc.get("source_type_label") or doc.get("source_type") or "-"
    title = normalize_space(doc.get("title")) or "(제목 없음)"
    doc_id = doc.get("doc_id") or "-"
    chunk_id = doc.get("chunk_id") or "-"
    hits = doc.get("term_hits")
    score = doc.get("score")
    tail = f"hits={hits}" if hits is not None else f"score={score}"
    return f"{prefix}{title} / {source_type} / doc={doc_id} / chunk={chunk_id} / {tail}"


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines: list[str] = [
        "# 질문 로그 카테고리별 정답문서 비교",
        "",
        f"- 생성 시각: {report['generated_at']}",
        f"- 분석 범위: 최근 INFO 질문 {report['summary']['total_questions']}건",
        f"- 비교 상태: {report['summary']['comparison_counts']}",
        "",
        "## 카테고리 요약",
        "",
        "| 카테고리 | 질문 수 | 비교 상태 |",
        "| --- | ---: | --- |",
    ]
    for category, info in report["categories"].items():
        lines.append(f"| {category} | {info['count']} | {info['comparison_counts']} |")

    for category, info in report["categories"].items():
        lines.extend(["", f"## {category}", ""])
        for case in info["questions"]:
            lines.extend(
                [
                    f"### query_id={case['query_id']}",
                    "",
                    f"- 질문: {normalize_space(case['question'])}",
                    f"- 키워드/탐색어: {', '.join(case['probe_terms']) or '-'}",
                    f"- 실제 검색 상태: {case['comparison']['status']}",
                    f"- 검색 로그: strategy={case['retrieval']['strategy']}, retrieved={case['retrieval']['retrieved_doc_count']}, selected={case['retrieval']['selected_doc_count']}, fallback={case['retrieval']['fallback_used']}",
                    "",
                    "정답문서 후보:",
                ]
            )
            expected = case["expected_answer_documents"][:5]
            if expected:
                for idx, doc in enumerate(expected, start=1):
                    lines.append(f"- {md_doc_line(doc, idx)}")
            else:
                lines.append("- 없음")

            lines.append("")
            lines.append("실제 검색/선택 문서:")
            actual = case["actual_selected_documents"][:5]
            if actual:
                for idx, doc in enumerate(actual, start=1):
                    lines.append(f"- {md_doc_line(doc, idx)}")
            else:
                lines.append("- 없음")

            diff = case["comparison"]
            lines.extend(
                [
                    "",
                    f"차이 분석: status={diff['status']}, doc_overlap={diff['doc_overlap']}, chunk_overlap={diff['chunk_overlap']}",
                    "",
                ]
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Classify logged INFO questions and compare expected vs selected answer documents.")
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--evidence-limit", type=int, default=8)
    parser.add_argument("--output-json", default="reports/logged_question_document_analysis.json")
    parser.add_argument("--output-md", default="reports/logged_question_document_analysis.md")
    args = parser.parse_args()

    report = analyze(limit=args.limit, evidence_limit=args.evidence_limit)
    json_path = ROOT / args.output_json
    md_path = ROOT / args.output_md
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report, md_path)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": report["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
