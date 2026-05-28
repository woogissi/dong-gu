from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "reports"
JSON_PATH = REPORT_DIR / "rag_log_failure_report.json"
MD_PATH = REPORT_DIR / "rag_log_failure_report.md"

TARGET_TABLES = [
    "query_logs",
    "response_logs",
    "retrieval_logs",
    "retrieval_selected_chunks",
    "documents",
    "document_contents",
    "chunks",
    "chunk_embeddings",
    "crawl_logs",
]

GENERIC_TERMS = {
    "정보",
    "알려줘",
    "뭐",
    "무엇",
    "어디",
    "어떻게",
    "동의대",
    "동의대학교",
    "안내",
    "확인",
    "관련",
    "내용",
    "질문",
    "있어",
    "있는",
    "이름",
}

NEGATIVE_PATTERNS = [
    "찾을 수 없",
    "확인할 수 없",
    "제공된 문서",
    "문서에서",
    "정보가 없습니다",
    "근거가 부족",
    "알 수 없습니다",
]

NOISE_PATTERNS = [
    "HOME",
    "공유",
    "SNS",
    "More",
    "메뉴",
    "게시판",
    "로그인",
    "사이트맵",
    "COPYRIGHT",
    "facebook",
    "instagram",
]


def load_env() -> None:
    env_path = ROOT / ".env"
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def connect() -> psycopg2.extensions.connection:
    load_env()
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)


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


def fetch_all(cur: psycopg2.extensions.cursor, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [clean(dict(row)) for row in cur.fetchall()]


def fetch_one(cur: psycopg2.extensions.cursor, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    rows = fetch_all(cur, sql, params)
    return rows[0] if rows else {}


def schema_summary(cur: psycopg2.extensions.cursor) -> dict[str, Any]:
    columns = fetch_all(
        cur,
        """
        SELECT table_name, column_name, data_type, udt_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position;
        """,
        (TARGET_TABLES,),
    )
    counts: dict[str, Any] = {}
    for table in TARGET_TABLES:
        counts[table] = fetch_one(
            cur,
            f"SELECT count(*)::int AS rows, min(created_at) AS first_at, max(created_at) AS last_at FROM public.{table};",
        )
    return {"columns": columns, "counts": counts}


def text_terms(*values: Any) -> list[str]:
    raw: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, list):
            raw.extend(str(item) for item in value if item)
        elif isinstance(value, dict):
            raw.extend(str(item) for item in value.values() if isinstance(item, str))
        else:
            raw.extend(re.findall(r"[0-9A-Za-z가-힣]{2,}", str(value)))
    terms: list[str] = []
    seen: set[str] = set()
    for term in raw:
        if term in GENERIC_TERMS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms[:10]


def score_lookup(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    branches = metadata.get("retrieval_branch_candidates") or {}
    if isinstance(branches, dict):
        for branch_name, rows in branches.items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or not row.get("chunk_id"):
                    continue
                item = lookup.setdefault(str(row["chunk_id"]), {})
                item[f"{branch_name}_rank"] = row.get("rank")
                item[f"{branch_name}_score"] = row.get("score")
                item["lexical_score"] = row.get("lexical_score", item.get("lexical_score"))
                item["vector_score"] = row.get("vector_score", item.get("vector_score"))
                item["final_score"] = row.get("final_score", item.get("final_score"))
    for row in metadata.get("rerank_comparison") or []:
        if isinstance(row, dict) and row.get("chunk_id"):
            item = lookup.setdefault(str(row["chunk_id"]), {})
            item["rank_before"] = row.get("rank_before")
            item["rank_after"] = row.get("rank_after")
            item["rank_delta"] = row.get("rank_delta")
            item["rerank_score"] = row.get("rerank_score")
            item["selected_in_rerank_log"] = row.get("selected")
    return lookup


def fetch_cases(cur: psycopg2.extensions.cursor, limit: int = 70) -> list[dict[str, Any]]:
    rows = fetch_all(
        cur,
        """
        WITH latest_retrieval AS (
            SELECT DISTINCT ON (request_id) *
            FROM retrieval_logs
            ORDER BY request_id, created_at DESC, id DESC
        ),
        latest_response AS (
            SELECT DISTINCT ON (request_id) *
            FROM response_logs
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
                        'page_kind', d.page_kind,
                        'department', d.department,
                        'content_type', dc.content_type,
                        'score', rsc.score,
                        'rerank_score', rsc.rerank_score,
                        'metadata', rsc.metadata,
                        'content_preview', left(coalesce(c.content, rsc.content_snapshot), 520)
                    )
                    ORDER BY rsc.rank
                ) AS selected_chunks
            FROM retrieval_selected_chunks rsc
            LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
            LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id)
            LEFT JOIN document_contents dc ON dc.id = c.content_id
            GROUP BY rsc.retrieval_log_id
        )
        SELECT
            q.id AS query_id,
            q.request_id,
            NULL::text AS session_id,
            q.created_at,
            q.question,
            q.intent_type,
            r.answer_text,
            r.success AS response_success,
            r.error_message AS response_error,
            lr.id AS retrieval_log_id,
            lr.normalized_query,
            lr.rewritten_query,
            lr.rewritten_queries,
            lr.keywords,
            lr.entities,
            lr.filters,
            lr.category,
            lr.retrieval_strategy,
            lr.retrieval_top_k,
            lr.fallback_used,
            lr.retrieved_doc_count,
            lr.reranked_doc_count,
            lr.selected_doc_count,
            lr.success AS retrieval_success,
            lr.error_message AS retrieval_error,
            lr.metadata,
            coalesce(s.selected_chunks, '[]'::jsonb) AS selected_chunks
        FROM query_logs q
        LEFT JOIN latest_response r ON r.request_id = q.request_id
        LEFT JOIN latest_retrieval lr ON lr.request_id = q.request_id
        LEFT JOIN selected s ON s.retrieval_log_id = lr.id
        WHERE q.intent_type = 'INFO'
        ORDER BY q.created_at DESC
        LIMIT %s;
        """,
        (limit,),
    )
    for row in rows:
        lookup = score_lookup(row.get("metadata") or {})
        for chunk in row.get("selected_chunks") or []:
            if isinstance(chunk, dict):
                chunk.update(lookup.get(str(chunk.get("chunk_id")), {}))
    return rows


def db_probe(cur: psycopg2.extensions.cursor, terms: list[str]) -> list[dict[str, Any]]:
    if not terms:
        return []
    patterns = [f"%{term}%" for term in terms[:8]]
    return fetch_all(
        cur,
        """
        SELECT
            d.doc_id,
            c.chunk_id,
            d.title,
            d.source_type,
            d.page_kind,
            d.department,
            d.source_url,
            dc.content_type,
            count(*) OVER ()::int AS total_matches,
            (
                SELECT count(*)
                FROM unnest(%s::text[]) AS p(pattern)
                WHERE c.content ILIKE p.pattern OR d.title ILIKE p.pattern
            )::int AS term_hits,
            left(c.content, 360) AS content_preview
        FROM chunks c
        JOIN documents d ON d.doc_id = c.doc_id
        LEFT JOIN document_contents dc ON dc.id = c.content_id
        WHERE EXISTS (
            SELECT 1
            FROM unnest(%s::text[]) AS p(pattern)
            WHERE c.content ILIKE p.pattern OR d.title ILIKE p.pattern
        )
        ORDER BY term_hits DESC, d.published_at DESC NULLS LAST, length(c.content) DESC
        LIMIT 8;
        """,
        (patterns, patterns),
    )


def has_negative_answer(answer: str | None) -> bool:
    return any(pattern in (answer or "") for pattern in NEGATIVE_PATTERNS)


def chunk_noise(chunk: dict[str, Any]) -> bool:
    text = " ".join(str(chunk.get(key) or "") for key in ("title", "content_preview", "source_url"))
    return any(pattern.lower() in text.lower() for pattern in NOISE_PATTERNS)


def classify(case: dict[str, Any], probes: list[dict[str, Any]]) -> tuple[str, str, str]:
    metadata = case.get("metadata") or {}
    selected = [c for c in case.get("selected_chunks") or [] if isinstance(c, dict)]
    selected_chunk_ids = {str(c.get("chunk_id")) for c in selected if c.get("chunk_id")}
    selected_doc_ids = {str(c.get("doc_id")) for c in selected if c.get("doc_id")}
    probe_chunk_ids = {str(p.get("chunk_id")) for p in probes if p.get("chunk_id")}
    probe_doc_ids = {str(p.get("doc_id")) for p in probes if p.get("doc_id")}
    lookup = score_lookup(metadata)
    candidate_chunk_ids = set(lookup)
    overlap_selected = bool(selected_chunk_ids & probe_chunk_ids or selected_doc_ids & probe_doc_ids)
    overlap_candidate = bool(candidate_chunk_ids & probe_chunk_ids)
    quality = metadata.get("retrieval_quality") or {}
    query_understanding = metadata.get("query_understanding") or {}
    rewrite_quality = query_understanding.get("rewrite_quality") or {}
    filters = case.get("filters") or {}

    if case.get("retrieval_log_id") is None:
        if probes:
            return "F. intent / category / filter 문제", "INFO 로그인데 retrieval log가 없고 DB에는 후보가 있어 RAG 경로 진입/라우팅을 봐야 함", "intent/routing"
        return "A. 데이터 없음", "retrieval log도 없고 DB lexical probe도 후보를 찾지 못함", "crawl/data"
    if not probes:
        return "A. 데이터 없음", "질문/재작성/키워드로 documents/chunks lexical probe를 수행했지만 후보가 없음", "crawler coverage"
    if selected and any(chunk_noise(c) for c in selected):
        return "D. 노이즈 문서가 상위에 섞임", "selected chunk에 메뉴/공유/SNS/게시판 등 UI성 텍스트가 포함됨", "text cleaning / noise filter"
    if quality.get("duplicate_doc_ratio", 0) and quality.get("duplicate_doc_ratio", 0) >= 0.35:
        return "D. 노이즈 문서가 상위에 섞임", f"duplicate_doc_ratio={quality.get('duplicate_doc_ratio')}로 동일/유사 문서 반복 위험", "dedupe / TopK selection"
    if filters and ("학과사무실" in json.dumps(filters, ensure_ascii=False) or rewrite_quality.get("missing_protected_terms")):
        return "F. intent / category / filter 문제", f"filters={filters}, rewrite_quality={rewrite_quality}", "filter/category extraction"
    if not selected:
        return "B. 데이터는 있지만 검색 실패", "DB 후보는 있지만 selected chunk가 없음", "retrieval / selection"
    if overlap_candidate and not overlap_selected:
        return "C. 검색은 됐지만 selection/rerank 실패", "DB 후보 chunk가 retrieval/rerank 후보에는 있으나 selected chunk에는 없음", "rerank / TopK selection"
    if not overlap_selected:
        return "B. 데이터는 있지만 검색 실패", "DB 후보는 있으나 retrieval 후보/selected와 겹치지 않음", "lexical/vector query"
    if has_negative_answer(case.get("answer_text")):
        return "E. 답변 생성 단계 문제", "selected chunk에 후보 근거가 있는데 답변은 근거 부족/확인 불가 계열", "answer generation"
    top_strong = quality.get("top_strong_term_match")
    if top_strong == 0:
        return "C. 검색은 됐지만 selection/rerank 실패", "retrieval_quality.top_strong_term_match=0으로 상위 선택 chunk의 핵심어 적합도가 낮음", "rerank scoring"
    return "E. 답변 생성 단계 문제", "근거 후보와 selected chunk가 겹치므로 남은 위험은 답변 합성/근거 해석", "answer generation"


def suspicion_score(case: dict[str, Any], probes: list[dict[str, Any]]) -> int:
    metadata = case.get("metadata") or {}
    quality = metadata.get("retrieval_quality") or {}
    score = 0
    if has_negative_answer(case.get("answer_text")):
        score += 4
    if not case.get("retrieval_success") or case.get("fallback_used"):
        score += 3
    if not case.get("selected_chunks"):
        score += 3
    if probes:
        selected_doc_ids = {str(c.get("doc_id")) for c in case.get("selected_chunks") or [] if isinstance(c, dict)}
        probe_doc_ids = {str(p.get("doc_id")) for p in probes if p.get("doc_id")}
        if selected_doc_ids.isdisjoint(probe_doc_ids):
            score += 3
    if quality.get("top_strong_term_match") == 0:
        score += 2
    if quality.get("duplicate_doc_ratio", 0) >= 0.35:
        score += 2
    if any(chunk_noise(c) for c in case.get("selected_chunks") or [] if isinstance(c, dict)):
        score += 2
    if case.get("filters"):
        score += 1
    return score


def compact_case(case: dict[str, Any], probes: list[dict[str, Any]]) -> dict[str, Any]:
    issue_type, reason, fix_area = classify(case, probes)
    metadata = case.get("metadata") or {}
    candidates = metadata.get("rerank_comparison") or []
    branch = metadata.get("retrieval_branch_candidates") or {}
    retrieved_docs = []
    for name in ("lexical", "vector"):
        for item in (branch.get(name) or [])[:5]:
            if isinstance(item, dict):
                retrieved_docs.append(
                    {
                        "branch": name,
                        "rank": item.get("rank"),
                        "title": item.get("title"),
                        "doc_id": item.get("doc_id"),
                        "chunk_id": item.get("chunk_id"),
                        "source_type": item.get("source_type"),
                        "lexical_score": item.get("lexical_score"),
                        "vector_score": item.get("vector_score"),
                        "final_score": item.get("final_score"),
                    }
                )
    return {
        "query_id": case.get("query_id"),
        "request_id": case.get("request_id"),
        "session_id": case.get("session_id"),
        "created_at": case.get("created_at"),
        "question": case.get("question"),
        "answer": case.get("answer_text"),
        "intent": case.get("intent_type"),
        "category": case.get("category"),
        "filters": case.get("filters"),
        "rewritten_query": case.get("rewritten_query"),
        "rewritten_queries": case.get("rewritten_queries"),
        "keywords": case.get("keywords"),
        "retrieval": {
            "strategy": case.get("retrieval_strategy"),
            "retrieved_doc_count": case.get("retrieved_doc_count"),
            "reranked_doc_count": case.get("reranked_doc_count"),
            "selected_doc_count": case.get("selected_doc_count"),
            "fallback_used": case.get("fallback_used"),
            "success": case.get("retrieval_success"),
            "quality": metadata.get("retrieval_quality"),
        },
        "retrieved_documents_top": retrieved_docs,
        "rerank_top": candidates[:8] if isinstance(candidates, list) else [],
        "selected_chunks": case.get("selected_chunks"),
        "db_evidence_probe": probes,
        "issue_type": issue_type,
        "reason": reason,
        "fix_area": fix_area,
        "suspicion_score": suspicion_score(case, probes),
    }


def truncate(text: Any, limit: int) -> str:
    value = str(text or "").replace("\r", " ").replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 3] + "..."


def write_markdown(report: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# RAG 로그 실패 분석 리포트")
    lines.append("")
    lines.append(f"- 생성 시각: {report['generated_at']}")
    lines.append(f"- 분석 범위: 최근 INFO query {report['analyzed_recent_info_queries']}개 중 실패 가능성 상위 {len(report['failure_cases'])}개")
    lines.append("- DB 변경 없음: `.env`의 Postgres 접속으로 읽기 전용 조회만 수행")
    lines.append("")
    lines.append("## 스키마 확인")
    for table, info in report["schema"]["counts"].items():
        lines.append(f"- {table}: rows={info.get('rows')}, first={info.get('first_at')}, last={info.get('last_at')}")
    lines.append("")
    lines.append("## 전체 관찰 요약")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## 대표 실패 케이스")
    for idx, case in enumerate(report["failure_cases"], start=1):
        lines.append("")
        lines.append(f"### [Case {idx}] query_id={case['query_id']} / request_id={case['request_id']}")
        lines.append(f"- created_at: {case['created_at']}")
        lines.append(f"- 질문: {case['question']}")
        lines.append(f"- 답변: {truncate(case['answer'], 700)}")
        lines.append(f"- 문제 유형: {case['issue_type']}")
        lines.append(f"- intent/category/filters/rewrite: {case['intent']} / {case['category']} / {case['filters']} / {case['rewritten_query']}")
        lines.append(f"- 원인 분석: {case['reason']}")
        lines.append(f"- 수정 필요 지점: {case['fix_area']}")
        lines.append("- 검색된 문서:")
        for doc in case["retrieved_documents_top"][:6]:
            lines.append(
                f"  - {doc.get('branch')}#{doc.get('rank')} {truncate(doc.get('title'), 90)} "
                f"doc={doc.get('doc_id')} chunk={doc.get('chunk_id')} "
                f"lex={doc.get('lexical_score')} vec={doc.get('vector_score')} final={doc.get('final_score')}"
            )
        lines.append("- 선택된 chunk:")
        for chunk in (case.get("selected_chunks") or [])[:5]:
            lines.append(
                f"  - rank={chunk.get('rank')} title={truncate(chunk.get('title'), 90)} "
                f"source_type={chunk.get('source_type')} content_type={chunk.get('content_type')} "
                f"score={chunk.get('score')} rerank={chunk.get('rerank_score')} "
                f"lex={chunk.get('lexical_score')} vec={chunk.get('vector_score')} final={chunk.get('final_score')}"
            )
            lines.append(f"    source_url={chunk.get('source_url')}")
            lines.append(f"    원문 일부: {truncate(chunk.get('content_preview'), 300)}")
        lines.append("- 정답 후보 문서 존재 여부:")
        for probe in case["db_evidence_probe"][:5]:
            lines.append(
                f"  - hits={probe.get('term_hits')} title={truncate(probe.get('title'), 90)} "
                f"doc={probe.get('doc_id')} chunk={probe.get('chunk_id')} "
                f"source_type={probe.get('source_type')} content_type={probe.get('content_type')}"
            )
            lines.append(f"    source_url={probe.get('source_url')}")
    lines.append("")
    lines.append("## 파이프라인별 진단")
    for item in report["pipeline_diagnosis"]:
        lines.append("")
        lines.append(f"### {item['stage']}")
        lines.append(f"- 현재 관찰된 문제: {item['observed_problem']}")
        lines.append(f"- 근거 로그: {item['evidence']}")
        lines.append(f"- 재현 query id: {', '.join(map(str, item['example_query_ids']))}")
        lines.append(f"- 수정 방향: {item['fix_direction']}")
        lines.append(f"- 우선순위: {item['priority']}")
        lines.append(f"- 주의사항: {item['caution']}")
    lines.append("")
    lines.append("## 수정 계획")
    for step in report["fix_plan"]:
        lines.append(f"- {step}")
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pipeline_diagnosis(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_type: dict[str, list[int]] = {}
    for case in cases:
        by_type.setdefault(case["issue_type"], []).append(case["query_id"])
    return [
        {
            "stage": "query preprocessing",
            "observed_problem": "숫자/짧은 질의에서 일반어가 많이 남아 위치/건물 질의가 넓은 문서군으로 확산됨",
            "evidence": "keywords, rewritten_queries, retrieval_quality.top_strong_term_match",
            "example_query_ids": [c["query_id"] for c in cases if "건물" in c["question"] or "정보공학관" in c["question"]][:5],
            "fix_direction": "숫자+건물, 건물명+층, 학과+이수표 같은 질의 패턴을 별도 엔티티로 보호",
            "priority": "P1",
            "caution": "일반 공지 검색까지 과하게 좁아지지 않도록 패턴별로만 적용",
        },
        {
            "stage": "intent classification",
            "observed_problem": "최근 INFO 로그는 대부분 RAG로 진입하지만, DB 후보가 있는데 retrieval_log가 없을 가능성은 별도 감시 필요",
            "evidence": "query_logs.intent_type, retrieval_logs 존재 여부",
            "example_query_ids": by_type.get("F. intent / category / filter 문제", [])[:5],
            "fix_direction": "INFO인데 retrieval_log가 없는 케이스를 경고 지표로 추가",
            "priority": "P2",
            "caution": "욕설/일반대화 우회 경로와 혼동하지 말 것",
        },
        {
            "stage": "query rewriting",
            "observed_problem": "protected term 누락 또는 형태 변형이 보임",
            "evidence": "metadata.query_understanding.rewrite_quality.missing_protected_terms",
            "example_query_ids": [c["query_id"] for c in cases if (c["retrieval"].get("quality") or {}).get("top_strong_term_match") == 0][:5],
            "fix_direction": "protected_terms가 rewrite/query_variants 전체에 보존되도록 테스트 추가",
            "priority": "P1",
            "caution": "동의대 같은 범용어는 보호 대상에서 제외",
        },
        {
            "stage": "keyword extraction",
            "observed_problem": "핵심어보다 범용어가 top keyword에 섞여 lexical branch가 넓어짐",
            "evidence": "retrieval_logs.keywords, retrieval_branch_candidates.lexical",
            "example_query_ids": [c["query_id"] for c in cases if c["issue_type"].startswith("B.")][:5],
            "fix_direction": "질문별 강한 명사/숫자 토큰을 strong_terms로 분리하고 점수 로그에 남김",
            "priority": "P1",
            "caution": "한국어 복합명사 분해와 원형 보존을 같이 유지",
        },
        {
            "stage": "filter/category extraction",
            "observed_problem": "department filter에 `학과사무실` 같은 조직명이 들어가 검색 범위를 왜곡하는 사례가 있음",
            "evidence": "retrieval_logs.filters, metadata.query_understanding.extracted_entities.department",
            "example_query_ids": by_type.get("F. intent / category / filter 문제", [])[:5],
            "fix_direction": "department/site/page_type 필터는 실제 corpus facet 값과 매칭될 때만 적용",
            "priority": "P1",
            "caution": "필터 적용 전/후 후보 수를 로그로 남겨야 회귀를 잡을 수 있음",
        },
        {
            "stage": "lexical search",
            "observed_problem": "DB에는 lexical probe 후보가 있는데 retrieval 후보와 겹치지 않는 케이스가 있음",
            "evidence": "db_evidence_probe vs retrieval_branch_candidates.lexical",
            "example_query_ids": [c["query_id"] for c in cases if c["issue_type"].startswith("B.")][:5],
            "fix_direction": "strong_terms 필수 포함 옵션과 title/section_title 가중치 재조정",
            "priority": "P1",
            "caution": "부분일치만 강화하면 UI/메뉴 노이즈가 같이 올라올 수 있음",
        },
        {
            "stage": "vector search",
            "observed_problem": "짧은 시설/건물 질의에서 의미적으로 가까운 학과/공지 문서가 섞임",
            "evidence": "retrieval_branch_candidates.vector vector_score",
            "example_query_ids": [c["query_id"] for c in cases if "정보공학관" in c["question"]][:5],
            "fix_direction": "시설/위치 질의는 lexical/title exact signal을 vector보다 우선",
            "priority": "P2",
            "caution": "일반 의미 질의에서는 vector branch 비중을 유지",
        },
        {
            "stage": "hybrid merge",
            "observed_problem": "lexical/vector 점수의 final_score가 rerank 이전 후보 적합성을 충분히 보장하지 못함",
            "evidence": "retrieval_branch_candidates final_score, rerank_comparison rank_before",
            "example_query_ids": [c["query_id"] for c in cases if c["retrieval"]["retrieved_doc_count"]][:5],
            "fix_direction": "query family별 fusion weight와 branch별 minimum evidence gate 적용",
            "priority": "P2",
            "caution": "가중치 조정 전후 20개 대표 질의 회귀셋 필요",
        },
        {
            "stage": "rerank",
            "observed_problem": "후보에는 있으나 selected에서 밀리는 C 유형이 확인됨",
            "evidence": "rerank_comparison selected/rank_after/rerank_score",
            "example_query_ids": by_type.get("C. 검색은 됐지만 selection/rerank 실패", [])[:5],
            "fix_direction": "rerank_signals에 strong_term_match와 exact heading match 하한 조건 추가",
            "priority": "P1",
            "caution": "reranker가 긴 첨부문서의 반복어에 끌리지 않게 attachment_noise 유지",
        },
        {
            "stage": "TopK selection",
            "observed_problem": "duplicate_doc_ratio가 높은 케이스에서 반복 chunk가 context를 잠식함",
            "evidence": "retrieval_quality.duplicate_doc_ratio, selected_chunks doc_id",
            "example_query_ids": by_type.get("D. 노이즈 문서가 상위에 섞임", [])[:5],
            "fix_direction": "max_chunks_per_doc, near-duplicate content hash, source diversity를 selection gate로 적용",
            "priority": "P1",
            "caution": "한 문서 내 표/본문이 모두 필요한 공지형 답변은 예외 필요",
        },
        {
            "stage": "context formatting",
            "observed_problem": "selected chunk 원문에 제목/본문 경계와 출처가 섞여 있어 LLM이 근거를 구분하기 어려운 사례가 있음",
            "evidence": "retrieval_logs.context, selected_chunks.content_preview",
            "example_query_ids": [c["query_id"] for c in cases if c["selected_chunks"]][:5],
            "fix_direction": "chunk별 title/source_url/content_type/score를 명시한 구조화 context로 정리",
            "priority": "P2",
            "caution": "프롬프트 토큰을 늘리지 않도록 chunk 수와 preview 길이 제한",
        },
        {
            "stage": "answer generation",
            "observed_problem": "근거 후보가 선택됐는데 답변이 부정확하거나 근거 부족형으로 나오는 E 유형이 있음",
            "evidence": "selected_chunks vs response_logs.answer_text",
            "example_query_ids": by_type.get("E. 답변 생성 단계 문제", [])[:5],
            "fix_direction": "답변 전 evidence sufficiency/self-check와 인용 강제 규칙 추가",
            "priority": "P2",
            "caution": "근거 없음일 때는 억지 답변을 막는 현재 안전장치 유지",
        },
        {
            "stage": "citation/source mapping",
            "observed_problem": "selected chunk에는 source_url이 있으나 답변이 어떤 근거에서 왔는지 추적성이 약함",
            "evidence": "retrieval_selected_chunks.source_snapshot/documents.source_url",
            "example_query_ids": [c["query_id"] for c in cases if c["selected_chunks"]][:5],
            "fix_direction": "answer에 사용된 chunk_id/source_url을 response metadata로 별도 저장",
            "priority": "P3",
            "caution": "사용자 노출 citation과 내부 디버그 citation을 분리",
        },
    ]


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SET statement_timeout = '45s';")
        schema = schema_summary(cur)
        raw_cases = fetch_cases(cur, 220)
        compacted = []
        for case in raw_cases:
            terms = text_terms(
                case.get("question"),
                case.get("rewritten_query"),
                case.get("rewritten_queries"),
                case.get("keywords"),
                case.get("category"),
            )
            probes = db_probe(cur, terms)
            compacted.append(compact_case(case, probes))

    compacted.sort(key=lambda row: (row["suspicion_score"], row["query_id"]), reverse=True)
    failure_cases = compacted[:25]
    type_counts = Counter(case["issue_type"] for case in failure_cases)
    summary = {
        "failure_type_counts_top25": dict(type_counts),
        "negative_answer_cases_top25": sum(1 for c in failure_cases if has_negative_answer(c.get("answer"))),
        "fallback_cases_top25": sum(1 for c in failure_cases if c["retrieval"].get("fallback_used")),
        "with_db_evidence_probe_top25": sum(1 for c in failure_cases if c["db_evidence_probe"]),
    }
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "schema": schema,
        "analyzed_recent_info_queries": len(raw_cases),
        "summary": summary,
        "failure_cases": failure_cases,
        "pipeline_diagnosis": pipeline_diagnosis(failure_cases),
        "fix_plan": [
            "1차: 로그에 남은 대표 25개 query_id를 회귀셋으로 고정하고 기대 source/chunk를 수동 라벨링",
            "2차: filter/category extraction에서 corpus facet 검증과 protected term 보존 테스트 추가",
            "3차: lexical strong_terms/title/section_title 가중치와 hybrid fusion weight를 회귀셋으로 튜닝",
            "4차: rerank/TopK에 duplicate doc 제한, UI noise gate, strong_term 하한을 추가",
            "5차: context formatting과 response metadata에 사용 chunk/source_url/citation trace를 저장",
            "승인 전까지 제품 코드 수정은 하지 않음",
        ],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(report)
    print(f"WROTE {JSON_PATH}")
    print(f"WROTE {MD_PATH}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
