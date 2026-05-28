from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_supabase_rag_quality import (  # noqa: E402
    analyze_cases,
    corpus_quality,
    failure_cases,
    open_connection,
    precise_probe,
    precise_terms,
    schema_summary,
)
from psycopg2.extras import RealDictCursor  # noqa: E402
from rag.embedding.koe5_embedder import KoE5Embedder  # noqa: E402
from rag.pipeline.preprocessor import QueryPreprocessor  # noqa: E402
from rag.pipeline.state import PipelineState  # noqa: E402
from rag.retrieval.retriever import retrieve_documents  # noqa: E402
from rag.retrieval.search_strategy import build_retrieval_request  # noqa: E402
from rag.selection.reranker import rerank_documents  # noqa: E402
from rag.selection.topk_selector import select_topk  # noqa: E402


NEGATIVE_ANSWER_PATTERNS = (
    "확인할 수 없",
    "찾을 수 없",
    "알 수 없",
    "제공된 정보",
    "관련 정보를 찾을 수",
    "죄송",
)


def summarize_doc(doc: Any, rank: int) -> dict[str, Any]:
    metadata = getattr(doc, "metadata", {}) or {}
    signals = metadata.get("rerank_signals") or {}
    return {
        "rank": rank,
        "doc_id": getattr(doc, "doc_id", None),
        "chunk_id": getattr(doc, "chunk_id", None),
        "title": getattr(doc, "title", ""),
        "source": getattr(doc, "source", ""),
        "score": getattr(doc, "score", None),
        "source_type": metadata.get("source_type"),
        "department": metadata.get("department"),
        "section_type": metadata.get("section_type"),
        "section_title": metadata.get("section_title"),
        "content_length": metadata.get("content_length"),
        "lexical_score": metadata.get("lexical_score"),
        "lexical_norm_score": metadata.get("lexical_norm_score"),
        "vector_score": metadata.get("vector_score"),
        "rrf_score": metadata.get("rrf_score"),
        "srrf_score": metadata.get("srrf_score"),
        "final_score": metadata.get("final_score"),
        "search_mode": metadata.get("search_mode"),
        "rerank_score": metadata.get("rerank_score", getattr(doc, "score", None)),
        "rerank_signals": signals,
        "content_preview": (getattr(doc, "content", "") or "")[:260],
    }


def run_with_mode(request: Any, mode: str) -> list[Any]:
    previous_mode = os.getenv("RETRIEVAL_MODE")
    os.environ["RETRIEVAL_MODE"] = mode
    try:
        return retrieve_documents(request=request)
    finally:
        if previous_mode is None:
            os.environ.pop("RETRIEVAL_MODE", None)
        else:
            os.environ["RETRIEVAL_MODE"] = previous_mode


def build_request(preprocessor: QueryPreprocessor, embedder: KoE5Embedder, query: str, top_k: int) -> tuple[Any, dict[str, Any]]:
    state = PipelineState.from_query(query)
    preprocessor.run(state)
    request = build_retrieval_request(state)
    query_vector = embedder.embed_query(request.query)
    request = request.model_copy(
        update={
            "top_k": top_k,
            "query_vector": list(query_vector or []),
        }
    )
    query_analysis = {
        "original_query": query,
        "normalized_query": state.normalized_query,
        "rewritten_query": state.rewritten_query,
        "rewritten_queries": state.rewritten_queries,
        "keywords": state.keywords,
        "category": state.category,
        "filters": state.filters,
        "query_vector_size": len(query_vector or []),
        "fallback_triggers": request.fallback_triggers,
    }
    return request, query_analysis


def rank_of_evidence(candidates: list[dict[str, Any]], evidence_chunk_ids: set[str], evidence_doc_ids: set[str]) -> int | None:
    for item in candidates:
        if item.get("chunk_id") in evidence_chunk_ids or item.get("doc_id") in evidence_doc_ids:
            return int(item["rank"])
    return None


def selected_has_query_evidence(selected: list[dict[str, Any]], terms: list[str]) -> bool:
    strong_terms = precise_terms(terms)
    if not strong_terms:
        return False
    text = " ".join(
        f"{item.get('title') or ''} {item.get('content_preview') or ''}"
        for item in selected
    ).lower()
    return any(term.lower() in text for term in strong_terms)


def classify_stage(case: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    evidence = stage["evidence"]
    ranks = stage["evidence_ranks"]
    selected = stage["selected_top"]
    answer = case.get("final_answer") or ""
    negative_answer = any(pattern in answer for pattern in NEGATIVE_ANSWER_PATTERNS)
    retrieval_id = case.get("retrieval_log_id")
    selected_doc_count = int(case.get("selected_doc_count") or 0)
    retrieved_doc_count = int(case.get("retrieved_doc_count") or 0)

    if not retrieval_id:
        if case.get("intent") == "PROFANITY":
            return {"bucket": "out_of_scope", "stage": "policy_route", "reason": "Profanity route intentionally bypassed RAG."}
        if evidence["exists"]:
            return {"bucket": "keyword/category/filter", "stage": "query_analysis", "reason": "DB evidence exists, but intent/routing bypassed RAG."}
        return {"bucket": "crawler/data 부족", "stage": "data", "reason": "RAG was bypassed and no precise DB evidence was found."}

    if evidence["exists"] and selected_has_query_evidence(selected, stage["query_terms"]) and negative_answer:
        return {"bucket": "final generation 문제", "stage": "generation", "reason": "Selected context contains query evidence, but final answer is negative or contradicts it."}

    if evidence["exists"] and selected_doc_count == 0:
        if case.get("filters"):
            return {"bucket": "keyword/category/filter 문제", "stage": "filter_or_selection", "reason": "Evidence exists, but logged retrieval selected zero chunks; filters may be over-constraining."}
        return {"bucket": "lexical search 문제", "stage": "retrieval_empty", "reason": "Evidence exists, but logged retrieval returned or selected zero chunks."}

    if not evidence["exists"]:
        return {"bucket": "crawler/data 부족", "stage": "data", "reason": "No precise DB evidence was found for strong query terms."}

    lexical_rank = ranks.get("lexical")
    vector_rank = ranks.get("vector")
    hybrid_rank = ranks.get("hybrid")
    rerank_rank = ranks.get("reranked")
    selected_rank = ranks.get("selected")

    if lexical_rank and not vector_rank and hybrid_rank and hybrid_rank > lexical_rank + 5:
        return {"bucket": "vector search 문제", "stage": "vector", "reason": "Evidence appears lexically, but vector branch misses it and hybrid rank deteriorates."}
    if vector_rank and not lexical_rank and hybrid_rank and hybrid_rank > vector_rank + 5:
        return {"bucket": "lexical search 문제", "stage": "lexical", "reason": "Evidence appears semantically, but lexical branch misses it and hybrid rank deteriorates."}
    if (lexical_rank or vector_rank) and (not hybrid_rank or hybrid_rank > min(x for x in [lexical_rank, vector_rank] if x) + 5):
        return {"bucket": "hybrid merge 문제", "stage": "hybrid_merge", "reason": "Evidence is present before merge but drops after hybrid scoring."}
    if hybrid_rank and rerank_rank and rerank_rank > hybrid_rank + 3:
        return {"bucket": "rerank 문제", "stage": "rerank", "reason": "Evidence drops after reranking."}
    if rerank_rank and not selected_rank:
        return {"bucket": "rerank 문제", "stage": "final_selection", "reason": "Evidence survives rerank but is not selected into final context."}
    if retrieved_doc_count > 0 and selected_doc_count > 0 and negative_answer:
        return {"bucket": "final generation 문제", "stage": "generation", "reason": "Retrieval selected context, but answer is uncertain or negative."}
    return {"bucket": "mixed", "stage": "manual_review", "reason": "Evidence/ranking pattern is mixed; inspect candidates and selected context."}


def diagnose_stage_for_case(
    cur: Any,
    preprocessor: QueryPreprocessor,
    embedder: KoE5Embedder,
    case: dict[str, Any],
    *,
    candidate_top_k: int,
) -> dict[str, Any]:
    query = case.get("user_query") or case.get("question") or ""
    request, query_analysis = build_request(preprocessor, embedder, query, candidate_top_k)
    lexical_docs = run_with_mode(request.model_copy(update={"strategy": "keyword"}), "lexical")
    vector_docs = run_with_mode(request.model_copy(update={"strategy": "vector"}), "vector")
    hybrid_docs = run_with_mode(request.model_copy(update={"strategy": "hybrid"}), "hybrid")
    reranked_docs = rerank_documents(
        hybrid_docs,
        query=request.query,
        keywords=request.keywords,
        category=request.category,
        filters=request.filters,
    )
    selected_docs = select_topk(reranked_docs)

    lexical_top = [summarize_doc(doc, rank) for rank, doc in enumerate(lexical_docs[:candidate_top_k], start=1)]
    vector_top = [summarize_doc(doc, rank) for rank, doc in enumerate(vector_docs[:candidate_top_k], start=1)]
    hybrid_top = [summarize_doc(doc, rank) for rank, doc in enumerate(hybrid_docs[:candidate_top_k], start=1)]
    reranked_top = [summarize_doc(doc, rank) for rank, doc in enumerate(reranked_docs[:candidate_top_k], start=1)]
    selected_top = [summarize_doc(doc, rank) for rank, doc in enumerate(selected_docs, start=1)]

    terms = list(
        dict.fromkeys(
            [
                *(query_analysis.get("keywords") or []),
                query_analysis.get("rewritten_query") or "",
                query,
            ]
        )
    )
    evidence_rows = precise_probe(cur, terms, limit=8)
    evidence_chunk_ids = {row["chunk_id"] for row in evidence_rows if row.get("chunk_id")}
    evidence_doc_ids = {row["doc_id"] for row in evidence_rows if row.get("doc_id")}

    stage = {
        "query_analysis": query_analysis,
        "query_terms": terms,
        "evidence": {
            "exists": bool(evidence_rows),
            "precise_terms": precise_terms(terms),
            "top_db_matches": evidence_rows,
        },
        "lexical_top": lexical_top,
        "vector_top": vector_top,
        "hybrid_top": hybrid_top,
        "reranked_top": reranked_top,
        "selected_top": selected_top,
        "evidence_ranks": {
            "lexical": rank_of_evidence(lexical_top, evidence_chunk_ids, evidence_doc_ids),
            "vector": rank_of_evidence(vector_top, evidence_chunk_ids, evidence_doc_ids),
            "hybrid": rank_of_evidence(hybrid_top, evidence_chunk_ids, evidence_doc_ids),
            "reranked": rank_of_evidence(reranked_top, evidence_chunk_ids, evidence_doc_ids),
            "selected": rank_of_evidence(selected_top, evidence_chunk_ids, evidence_doc_ids),
        },
    }
    stage["stage_classification"] = classify_stage(case, stage)
    return stage


def compact_case(case: dict[str, Any], stage: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "query_id",
        "request_id",
        "user_query",
        "intent",
        "rewritten_query",
        "extracted_keywords",
        "category",
        "filters",
        "retrieved_doc_count",
        "reranked_doc_count",
        "selected_doc_count",
        "fallback_used",
        "retrieval_strategy",
        "retrieval_strategy_log",
        "final_answer",
        "created_at",
    ]
    return {key: case.get(key) for key in keys} | {"stage_diagnosis": stage}


def markdown_table(rows: list[list[Any]], headers: list[str]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def top_titles(items: list[dict[str, Any]], limit: int = 3) -> str:
    if not items:
        return "없음"
    return "; ".join(f"{item.get('rank')}. {item.get('title')} ({item.get('score')})" for item in items[:limit])


def write_report(path: Path, result: dict[str, Any]) -> None:
    cases = result["cases"]
    bucket_counts = Counter(case["stage_diagnosis"]["stage_classification"]["bucket"] for case in cases)
    requested_buckets = [
        "crawler/data 부족",
        "query rewrite 문제",
        "keyword/category/filter",
        "lexical search 문제",
        "vector search 문제",
        "hybrid merge 문제",
        "rerank 문제",
        "fallback 문제",
        "final generation 문제",
        "mixed",
        "out_of_scope",
    ]
    sorted_cases = sorted(
        cases,
        key=lambda case: (
            case["stage_diagnosis"]["stage_classification"]["bucket"] == "out_of_scope",
            case["stage_diagnosis"]["stage_classification"]["bucket"] == "mixed",
            str(case.get("created_at") or ""),
        ),
    )
    lines = [
        "# RAG 품질 저하 단계별 진단 리포트",
        "",
        "## 전체 요약",
        "",
        f"- 총 분석 query 수: {result['summary']['total_queries']}",
        f"- 실패/의심 케이스 수: {len(cases)}",
        "- 원인별 분포:",
    ]
    for bucket in requested_buckets:
        lines.append(f"  - {bucket}: {bucket_counts.get(bucket, 0)}")

    corpus = result["corpus_quality"]
    coverage_rows = corpus.get("coverage_gaps") or []
    lines.extend(
        [
            "",
            "## 데이터/크롤러 품질",
            "",
            markdown_table([[row.get("gap"), row.get("count")] for row in coverage_rows], ["gap", "count"]),
            "",
            "해석: documents/chunks/embeddings의 큰 적재 누락은 제한적이지만, assets_without_extracted_content와 very_short_chunks가 검색 잡음 및 답변 누락 리스크다.",
            "",
            "## 대표 실패 케이스",
            "",
        ]
    )

    for case in sorted_cases[:12]:
        stage = case["stage_diagnosis"]
        classification = stage["stage_classification"]
        qa = stage["query_analysis"]
        evidence = stage["evidence"]
        lines.extend(
            [
                f"### Query ID: {case.get('query_id')}",
                "",
                f"원 질문: {case.get('user_query')}",
                f"Rewrite: {case.get('rewritten_query') or qa.get('rewritten_query')}",
                f"Intent: {case.get('intent')}",
                f"Keywords: {case.get('extracted_keywords') or qa.get('keywords')}",
                f"Category: {case.get('category') or qa.get('category')}",
                f"Filters: {case.get('filters') or qa.get('filters')}",
                "",
                f"최종 답변: {(case.get('final_answer') or '')[:500]}",
                f"문제 요약: {classification['reason']}",
                "",
                "검색 후보:",
                f"- lexical top 결과: {top_titles(stage['lexical_top'])}",
                f"- vector top 결과: {top_titles(stage['vector_top'])}",
                f"- hybrid top 결과: {top_titles(stage['hybrid_top'])}",
                f"- rerank 후 결과: {top_titles(stage['reranked_top'])}",
                f"- selected chunks: {top_titles(stage['selected_top'])}",
                "",
                f"정답 근거 DB 존재 여부: {'있음' if evidence['exists'] else '없음/불확실'}",
                f"- 근거 탐색어: {', '.join(evidence['precise_terms']) or '없음'}",
                f"- evidence ranks: {stage['evidence_ranks']}",
                "",
                f"원인 분류: {classification['bucket']} / {classification['stage']}",
                f"수정 제안: {recommendation_for(classification['bucket'])}",
                "",
            ]
        )

    lines.extend(
        [
            "## 6단계 개선안",
            "",
            "### 크롤러 개선",
            "",
            "- 본문 추출 품질 개선: document_assets 중 document_contents가 없는 첨부를 우선 재처리한다.",
            "- UI/메뉴/목록/preview 텍스트 제거: 메뉴, breadcrumb, 목록 preview, 회의록/공고 하단 반복 텍스트를 chunk 전처리에서 제거한다.",
            "- PDF/첨부 본문 추출 여부 확인: file_ext/parser_type별 추출 실패율을 로그화하고 ZIP/HWP/PDF를 별도 retry queue로 분리한다.",
            "- static/index 페이지 chunk 제외 또는 낮은 가중치: source_type이 static/index/menu 성격이면 검색 score penalty를 적용한다.",
            "- 중복 chunk 제거: content_hash뿐 아니라 normalized title+body 기반 중복 제거를 추가한다.",
            "- 짧은/무의미 chunk 필터링: 120자 미만 또는 날짜/메뉴/링크 중심 chunk는 embedding/search 대상에서 제외하거나 낮은 가중치를 준다.",
            "- 문서 타입별 metadata 강화: building/facility, department, scholarship, academic_calendar, shuttle/bus 같은 domain 태그를 crawler 단계에서 확정한다.",
            "",
            "### Retrieval 개선",
            "",
            "- keyword/category/filter 추출 검증: 건물명, 학과명, 부서명, 숫자/호관/버스번호가 rewrite 뒤에도 보존되는지 테스트한다.",
            "- rewrite 전후 검색 결과 비교: original_query, rewritten_query, keywords 각각의 lexical/vector top-k를 저장해 나빠진 rewrite를 감지한다.",
            "- filter relaxation 전략: selected_doc_count=0뿐 아니라 low-confidence일 때 department/category/time filter 제거 retry를 수행한다.",
            "- lexical/vector top-k 확대: merge 전 후보를 최소 60개 이상 유지하고, short/static/source penalty는 merge 후가 아니라 후보 점수에 반영한다.",
            "- hybrid RRF 또는 weighted merge 개선: 현재 weighted 모드에서 vector_norm이 강하게 작동하므로 lexical exact/strong term match를 더 크게 보정한다.",
            "- score normalization 점검: lexical_score null, vector-only 후보가 final_score를 지배하는 케이스를 분리 로그화한다.",
            "- doc type/source별 penalty: external_notice, council, attachment, static 메뉴성 문서가 domain query를 덮지 않도록 penalty를 둔다.",
            "- attachment 공고/회의자료 잡음 완화: 제목/본문에 핵심 고유명사가 없으면 첨부 chunk의 rerank 상향을 제한한다.",
            "- 정답 후보가 2~5위에 있을 때 selection 보정: selected top3가 모두 같은 source_type 또는 low evidence면 다음 후보를 섞는다.",
            "",
            "### Rerank 개선",
            "",
            "- rerank 전후 정답 후보 순위 비교 로그 추가: hybrid_rank, rerank_rank, selected_rank를 request_id별로 저장한다.",
            "- reranker 입력 텍스트 길이 제한 점검: 제목/section/앞부분만 보고 첨부 공고를 과대평가하지 않도록 핵심문장 추출을 적용한다.",
            "- 제목/본문/metadata 조합 개선: title exact match, source_type domain match, department match를 별도 신호로 기록한다.",
            "- UI성 문서 penalty 적용: static/index/menu/회의록/외부채용 공고는 query family mismatch 시 강한 penalty를 둔다.",
            "- rerank threshold 조정: strong_term_match가 낮은 후보는 base_score가 높아도 selected에서 제외한다.",
            "",
            "### Fallback 개선",
            "",
            "- fallback 조건 명확화: empty result뿐 아니라 top score 낮음, selected evidence 없음, answer negative 예상 케이스에도 fallback한다.",
            "- category/filter 제거 fallback: filters/category/time_scope를 제거한 검색 결과와 원 결과를 비교한다.",
            "- rewrite 제거 fallback: rewritten_query가 고유명사를 손상시키면 original_query 기반 검색으로 되돌린다.",
            "- lexical-only/vector-only fallback 비교: 두 branch 중 evidence rank가 더 좋은 쪽을 selected 후보에 강제로 포함한다.",
            "",
            "### Logging 개선",
            "",
            "현재 로그는 selected_chunks 중심이라 후보 탈락 위치를 사후에 완전히 복원하기 어렵다. 다음 로그를 추가해야 한다.",
            "",
            "- original_query",
            "- rewritten_query",
            "- extracted_keywords",
            "- extracted_category",
            "- applied_filters",
            "- lexical_candidates",
            "- vector_candidates",
            "- merged_candidates",
            "- reranked_candidates",
            "- selected_chunks",
            "- rejected_chunks",
            "- rejection_reason",
            "- fallback_reason",
            "- final_context",
            "- answer_grounding_score",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def recommendation_for(bucket: str) -> str:
    if "generation" in bucket:
        return "selected context의 핵심 문장 인용률을 높이고, 답변 전 grounding 검증을 추가한다."
    if "filter" in bucket or "keyword" in bucket:
        return "intent/category/filter 추출을 보수화하고, 고유명사 보존 및 filter relaxation fallback을 추가한다."
    if "hybrid" in bucket:
        return "lexical exact/strong term 후보가 vector-only 잡음에 밀리지 않도록 hybrid scoring을 보정한다."
    if "rerank" in bucket:
        return "rerank 전후 후보 순위 로그를 남기고 source_type/query_family mismatch penalty를 강화한다."
    if "data" in bucket or "crawler" in bucket:
        return "첨부/본문 추출 누락과 짧은 chunk를 우선 정리하고 source metadata를 강화한다."
    return "후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다."


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Diagnose RAG quality from Supabase logs with stage-level candidate replay.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--candidate-top-k", type=int, default=12)
    parser.add_argument("--output-json", default="reports/rag_quality_diagnosis_stage.json")
    parser.add_argument("--report", default="reports/rag_quality_diagnosis.md")
    parser.add_argument("--skip-stage-replay", action="store_true")
    args = parser.parse_args()

    with open_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            schema = schema_summary(cur)
            raw_cases = failure_cases(cur, args.limit)
            analyzed_cases = analyze_cases(cur, raw_cases, per_case_probe_limit=5)
            corpus = corpus_quality(cur)
            cases: list[dict[str, Any]] = []
            preprocessor = None
            embedder = None
            if not args.skip_stage_replay:
                preprocessor = QueryPreprocessor()
                embedder = KoE5Embedder()
            for case in analyzed_cases:
                if args.skip_stage_replay:
                    stage = {
                        "query_analysis": {},
                        "query_terms": case.get("probe_terms") or [],
                        "evidence": {
                            "exists": bool(case.get("db_precise_probe_top")),
                            "precise_terms": case.get("precise_probe_terms") or [],
                            "top_db_matches": case.get("db_precise_probe_top") or [],
                        },
                        "lexical_top": [],
                        "vector_top": [],
                        "hybrid_top": [],
                        "reranked_top": [],
                        "selected_top": case.get("selected_chunks") or [],
                        "evidence_ranks": {},
                        "stage_classification": {
                            "bucket": case["diagnosis"]["cause"],
                            "stage": "log_only",
                            "reason": case["diagnosis"]["reason"],
                        },
                    }
                else:
                    stage = diagnose_stage_for_case(
                        cur,
                        preprocessor,
                        embedder,
                        case,
                        candidate_top_k=args.candidate_top_k,
                    )
                cases.append(compact_case(case, stage))

    result = {
        "summary": {
            "total_queries": schema["row_counts"].get("query_logs"),
            "analyzed_cases": len(cases),
            "cause_distribution": dict(Counter(case["stage_diagnosis"]["stage_classification"]["bucket"] for case in cases)),
        },
        "schema": schema,
        "corpus_quality": corpus,
        "cases": cases,
    }

    output_path = ROOT / args.output_json
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    write_report(ROOT / args.report, result)
    print(json.dumps({"output_json": str(output_path), "report": str(ROOT / args.report), "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
