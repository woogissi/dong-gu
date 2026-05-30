"""
Retrieval quality audit: 대표 질문별 파이프라인 전 단계 추적 및 웹 vs DB 비교.

실행:
    docker compose run --rm rag python -m rag.ops.retrieval_quality_audit \
        --output /app/reports/retrieval_audit_YYYYMMDD.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# --------------------------------------------------------------------------- #
# 환경 설정 — DB 검색 모드 강제
# --------------------------------------------------------------------------- #
os.environ.setdefault("RAG_USE_DB", "1")
os.environ.setdefault("RETRIEVAL_MODE", "hybrid")

# --------------------------------------------------------------------------- #
# 대표 질문셋 정의
# --------------------------------------------------------------------------- #
@dataclass
class QuestionCase:
    qid: str
    query: str
    category: str
    expected_keywords: list[str]               # DB content에 있어야 할 핵심 키워드
    expected_source_types: list[str]            # 기대하는 source_type
    expected_doc_title_hints: list[str]         # 정답 문서 제목 힌트 (부분 일치)
    failure_risk: str                           # "attachment" | "duplicate" | "missing" | "noise" | "ok"
    notes: str = ""


QUESTION_CASES: list[QuestionCase] = [
    # ── 졸업 ──────────────────────────────────────────────────────────────────
    QuestionCase("Q01", "졸업 요건 어떻게 되나요", "graduation",
                 ["졸업학점", "졸업요건", "이수학점"],
                 ["academic_notice", "department", "static"],
                 ["졸업", "이수안내"],
                 "ok"),
    QuestionCase("Q02", "컴퓨터공학과 졸업학점 알려줘", "graduation",
                 ["컴퓨터공학과", "졸업학점", "전공필수"],
                 ["department", "static"],
                 ["컴퓨터공학과", "이수표"],
                 "attachment",
                 "학과 이수표 PDF 미추출 가능성"),
    # ── 수강신청 ──────────────────────────────────────────────────────────────
    QuestionCase("Q03", "2026년 1학기 수강신청 기간 알려줘", "course_registration",
                 ["수강신청", "기간", "2026"],
                 ["academic_notice", "notice"],
                 ["수강신청 안내", "2026학년도 1학기"],
                 "duplicate",
                 "동일 공지가 34개 학과에 중복 저장"),
    QuestionCase("Q04", "신입생 수강신청 어떻게 해", "course_registration",
                 ["신입생", "수강신청", "방법"],
                 ["academic_notice", "notice"],
                 ["신입생", "수강신청"],
                 "duplicate"),
    QuestionCase("Q05", "수강 정정 기간 언제야", "course_registration",
                 ["수강정정", "기간"],
                 ["academic_notice", "notice"],
                 ["수강정정"],
                 "ok"),
    # ── 장학금 ────────────────────────────────────────────────────────────────
    QuestionCase("Q06", "국가장학금 신청 기간 알려줘", "scholarship",
                 ["국가장학금", "신청기간", "한국장학재단"],
                 ["scholarship", "academic_notice", "notice"],
                 ["국가장학금"],
                 "ok"),
    QuestionCase("Q07", "성적우수장학금 선발 기준 알려줘", "scholarship",
                 ["성적우수장학금", "선발기준", "평점"],
                 ["scholarship"],
                 ["성적우수장학금"],
                 "attachment",
                 "HWP 첨부파일에 선발기준 포함 가능"),
    QuestionCase("Q08", "형제장학금 신청 방법", "scholarship",
                 ["형제장학금", "신청", "기간"],
                 ["scholarship", "department"],
                 ["형제장학금"],
                 "duplicate",
                 "34개 학과에 동일 공지 중복"),
    QuestionCase("Q09", "기초생활수급자 장학금 있나요", "scholarship",
                 ["기초생활", "장학금", "수급자"],
                 ["scholarship"],
                 ["기초생활", "희망장학"],
                 "attachment"),
    # ── 계절학기 ──────────────────────────────────────────────────────────────
    QuestionCase("Q10", "2026년 하계 계절수업 신청 기간", "seasonal_course",
                 ["하계", "계절수업", "신청", "2026"],
                 ["academic_notice"],
                 ["하계 계절수업", "계절수업 안내"],
                 "attachment",
                 "안내문 HWP 첨부 미추출 가능"),
    QuestionCase("Q11", "계절학기 수강료 얼마야", "seasonal_course",
                 ["계절수업", "수강료", "등록금"],
                 ["academic_notice"],
                 ["계절수업", "수강료"],
                 "attachment"),
    # ── 학사 행정 ─────────────────────────────────────────────────────────────
    QuestionCase("Q12", "휴학 신청 방법 알려줘", "academic_admin",
                 ["휴학", "신청", "방법", "기간"],
                 ["academic_notice", "static"],
                 ["휴학"],
                 "ok"),
    QuestionCase("Q13", "복학 신청 기간 언제야", "academic_admin",
                 ["복학", "신청", "기간"],
                 ["academic_notice"],
                 ["복학"],
                 "ok"),
    QuestionCase("Q14", "전과 신청 방법", "academic_admin",
                 ["전과", "신청", "방법"],
                 ["academic_notice", "static"],
                 ["전과"],
                 "ok"),
    # ── 다전공 ────────────────────────────────────────────────────────────────
    QuestionCase("Q15", "다전공 신청 어떻게 해", "academic_admin",
                 ["다전공", "신청", "방법"],
                 ["advising", "academic_notice"],
                 ["다전공 안내", "학생설계전공"],
                 "attachment",
                 "다전공 가이드 PDF 316청크 section_truncated"),
    QuestionCase("Q16", "이중전공 이수학점 얼마야", "academic_admin",
                 ["이중전공", "이수학점"],
                 ["advising", "academic_notice", "static"],
                 ["이중전공", "다전공"],
                 "attachment"),
    # ── 증명서 ────────────────────────────────────────────────────────────────
    QuestionCase("Q17", "재학증명서 어디서 발급해", "certificate",
                 ["재학증명서", "발급", "방법"],
                 ["static", "academic_notice"],
                 ["증명서", "발급"],
                 "ok"),
    # ── 시설/위치 ─────────────────────────────────────────────────────────────
    QuestionCase("Q18", "지천관 위치 어디야", "building_location",
                 ["지천관", "위치"],
                 ["institution", "static"],
                 ["지천관", "캠퍼스맵"],
                 "missing",
                 "static 페이지에 위치 정보가 있는지 불확실"),
    QuestionCase("Q19", "학생식당 운영시간", "welfare_facility",
                 ["학생식당", "운영시간"],
                 ["institution", "static"],
                 ["학생식당", "복지문화시설"],
                 "noise",
                 "짧은 noise chunk가 retrieval 상위 등장"),
    QuestionCase("Q20", "도서관 운영시간", "library",
                 ["도서관", "운영시간"],
                 ["static", "institution"],
                 ["도서관"],
                 "ok"),
    # ── 기숙사 ────────────────────────────────────────────────────────────────
    QuestionCase("Q21", "기숙사 신청 방법 알려줘", "dormitory",
                 ["기숙사", "신청", "방법"],
                 ["dormitory", "notice"],
                 ["기숙사", "생활관"],
                 "ok"),
    QuestionCase("Q22", "기숙사 비용 얼마야", "dormitory",
                 ["기숙사", "비용", "생활관비"],
                 ["dormitory"],
                 ["기숙사", "생활관"],
                 "attachment"),
    # ── 등록금 ────────────────────────────────────────────────────────────────
    QuestionCase("Q23", "2026년 등록금 납부 기간 알려줘", "tuition",
                 ["등록금", "납부", "기간", "2026"],
                 ["academic_notice", "notice"],
                 ["등록금", "납부"],
                 "ok"),
    # ── 취업지원 ──────────────────────────────────────────────────────────────
    QuestionCase("Q24", "취업지원센터 위치 어디야", "career",
                 ["취업지원센터", "위치"],
                 ["institution", "static"],
                 ["취업지원센터"],
                 "noise"),
    QuestionCase("Q25", "현장실습 신청 방법", "career",
                 ["현장실습", "신청", "방법"],
                 ["academic_notice", "department"],
                 ["현장실습"],
                 "attachment"),
    # ── 국제교류 ──────────────────────────────────────────────────────────────
    QuestionCase("Q26", "외국인 유학생 입학 지원 방법", "exchange",
                 ["외국인", "유학생", "입학", "특별전형"],
                 ["exchange"],
                 ["외국인특별전형", "유학생"],
                 "attachment",
                 "영어 안내문 PDF 미추출 가능"),
    # ── 비교과 ────────────────────────────────────────────────────────────────
    QuestionCase("Q27", "비교과 프로그램 종류", "extracurricular",
                 ["비교과", "프로그램"],
                 ["notice", "department", "advising"],
                 ["비교과", "마일리지"],
                 "ok"),
    # ── 공지사항 ──────────────────────────────────────────────────────────────
    QuestionCase("Q28", "학사 공지 최근 것 알려줘", "notice",
                 ["학사", "공지"],
                 ["notice", "academic_notice"],
                 ["공지사항"],
                 "noise",
                 "recency intent — temporal reranking 작동 여부"),
    # ── 교내 프로그램 ──────────────────────────────────────────────────────────
    QuestionCase("Q29", "동아리 가입 방법", "club_activity",
                 ["동아리", "가입", "신청"],
                 ["notice", "department"],
                 ["동아리"],
                 "duplicate",
                 "학과별 동아리 공지 중복"),
    QuestionCase("Q30", "학군단 ROTC 지원 자격", "military",
                 ["ROTC", "학군단", "지원자격"],
                 ["notice", "static"],
                 ["학군단", "ROTC"],
                 "ok"),
]

# --------------------------------------------------------------------------- #
# 웹 vs DB 비교 대상 URL (첨부파일 미추출 / section_truncated 대표 사례)
# --------------------------------------------------------------------------- #
WEB_COMPARE_URLS = [
    {
        "label": "2026 하계계절수업 안내",
        "url": "https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=84378&mode=view",
        "doc_id_hint": "deu_academic_notice_84378",
        "expected_keywords": ["계절수업", "신청기간", "수강료"],
    },
    {
        "label": "2026 수강신청 신입생 안내",
        "url": "https://www.deu.ac.kr/www/deu-notice.do?article.offset=30&articleLimit=10&articleNo=81190&mode=view",
        "doc_id_hint": "deu_notice_81190",
        "expected_keywords": ["수강신청", "신입생", "2026"],
    },
    {
        "label": "다전공 안내 가이드(2026)",
        "url": "https://www.deu.ac.kr/www/gra-notice.do?article.offset=0&articleLimit=10&articleNo=80310&mode=view",
        "doc_id_hint": "deu_academic_notice_80310",
        "expected_keywords": ["다전공", "이수학점", "신청"],
    },
    {
        "label": "형제장학금 신청 안내",
        "url": "https://www.deu.ac.kr/www/deu-scholarship.do",
        "doc_id_hint": "deu_department_81485",
        "expected_keywords": ["형제장학금", "신청기간", "제출서류"],
    },
    {
        "label": "재수강 과목 현황 xlsx",
        "url": "https://www.deu.ac.kr/www/gra-notice.do?article.offset=20&articleLimit=10&articleNo=80772&mode=view",
        "doc_id_hint": "deu_academic_notice_80772",
        "expected_keywords": ["재수강", "과목", "이수구분"],
    },
]


# --------------------------------------------------------------------------- #
# DB 연결 헬퍼
# --------------------------------------------------------------------------- #
def _open_db():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    url = os.environ.get("DATABASE_URL", "postgresql://chatbot:chatbot@postgres:5432/chatbot")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    return conn, RealDictCursor


def _db_query(conn, cursor_factory, sql: str, params=None) -> list[dict]:
    with conn.cursor(cursor_factory=cursor_factory) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


# --------------------------------------------------------------------------- #
# 파이프라인 실행 (preprocessor + retrieval + rerank)
# --------------------------------------------------------------------------- #
def run_pipeline_retrieval(query: str, top_k: int = 15) -> dict[str, Any]:
    """Preprocessor → retrieval → rerank 까지 실행하고 중간 결과를 반환."""
    from rag.pipeline.state import PipelineState
    from rag.pipeline.preprocessor import QueryPreprocessor
    from rag.retrieval.search_strategy import build_retrieval_request
    from rag.retrieval import retriever
    from rag.selection.reranker import rerank_documents

    state = PipelineState.from_query(query)
    state.retrieval_top_k = top_k

    # 1. 전처리
    t0 = time.time()
    QueryPreprocessor().run(state)
    preprocess_ms = int((time.time() - t0) * 1000)

    # 2. retrieval request 구성
    req = build_retrieval_request(state)

    # 3. 검색
    t1 = time.time()
    docs = retriever.retrieve_documents(request=req)
    retrieval_ms = int((time.time() - t1) * 1000)

    # 4. rerank
    t2 = time.time()
    reranked = rerank_documents(
        docs,
        query=state.rewritten_query or state.normalized_query or state.original_query,
        keywords=state.keywords,
        category=state.category,
        filters=state.filters,
        ranking_hints=state.metadata.get("retrieval_strategy_log", {}).get("ranking_hints", {}),
    )
    rerank_ms = int((time.time() - t2) * 1000)

    selected = reranked[:5]

    features = state.metadata.get("query_understanding", {}).get("query_features", {})
    return {
        "query": query,
        "normalized": state.normalized_query,
        "rewritten": state.rewritten_query,
        "keywords": state.keywords,
        "filters": state.filters,
        "family": features.get("family", ""),
        "domain": features.get("domain", ""),
        "category": state.category,
        "strategy": req.strategy,
        "retrieved_count": len(docs),
        "retrieved_top5": [_doc_row(d, i + 1) for i, d in enumerate(docs[:5])],
        "reranked_top5": [_doc_row(d, i + 1) for i, d in enumerate(reranked[:5])],
        "selected_top3": [_doc_row(d, i + 1) for i, d in enumerate(selected[:3])],
        "preprocess_ms": preprocess_ms,
        "retrieval_ms": retrieval_ms,
        "rerank_ms": rerank_ms,
    }


def _doc_row(doc: Any, rank: int) -> dict:
    meta = doc.metadata if hasattr(doc, "metadata") and doc.metadata else {}
    return {
        "rank": rank,
        "doc_id": doc.doc_id,
        "chunk_id": doc.chunk_id,
        "title": getattr(doc, "title", ""),
        "source_type": meta.get("source_type", ""),
        "score": round(float(getattr(doc, "score", 0)), 4),
        "rerank_score": round(float(meta.get("rerank_score") or doc.score or 0), 4),
        "content_length": meta.get("content_length") or len(getattr(doc, "content", "") or ""),
        "content_snippet": (getattr(doc, "content", "") or "")[:120].replace("\n", " "),
    }


# --------------------------------------------------------------------------- #
# DB 커버리지 분석
# --------------------------------------------------------------------------- #
def check_db_coverage(conn, cursor_factory, case: QuestionCase) -> dict[str, Any]:
    """대표 질문에 대한 DB 저장 상태를 분석."""
    # 키워드 중 첫 번째로 content/title ilike 검색
    kw = case.expected_keywords[0] if case.expected_keywords else case.query[:10]

    doc_rows = _db_query(conn, cursor_factory, """
        SELECT d.doc_id, d.source_type, d.title,
               d.published_at::date AS published_at,
               (SELECT count(*) FROM chunks c WHERE c.doc_id=d.doc_id) AS chunk_count,
               (SELECT count(*) FROM document_assets da WHERE da.doc_id=d.doc_id AND da.asset_type='attachment') AS asset_count,
               (SELECT count(*) FROM document_assets da
                LEFT JOIN document_contents dc ON dc.asset_id=da.id AND dc.content_type='attachment' AND length(btrim(dc.content))>50
                WHERE da.doc_id=d.doc_id AND da.asset_type='attachment' AND dc.asset_id IS NULL) AS missing_attach
        FROM documents d
        WHERE d.title ILIKE %s OR EXISTS (
            SELECT 1 FROM document_contents dc WHERE dc.doc_id=d.doc_id AND dc.content_type='clean' AND dc.content ILIKE %s
        )
        ORDER BY d.published_at DESC NULLS LAST
        LIMIT 5
    """, (f"%{kw}%", f"%{kw}%"))

    return {
        "keyword": kw,
        "matched_docs": len(doc_rows),
        "top_docs": [
            {
                "doc_id": r["doc_id"],
                "source_type": r["source_type"],
                "title": (r["title"] or "")[:80],
                "published_at": str(r["published_at"] or ""),
                "chunk_count": r["chunk_count"],
                "asset_count": r["asset_count"],
                "missing_attach": r["missing_attach"],
            }
            for r in doc_rows
        ],
    }


# --------------------------------------------------------------------------- #
# 중복 chunk 영향 분석
# --------------------------------------------------------------------------- #
def analyze_duplicate_impact(conn, cursor_factory, retrieved_top5: list[dict]) -> dict[str, Any]:
    """retrieval 상위 결과에서 중복 chunk 비율 측정."""
    if not retrieved_top5:
        return {"dup_ratio": 0.0, "dup_chunks": []}

    chunk_ids = [r["chunk_id"] for r in retrieved_top5 if r.get("chunk_id")]
    if not chunk_ids:
        return {"dup_ratio": 0.0, "dup_chunks": []}

    placeholders = ",".join(["%s"] * len(chunk_ids))
    rows = _db_query(conn, cursor_factory, f"""
        SELECT c.chunk_id, c.content_hash,
               (SELECT count(*) FROM chunks c2 WHERE c2.content_hash=c.content_hash) AS dup_count
        FROM chunks c
        WHERE c.chunk_id IN ({placeholders})
    """, chunk_ids)

    dup_chunks = [r for r in rows if r["dup_count"] > 1]
    return {
        "dup_ratio": round(len(dup_chunks) / len(rows), 2) if rows else 0.0,
        "dup_chunks": [{"chunk_id": r["chunk_id"], "dup_count": r["dup_count"]} for r in dup_chunks],
    }


# --------------------------------------------------------------------------- #
# 웹 vs DB 비교
# --------------------------------------------------------------------------- #
def compare_web_vs_db(conn, cursor_factory, entry: dict) -> dict[str, Any]:
    """단일 URL에 대해 실제 웹 visible text와 DB 저장 content를 비교."""
    label = entry["label"]
    url = entry["url"]
    doc_id_hint = entry["doc_id_hint"]
    expected_keywords = entry["expected_keywords"]

    result: dict[str, Any] = {
        "label": label,
        "url": url,
        "web_fetch_ok": False,
        "web_text_len": 0,
        "web_keywords_found": [],
        "db_doc_found": False,
        "db_clean_len": 0,
        "db_chunk_count": 0,
        "db_asset_count": 0,
        "db_missing_attach": 0,
        "db_keywords_found": [],
        "coverage_gap": [],
        "verdict": "UNKNOWN",
    }

    # 1. 웹 fetch
    try:
        import urllib.request
        import urllib.error
        req_obj = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DEU-Audit/1.0)"})
        with urllib.request.urlopen(req_obj, timeout=10) as resp:
            raw = resp.read()
        encoding = "utf-8"
        try:
            text = raw.decode(encoding)
        except UnicodeDecodeError:
            text = raw.decode("euc-kr", errors="replace")

        # visible text 추출 (간단한 tag strip)
        visible = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        visible = re.sub(r"<style[^>]*>.*?</style>", "", visible, flags=re.DOTALL | re.IGNORECASE)
        visible = re.sub(r"<[^>]+>", " ", visible)
        visible = re.sub(r"\s+", " ", visible).strip()

        result["web_fetch_ok"] = True
        result["web_text_len"] = len(visible)
        result["web_keywords_found"] = [kw for kw in expected_keywords if kw in visible]
    except Exception as exc:
        result["web_error"] = str(exc)[:100]

    # 2. DB 상태 조회
    db_rows = _db_query(conn, cursor_factory, """
        SELECT d.doc_id, d.title,
               (SELECT length(btrim(dc.content)) FROM document_contents dc
                WHERE dc.doc_id=d.doc_id AND dc.content_type='clean' LIMIT 1) AS clean_len,
               (SELECT count(*) FROM chunks c WHERE c.doc_id=d.doc_id) AS chunk_count,
               (SELECT count(*) FROM document_assets da WHERE da.doc_id=d.doc_id AND da.asset_type='attachment') AS asset_count,
               (SELECT count(*) FROM document_assets da
                LEFT JOIN document_contents dc2 ON dc2.asset_id=da.id AND dc2.content_type='attachment' AND length(btrim(dc2.content))>50
                WHERE da.doc_id=d.doc_id AND da.asset_type='attachment' AND dc2.asset_id IS NULL) AS missing_attach
        FROM documents d
        WHERE d.doc_id LIKE %s OR d.source_url = %s
        LIMIT 3
    """, (f"%{doc_id_hint.split('_')[-1]}%", url))

    if db_rows:
        r = db_rows[0]
        result["db_doc_found"] = True
        result["db_clean_len"] = r["clean_len"] or 0
        result["db_chunk_count"] = r["chunk_count"] or 0
        result["db_asset_count"] = r["asset_count"] or 0
        result["db_missing_attach"] = r["missing_attach"] or 0

        # DB content에서 키워드 확인
        content_rows = _db_query(conn, cursor_factory, """
            SELECT dc.content FROM document_contents dc
            WHERE dc.doc_id = %s AND dc.content_type IN ('clean','attachment')
            LIMIT 10
        """, (r["doc_id"],))
        all_content = " ".join(cr["content"] or "" for cr in content_rows)
        result["db_keywords_found"] = [kw for kw in expected_keywords if kw in all_content]

    # 3. 차이 분석
    web_kw = set(result["web_keywords_found"])
    db_kw = set(result["db_keywords_found"])
    gap = list(web_kw - db_kw)
    result["coverage_gap"] = gap

    # content length 비율 계산
    web_len = result["web_text_len"]
    db_len = result["db_clean_len"]
    result["web_db_ratio"] = round(db_len / web_len, 2) if web_len > 0 else 0.0

    if not result["db_doc_found"]:
        result["verdict"] = "DB_MISSING"
    elif result["db_missing_attach"] > 0:
        result["verdict"] = "ATTACH_UNEXTRACTED"
    elif gap:
        result["verdict"] = "CONTENT_GAP"
    elif db_len > 0 and web_len > 0 and (db_len / web_len) < 0.3:
        result["verdict"] = "LOW_COVERAGE"
    elif result["db_chunk_count"] == 0:
        result["verdict"] = "NO_CHUNKS"
    else:
        result["verdict"] = "OK"

    return result


# --------------------------------------------------------------------------- #
# 실패 케이스 분류
# --------------------------------------------------------------------------- #
def classify_failure(case: QuestionCase, result: dict) -> dict[str, Any]:
    """retrieval 결과를 분석하여 실패 유형 판별."""
    pipe = result.get("pipeline", result)  # result가 pipe 자체인 경우도 허용
    retrieved = pipe.get("retrieved_count", 0)
    top5 = pipe.get("reranked_top5", [])
    dup = result.get("duplicate_impact", {})

    failures = []
    root_cause = "ok"

    # 1. retrieval 실패
    if retrieved == 0:
        failures.append("zero_retrieval")
        root_cause = "retrieval_failure"

    # 2. 기대 source_type 미등장
    top5_sources = {d["source_type"] for d in top5}
    expected_sources = set(case.expected_source_types)
    if top5 and not (top5_sources & expected_sources):
        failures.append(f"wrong_source_type: got {top5_sources}, expected {expected_sources}")
        if root_cause == "ok":
            root_cause = "retrieval_noise"

    # 3. 짧은 chunk 상위 등장
    short_top = [d for d in top5[:3] if d["content_length"] < 120]
    if short_top:
        failures.append(f"short_chunk_top3: {[d['chunk_id'] for d in short_top]}")
        if root_cause == "ok":
            root_cause = "chunking_noise"

    # 4. 중복 chunk 비율
    if dup.get("dup_ratio", 0) >= 0.4:
        failures.append(f"high_dup_ratio: {dup['dup_ratio']}")
        if root_cause == "ok":
            root_cause = "duplicate_chunk"

    # 5. attachment 위험
    if case.failure_risk == "attachment":
        failures.append("attachment_risk: HWP/PDF 미추출로 핵심 내용 누락 가능")
        if root_cause == "ok":
            root_cause = "attachment_parser"

    # 6. DB 커버리지 부재
    db_cov = result.get("db_coverage", result.get("pipeline", {}))
    if db_cov.get("matched_docs", 0) == 0:
        failures.append("no_db_document: 관련 문서 DB 없음")
        if root_cause == "ok":
            root_cause = "crawler_missing"

    stage_map = {
        "retrieval_failure": "retrieval",
        "retrieval_noise": "retrieval/rerank",
        "chunking_noise": "chunking",
        "duplicate_chunk": "chunking/dedup",
        "attachment_parser": "attachment_parser",
        "crawler_missing": "crawler",
        "ok": "—",
    }

    return {
        "failures": failures,
        "root_cause": root_cause,
        "bottleneck_stage": stage_map.get(root_cause, root_cause),
        "severity": "HIGH" if root_cause in ("retrieval_failure", "crawler_missing") else
                    "MED" if root_cause in ("attachment_parser", "duplicate_chunk", "retrieval_noise") else "LOW",
    }


# --------------------------------------------------------------------------- #
# Markdown 리포트 생성
# --------------------------------------------------------------------------- #
def build_report(results: list[dict], web_compare: list[dict], stage_stats: dict) -> str:
    lines: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines += [
        f"# RAG Retrieval 품질 감사 리포트",
        f"",
        f"- **생성일시**: {now}",
        f"- **분석 질문**: {len(results)}건",
        f"- **웹 vs DB 비교 URL**: {len(web_compare)}건",
        f"",
        "---",
        "",
    ]

    # ── 1. 병목 단계 요약 ──────────────────────────────────────────────────────
    lines += ["## 1. 병목 단계별 집계", ""]
    lines += ["| 단계 | 영향 질문 수 | 심각도 |", "|---|---|---|"]
    for stage, info in sorted(stage_stats.items(), key=lambda x: -x[1]["count"]):
        lines.append(f"| {stage} | {info['count']}건 | {info['severity']} |")
    lines.append("")

    # ── 2. 질문별 결과 요약 테이블 ────────────────────────────────────────────
    lines += ["## 2. 질문별 결과 요약", ""]
    lines += [
        "| QID | 질문 | 검색결과 | 전략 | 중복율 | 실패원인 | 단계 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        fail = r.get("failure_analysis", {})
        root = fail.get("root_cause", "ok")
        stage = fail.get("bottleneck_stage", "—")
        dup_ratio = r.get("duplicate_impact", {}).get("dup_ratio", 0.0)
        icon = "✅" if root == "ok" else ("🔴" if fail.get("severity") == "HIGH" else "🟡")
        lines.append(
            f"| {r['case'].qid} | {r['case'].query[:25]} | {r['pipeline'].get('retrieved_count',0)}건 "
            f"| {r['pipeline'].get('strategy','?')} | {dup_ratio:.0%} | {root} | {stage} |"
        )
    lines.append("")

    # ── 3. 상세 실패 케이스 ────────────────────────────────────────────────────
    lines += ["## 3. 실패 케이스 상세 분석", ""]
    fail_cases = [r for r in results if r.get("failure_analysis", {}).get("root_cause", "ok") != "ok"]

    for r in fail_cases:
        case: QuestionCase = r["case"]
        pipe = r["pipeline"]
        fail = r["failure_analysis"]
        db_cov = r.get("db_coverage", {})

        lines += [
            f"### {case.qid} — {case.query}",
            f"",
            f"**실패 원인**: `{fail['root_cause']}` | **단계**: `{fail['bottleneck_stage']}` | **심각도**: {fail['severity']}",
            f"",
            f"#### 전처리 결과",
            f"- 정규화: `{pipe.get('normalized', '')}`",
            f"- 리라이팅: `{pipe.get('rewritten', '')}`",
            f"- 키워드: `{pipe.get('keywords', [])}`",
            f"- 필터: `{pipe.get('filters', {})}`",
            f"- 패밀리/도메인: `{pipe.get('family', '')}` / `{pipe.get('domain', '')}`",
            f"",
            f"#### Retrieval 결과 (상위 5개)",
        ]

        top5 = pipe.get("retrieved_top5", [])
        if top5:
            lines.append("| 순위 | doc_id | source_type | score | 길이 | 내용 (앞120자) |")
            lines.append("|---|---|---|---|---|---|")
            for d in top5:
                lines.append(
                    f"| {d['rank']} | `{d['doc_id'][:30]}` | {d['source_type']} "
                    f"| {d['score']} | {d['content_length']} | {d['content_snippet'][:60]} |"
                )
        else:
            lines.append("*검색 결과 없음*")
        lines.append("")

        lines += [f"#### Rerank 후 상위 5개"]
        reranked = pipe.get("reranked_top5", [])
        if reranked:
            lines.append("| 순위 | doc_id | source_type | rerank_score | 길이 | 내용 |")
            lines.append("|---|---|---|---|---|---|")
            for d in reranked:
                lines.append(
                    f"| {d['rank']} | `{d['doc_id'][:30]}` | {d['source_type']} "
                    f"| {d['rerank_score']} | {d['content_length']} | {d['content_snippet'][:60]} |"
                )
        lines.append("")

        lines += [
            f"#### DB 커버리지",
            f"- 검색 키워드: `{db_cov.get('keyword', '')}` → 매칭 문서 {db_cov.get('matched_docs', 0)}건",
        ]
        for doc in db_cov.get("top_docs", [])[:3]:
            attach_warn = " ⚠️ 첨부미추출" if doc["missing_attach"] > 0 else ""
            lines.append(
                f"  - `{doc['doc_id']}` | {doc['source_type']} | 청크 {doc['chunk_count']}개 "
                f"| 첨부 {doc['asset_count']}건{attach_warn} | {doc['title'][:50]}"
            )
        lines.append("")

        lines += [
            f"#### 실패 원인 목록",
        ]
        for f_item in fail.get("failures", []):
            lines.append(f"- {f_item}")
        lines.append("")

        lines += [
            f"#### 개선 방향",
        ]
        root = fail["root_cause"]
        if root == "retrieval_failure":
            lines.append("- BM25/vector 인덱스에서 관련 키워드가 없음. 동의어 확장 또는 쿼리 rewriting 개선 필요.")
        elif root == "retrieval_noise":
            lines.append("- 기대 source_type 문서가 retrieval 상위에 미등장. source_policy 또는 boost 튜닝 필요.")
        elif root == "chunking_noise":
            lines.append("- 짧은/노이즈 chunk가 상위에 등장. content_length < 120 + 고중복 hash 필터 강화.")
        elif root == "duplicate_chunk":
            lines.append("- 중복 chunk가 검색 다양성을 침식. content_hash 기반 dedup 또는 reranker 패널티 강화.")
        elif root == "attachment_parser":
            lines.append(f"- {case.notes}. HWP/XLS/PDF 파서 개선 또는 retry_queue 재실행 필요.")
        elif root == "crawler_missing":
            lines.append("- 관련 문서가 DB에 없음. 크롤링 대상 URL 추가 또는 pagination 실패 점검.")
        lines.append("")
        lines.append("---")
        lines.append("")

    # ── 4. 웹 vs DB 비교 ──────────────────────────────────────────────────────
    lines += ["## 4. 실제 웹 vs DB 비교", ""]
    lines += [
        "| 페이지 | DB 존재 | 웹(자) | DB(자) | 커버리지율 | 첨부 미추출 | 키워드 갭 | 판정 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for w in web_compare:
        db_found = "O" if w["db_doc_found"] else "X"
        ratio = f"{w.get('web_db_ratio', 0):.0%}"
        gap = ", ".join(w["coverage_gap"]) or "—"
        missing = str(w.get("db_missing_attach", 0))
        verdict_icon = {"OK": "✅", "ATTACH_UNEXTRACTED": "🟡", "CONTENT_GAP": "🟡",
                        "LOW_COVERAGE": "🟡", "DB_MISSING": "🔴", "NO_CHUNKS": "🔴"}.get(w["verdict"], "❓")
        lines.append(
            f"| {w['label']} | {db_found} | {w['web_text_len']} | {w['db_clean_len']} "
            f"| {ratio} | {missing} | {gap} | {verdict_icon} {w['verdict']} |"
        )
    lines.append("")

    # ── 5. 단계별 근본 원인 분석 ──────────────────────────────────────────────
    lines += [
        "## 5. 단계별 근본 원인 분석",
        "",
        "| 단계 | 문제 | 영향 | 개선 방향 |",
        "|---|---|---|---|",
        "| crawler | SSL 오류 100건, DISCOVERED 미처리 203건 | 게시판 목록 누락 | SSL 예외처리, 재시도 실행 |",
        "| attachment_parser | HWP 989건·PDF 504건·XLS 75건 미추출 | 첨부 기반 답변 불가 | XLS 파서 추가, OCR PDF 지원, retry 재실행 |",
        "| chunking | 14,336 중복 그룹, section_truncated 15,093개 | 검색 다양성 침식 | content_hash dedup, 대용량 문서 사전 분할 |",
        "| retrieval | keyword 전략 'category=수강' 3건 zero_retrieval | 특정 카테고리 검색 실패 | BM25 인덱스 토큰 확인, 동의어 확장 |",
        "| rerank | 노이즈 chunk(메뉴·헤더)가 상위 score 획득 | 잘못된 답변 소스 선택 | content_length < 100 + 고중복 hash 패널티 강화 |",
        "| LLM_grounding | (별도 분석 필요) | — | 컨텍스트 품질 개선이 선행 필요 |",
        "",
    ]

    # ── 6. 개선 우선순위 재정렬 ────────────────────────────────────────────────
    lines += [
        "## 6. 개선 우선순위 (사용자 체감 영향 기준)",
        "",
        "### P0 — 즉시 (이번 스프린트)",
        "",
        "| 항목 | 영향 | 작업량 |",
        "|---|---|---|",
        "| retry_queue pending 1,664건 재실행 (`run_retry_failed_documents`) | 첨부파일 일부 즉시 복구 | 30분 |",
        "| reranker에서 content_hash 중복 청크 MAX 1개로 제한 | 중복으로 인한 검색 다양성 침식 즉시 개선 | 2시간 |",
        "| content_length < 80 + 중복률 높은 청크 retrieval 제외 필터 | 메뉴/헤더 노이즈 청크 상위 노출 제거 | 1시간 |",
        "",
        "### P1 — 단기 (2주 내)",
        "",
        "| 항목 | 영향 | 작업량 |",
        "|---|---|---|",
        "| XLS/XLSX 파서 추가 (openpyxl) | 수강신청 현황·일정 표 데이터 복구 | 1일 |",
        "| HWP 파서 개선 또는 대체 파서 도입 | 장학금·학사 안내 핵심 내용 복구 | 2~3일 |",
        "| crawler_documents PARSED 217건 청킹 재실행 | 미완료 파이프라인 즉시 처리 | 1시간 |",
        "| document dedup: source_url 정규화 (학과 prefix 제거) | 82~34개 중복 문서 제거 | 1일 |",
        "",
        "### P2 — 중기 (1개월 내)",
        "",
        "| 항목 | 영향 | 작업량 |",
        "|---|---|---|",
        "| 대용량 첨부파일 heading/table 기반 사전 분할 | section_truncated 15,093개 개선 | 3~5일 |",
        "| SSL 오류 학과 서브도메인 100건 처리 | 게시판 목록 수집 복구 | 1일 |",
        "| SNS 아이콘 텍스트 265건 정규화 단계 제거 | 노이즈 content 정리 | 반일 |",
        "| published_at 없는 문서 날짜 파싱 개선 | temporal reranking 정확도 향상 | 1일 |",
        "",
    ]

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/app/reports/retrieval_audit.md")
    parser.add_argument("--skip-web", action="store_true", help="웹 fetch 건너뜀")
    parser.add_argument("--questions", default="all", help="쉼표 구분 QID 목록 (예: Q01,Q03)")
    args = parser.parse_args()

    print("=" * 60)
    print("RAG Retrieval Quality Audit")
    print("=" * 60)

    # DB 연결
    try:
        conn, cursor_factory = _open_db()
        print("[DB] 연결 성공")
    except Exception as exc:
        print(f"[DB] 연결 실패: {exc}", file=sys.stderr)
        sys.exit(1)

    # 질문 필터
    selected_qids = set(args.questions.split(",")) if args.questions != "all" else None
    cases = [c for c in QUESTION_CASES if selected_qids is None or c.qid in (selected_qids or set())]

    # 파이프라인 실행
    results: list[dict] = []
    stage_stats: dict[str, dict] = {}

    for case in cases:
        print(f"\n[{case.qid}] {case.query}")
        try:
            pipe = run_pipeline_retrieval(case.query)
        except Exception as exc:
            print(f"  ⚠ pipeline error: {exc}")
            pipe = {"query": case.query, "retrieved_count": 0, "error": str(exc)}

        db_cov = check_db_coverage(conn, cursor_factory, case)
        dup_impact = analyze_duplicate_impact(conn, cursor_factory, pipe.get("retrieved_top5", []))
        fail = classify_failure(case, {"pipeline": pipe, "db_coverage": db_cov, "duplicate_impact": dup_impact})

        print(f"  검색결과: {pipe.get('retrieved_count', 0)}건 | 전략: {pipe.get('strategy', '?')} "
              f"| 중복: {dup_impact.get('dup_ratio', 0):.0%} | 실패: {fail['root_cause']}")

        r = {
            "case": case,
            "pipeline": pipe,
            "db_coverage": db_cov,
            "duplicate_impact": dup_impact,
            "failure_analysis": fail,
        }
        results.append(r)

        # 단계별 통계 집계
        stage = fail["bottleneck_stage"]
        if stage not in stage_stats:
            stage_stats[stage] = {"count": 0, "severity": fail["severity"]}
        stage_stats[stage]["count"] += 1
        if fail["severity"] == "HIGH":
            stage_stats[stage]["severity"] = "HIGH"

    # 웹 vs DB 비교
    web_compare_results: list[dict] = []
    if not args.skip_web:
        print("\n[WEB vs DB 비교]")
        for entry in WEB_COMPARE_URLS:
            print(f"  {entry['label']}...")
            try:
                w = compare_web_vs_db(conn, cursor_factory, entry)
                print(f"  → {w['verdict']} | 웹:{w['web_text_len']}자 | DB:{w['db_clean_len']}자 "
                      f"| 갭:{w['coverage_gap']}")
            except Exception as exc:
                w = {"label": entry["label"], "url": entry["url"], "error": str(exc),
                     "verdict": "ERROR", "web_fetch_ok": False, "db_doc_found": False,
                     "web_text_len": 0, "db_clean_len": 0, "web_keywords_found": [],
                     "db_keywords_found": [], "coverage_gap": [], "db_missing_attach": 0}
                print(f"  ⚠ {exc}")
            web_compare_results.append(w)

    conn.close()

    # 리포트 생성
    report = build_report(results, web_compare_results, stage_stats)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n[완료] 리포트 저장: {args.output}")

    # 콘솔 요약
    fail_count = sum(1 for r in results if r["failure_analysis"]["root_cause"] != "ok")
    print(f"\n총 {len(results)}개 질문 중 실패/위험: {fail_count}개")
    print("단계별 병목:")
    for stage, info in sorted(stage_stats.items(), key=lambda x: -x[1]["count"]):
        print(f"  {stage}: {info['count']}건 ({info['severity']})")


if __name__ == "__main__":
    main()
