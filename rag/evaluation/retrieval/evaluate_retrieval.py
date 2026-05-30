"""Retrieval 파이프라인 자동 평가 스크립트.

실행:
    docker compose run --rm rag python -m rag.evaluation.retrieval.evaluate_retrieval
    docker compose run --rm rag python -m rag.evaluation.retrieval.evaluate_retrieval --query-id q001
    docker compose run --rm rag python -m rag.evaluation.retrieval.evaluate_retrieval --limit 5
    docker compose run --rm rag python -m rag.evaluation.retrieval.evaluate_retrieval --dataset datasets/real_queries.yaml
    docker compose run --rm rag python -m rag.evaluation.retrieval.evaluate_retrieval --dataset datasets/real_queries.yaml --tag real
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

# 프로젝트 루트를 sys.path에 추가
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.schemas.query import Query

_DATASET_PATH = Path(__file__).parent / "datasets" / "representative_queries.yaml"
_DATASETS_DIR = Path(__file__).parent / "datasets"
_RESULTS_DIR = Path(__file__).parent / "results"
_RESULTS_DIR.mkdir(exist_ok=True)


def load_queries(path: Path = _DATASET_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("queries", [])


def run_single_query(pipeline: ChatPipeline, query_text: str) -> tuple[Any, PipelineState]:
    q = Query(text=query_text)
    answer = pipeline.run(q)
    state = pipeline.last_state
    return answer, state


def _extract_retrieved_docs_info(state: PipelineState) -> list[dict]:
    docs = []
    for i, doc in enumerate(state.retrieved_docs or []):
        meta = doc.metadata or {}
        docs.append({
            "rank": i + 1,
            "doc_id": doc.doc_id,
            "chunk_id": doc.chunk_id,
            "title": doc.title,
            "source_url": doc.source,
            "source_type": meta.get("source_type", ""),
            "score": doc.score,
            "lexical_score": meta.get("lexical_score"),
            "vector_score": meta.get("vector_score"),
            "content_length": len(doc.content or ""),
        })
    return docs


def _extract_reranked_docs_info(state: PipelineState) -> list[dict]:
    docs = []
    for i, doc in enumerate(state.reranked_docs or []):
        meta = doc.metadata or {}
        signals = meta.get("rerank_signals") or {}
        docs.append({
            "rank": i + 1,
            "doc_id": doc.doc_id,
            "chunk_id": doc.chunk_id,
            "title": doc.title,
            "source_url": doc.source,
            "source_type": meta.get("source_type", ""),
            "score": doc.score,
            "rerank_score": meta.get("rerank_score"),
            "noise_score": signals.get("noise_score"),
            "query_family_boost": signals.get("query_family_boost"),
        })
    return docs


def _extract_selected_docs_info(state: PipelineState) -> list[dict]:
    docs = []
    for i, doc in enumerate(state.selected_docs or []):
        meta = doc.metadata or {}
        docs.append({
            "rank": i + 1,
            "doc_id": doc.doc_id,
            "chunk_id": doc.chunk_id,
            "title": doc.title,
            "source_url": doc.source,
            "source_type": meta.get("source_type", ""),
            "score": doc.score,
            "rerank_score": meta.get("rerank_score"),
            "content_preview": (doc.content or "")[:200],
        })
    return docs


def _check_hit(
    doc_id: str,
    source_url: str,
    chunk_id: str,
    expected_doc_ids: list[str],
    expected_source_urls: list[str],
) -> bool:
    if expected_doc_ids and chunk_id in expected_doc_ids:
        return True
    if expected_doc_ids and doc_id in expected_doc_ids:
        return True
    if expected_source_urls:
        for pattern in expected_source_urls:
            if pattern and pattern in (source_url or ""):
                return True
    return False


def _check_keyword_hit(content: str, title: str, expected_keywords: list[str]) -> bool:
    if not expected_keywords:
        return True
    combined = (content or "") + " " + (title or "")
    return all(kw in combined for kw in expected_keywords)


def evaluate_query(
    qcase: dict,
    state: PipelineState,
    answer_text: str,
) -> dict:
    query_id = qcase["id"]
    query_text = qcase["query"]
    expected_doc_ids = qcase.get("expected_doc_ids") or []
    expected_source_urls = qcase.get("expected_source_urls") or []
    expected_keywords = qcase.get("expected_keywords") or []
    expected_answer_contains = qcase.get("expected_answer_contains") or []
    expected_source_types = set(qcase.get("expected_source_types") or [])
    forbidden_source_types = set(qcase.get("forbidden_source_types") or [])

    retrieved = _extract_retrieved_docs_info(state)
    reranked = _extract_reranked_docs_info(state)
    selected = _extract_selected_docs_info(state)

    # top-1/3/5 hit
    top1_hit = False
    top3_hit = False
    top5_hit = False

    for doc in retrieved[:1]:
        if _check_hit(doc["doc_id"], doc["source_url"], doc["chunk_id"], expected_doc_ids, expected_source_urls):
            top1_hit = True
    for doc in retrieved[:3]:
        if _check_hit(doc["doc_id"], doc["source_url"], doc["chunk_id"], expected_doc_ids, expected_source_urls):
            top3_hit = True
    for doc in retrieved[:5]:
        if _check_hit(doc["doc_id"], doc["source_url"], doc["chunk_id"], expected_doc_ids, expected_source_urls):
            top5_hit = True

    # selected_context_hit
    selected_context_hit = False
    for doc in selected:
        if _check_hit(doc["doc_id"], doc["source_url"], doc["chunk_id"], expected_doc_ids, expected_source_urls):
            selected_context_hit = True
        if expected_keywords and _check_keyword_hit(
            doc.get("content_preview", ""), doc.get("title", ""), expected_keywords
        ):
            selected_context_hit = True

    # expected_doc_ids/URL이 없으면 keyword 기반으로만 체크
    if not expected_doc_ids and not expected_source_urls:
        selected_context_hit = _any_keyword_hit_in_selected(selected, expected_keywords)
    # answer 텍스트에 expected_keywords가 있으면 context hit로 간주 (ground truth 스테일 방지)
    if not selected_context_hit and expected_keywords:
        if any(kw in (answer_text or "") for kw in expected_keywords):
            selected_context_hit = True

    # irrelevant_document_included
    irrelevant_included = False
    for doc in selected:
        st = doc.get("source_type", "")
        if st in forbidden_source_types:
            irrelevant_included = True
            break

    # answer_grounded_in_selected_context: 키워드 매칭 + expected_answer_contains 체크
    answer_grounded = _check_answer_grounded(answer_text, selected, expected_keywords)
    # expected_answer_contains 체크: 답변에 반드시 있어야 할 텍스트 검증
    answer_contains_hit = True
    if expected_answer_contains:
        answer_contains_hit = all(
            phrase in (answer_text or "") for phrase in expected_answer_contains
        )

    # 실패 단계 진단
    failure_stage = _diagnose_failure_stage(
        query_id=query_id,
        expected_doc_ids=expected_doc_ids,
        expected_source_urls=expected_source_urls,
        expected_keywords=expected_keywords,
        retrieved=retrieved,
        reranked=reranked,
        selected=selected,
        top5_hit=top5_hit,
        selected_context_hit=selected_context_hit,
        answer_grounded=answer_grounded,
        state=state,
    )

    return {
        "query_id": query_id,
        "query": query_text,
        "category": qcase.get("category"),
        "department": qcase.get("department"),
        # 파이프라인 핵심 필드
        "original_query": state.original_query,
        "normalized_query": state.normalized_query,
        "rewritten_query": state.rewritten_query,
        "intent": state.primary_intent,
        "keywords": state.keywords,
        "filters": state.filters,
        "retrieval_strategy": state.retrieval_strategy,
        "fallback_used": state.fallback_used,
        # 검색 결과 수
        "retrieved_count": len(retrieved),
        "reranked_count": len(reranked),
        "selected_count": len(selected),
        # 평가 지표
        "top1_hit": top1_hit,
        "top3_hit": top3_hit,
        "top5_hit": top5_hit,
        "selected_context_hit": selected_context_hit,
        "irrelevant_document_included": irrelevant_included,
        "answer_grounded_in_selected_context": answer_grounded,
        "answer_contains_hit": answer_contains_hit,
        # 세부 결과
        "top5_retrieved": retrieved[:5],
        "selected_chunks": selected,
        "answer_preview": (answer_text or "")[:300],
        # 실패 분류
        "failure_stage": failure_stage,
        # 메타
        "quality_info": state.metadata.get("retrieval_quality", {}),
        "query_understanding": state.metadata.get("query_understanding", {}),
    }


def _any_keyword_hit_in_selected(selected: list[dict], keywords: list[str]) -> bool:
    if not keywords:
        return len(selected) > 0
    for doc in selected:
        combined = doc.get("content_preview", "") + " " + doc.get("title", "")
        if any(kw in combined for kw in keywords):
            return True
    return False


def _check_answer_grounded(answer_text: str, selected: list[dict], expected_keywords: list[str]) -> bool:
    if not answer_text:
        return False
    # 답변에 "모릅니다", "찾을 수 없습니다" 등이 포함된 경우 → 실패로 처리
    not_found_phrases = ["모릅니다", "찾을 수 없", "알 수 없", "없습니다", "제공되지 않"]
    if any(p in answer_text for p in not_found_phrases):
        # selected가 비어있으면 정상 (모른다고 정직하게 답변)
        if not selected:
            return True
        # selected에 근거가 있는데 모른다고 하면 실패
        return False
    if not selected:
        return False
    # selected의 키워드 중 하나라도 답변에 있으면 grounded로 판단
    for doc in selected:
        title_words = (doc.get("title") or "").split()
        for w in title_words:
            if len(w) >= 2 and w in answer_text:
                return True
    if expected_keywords:
        return any(kw in answer_text for kw in expected_keywords)
    return True


def _diagnose_failure_stage(
    query_id: str,
    expected_doc_ids: list[str],
    expected_source_urls: list[str],
    expected_keywords: list[str],
    retrieved: list[dict],
    reranked: list[dict],
    selected: list[dict],
    top5_hit: bool,
    selected_context_hit: bool,
    answer_grounded: bool,
    state: PipelineState,
) -> str | None:
    has_gt = bool(expected_doc_ids or expected_source_urls or expected_keywords)
    if not has_gt:
        return None

    # 전처리 이상: 키워드가 없거나 normalized_query도 없음
    if not state.keywords and not state.normalized_query:
        return "query_preprocessing_issue"

    # retrieved에 아무것도 없으면 DB 데이터 품질 문제 가능성
    if not retrieved:
        return "db_data_quality_issue"

    # context_hit=True이면 답변 생성 단계만 남음
    if selected_context_hit:
        if not answer_grounded:
            return "answer_generation_issue"
        return None  # 통과

    # top5에도 없고 context_hit도 False: 검색 자체 실패
    if not top5_hit:
        # expected_doc_ids/expected_source_urls 없이 keyword 기반으로만 체크한 경우
        # keyword-only 평가에서 top5에 못 들었으면 soft miss (진단 불가)
        if not expected_doc_ids and not expected_source_urls:
            return None  # keyword-only 케이스는 진단 생략

        # branch_candidates로 lexical/vector 개별 결과 비교
        branch = state.metadata.get("retrieval_branch_candidates", {})
        lexical_branch = branch.get("lexical") or []
        vector_branch = branch.get("vector") or []
        lexical_hits = [
            d for d in lexical_branch
            if _check_hit(d.get("doc_id", ""), d.get("source_url", ""), d.get("chunk_id", ""), expected_doc_ids, expected_source_urls)
        ]
        vector_hits = [
            d for d in vector_branch
            if _check_hit(d.get("doc_id", ""), d.get("source_url", ""), d.get("chunk_id", ""), expected_doc_ids, expected_source_urls)
        ]
        if lexical_hits and not vector_hits:
            return "vector_search_issue"
        if vector_hits and not lexical_hits:
            return "lexical_search_issue"
        if lexical_hits and vector_hits:
            return "hybrid_merge_issue"
        # 둘 다 없으면 DB에 없거나 검색 자체 실패
        return "db_data_quality_issue"

    # top5에는 있는데 context_hit 없음
    if top5_hit and not selected_context_hit:
        reranked_hits = [
            d for d in reranked
            if _check_hit(d["doc_id"], d["source_url"], d["chunk_id"], expected_doc_ids, expected_source_urls)
        ]
        if not reranked_hits:
            return "rerank_issue"
        top3_reranked_hits = [d for d in reranked[:3] if d in reranked_hits]
        if top3_reranked_hits:
            return "topk_selector_issue"
        return "rerank_issue"

    return None  # 통과


def compute_summary(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {}

    def rate(key: str) -> float:
        return round(sum(1 for r in results if r.get(key)) / n, 3)

    failure_counts: dict[str, int] = {}
    for r in results:
        stage = r.get("failure_stage")
        if stage:
            failure_counts[stage] = failure_counts.get(stage, 0) + 1

    return {
        "total": n,
        "top1_hit_rate": rate("top1_hit"),
        "top3_hit_rate": rate("top3_hit"),
        "top5_hit_rate": rate("top5_hit"),
        "selected_context_hit_rate": rate("selected_context_hit"),
        "irrelevant_included_rate": rate("irrelevant_document_included"),
        "answer_grounded_rate": rate("answer_grounded_in_selected_context"),
        "answer_contains_hit_rate": rate("answer_contains_hit"),
        "fallback_used_rate": rate("fallback_used"),
        "failure_stage_counts": failure_counts,
    }


def save_results(results: list[dict], summary: dict, tag: str = "latest") -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = _RESULTS_DIR / f"retrieval_eval_{tag}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results, "generated_at": ts}, f, ensure_ascii=False, indent=2)
    print(f"[eval] JSON 저장: {json_path}")

    csv_path = _RESULTS_DIR / f"retrieval_eval_{tag}.csv"
    if results:
        flat_fields = [
            "query_id", "query", "category", "department",
            "normalized_query", "rewritten_query", "intent",
            "retrieval_strategy", "fallback_used",
            "retrieved_count", "selected_count",
            "top1_hit", "top3_hit", "top5_hit",
            "selected_context_hit", "irrelevant_document_included",
            "answer_grounded_in_selected_context", "answer_contains_hit",
            "failure_stage", "answer_preview",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=flat_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)
    print(f"[eval] CSV 저장: {csv_path}")


def print_summary(summary: dict) -> None:
    print("\n" + "=" * 60)
    print("=== Retrieval 평가 요약 ===")
    print("=" * 60)
    print(f"총 질문 수     : {summary.get('total', 0)}")
    print(f"Top-1 Hit Rate : {summary.get('top1_hit_rate', 0):.1%}")
    print(f"Top-3 Hit Rate : {summary.get('top3_hit_rate', 0):.1%}")
    print(f"Top-5 Hit Rate : {summary.get('top5_hit_rate', 0):.1%}")
    print(f"Context Hit    : {summary.get('selected_context_hit_rate', 0):.1%}")
    print(f"Irrelevant 포함: {summary.get('irrelevant_included_rate', 0):.1%}")
    print(f"답변 근거 일치 : {summary.get('answer_grounded_rate', 0):.1%}")
    print(f"답변 내용 포함 : {summary.get('answer_contains_hit_rate', 0):.1%}")
    print(f"Fallback 사용  : {summary.get('fallback_used_rate', 0):.1%}")
    print()
    failure_counts = summary.get("failure_stage_counts", {})
    if failure_counts:
        print("=== 실패 단계 분류 ===")
        for stage, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
            print(f"  {stage:<40} : {count}")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval 평가 스크립트")
    parser.add_argument("--query-id", help="특정 질문 ID만 평가 (예: q001)")
    parser.add_argument("--limit", type=int, help="최대 평가 질문 수")
    parser.add_argument("--tag", default="latest", help="결과 파일 태그")
    parser.add_argument(
        "--dataset",
        default=None,
        help="데이터셋 파일 경로 (기본: datasets/representative_queries.yaml). datasets/ 상대 경로 또는 절대 경로",
    )
    args = parser.parse_args()

    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.is_absolute():
            # datasets/ 접두사가 없으면 datasets 디렉토리 기준으로 해석
            if not str(dataset_path).startswith("datasets"):
                dataset_path = _DATASETS_DIR / dataset_path
            else:
                dataset_path = Path(__file__).parent / dataset_path
    else:
        dataset_path = _DATASET_PATH

    queries = load_queries(dataset_path)
    if args.query_id:
        queries = [q for q in queries if q["id"] == args.query_id]
        if not queries:
            print(f"[오류] query_id={args.query_id} 를 찾을 수 없습니다.")
            sys.exit(1)
    if args.limit:
        queries = queries[: args.limit]

    print(f"[eval] 평가 질문 수: {len(queries)}")
    print("[eval] 파이프라인 초기화 중...")

    pipeline = ChatPipeline()
    try:
        pipeline.initialize()
    except Exception as e:
        print(f"[경고] 임베더 초기화 실패 (벡터 검색 불가): {e}")

    results = []
    for i, qcase in enumerate(queries, 1):
        qid = qcase["id"]
        qtext = qcase["query"]
        print(f"[eval] ({i}/{len(queries)}) {qid}: {qtext!r}")
        t0 = time.perf_counter()
        try:
            answer, state = run_single_query(pipeline, qtext)
            elapsed = round((time.perf_counter() - t0) * 1000)
            result = evaluate_query(qcase, state, answer.answer if answer else "")
            result["elapsed_ms"] = elapsed
            # 핵심 지표 출력
            indicators = []
            if result["top1_hit"]:
                indicators.append("TOP1✓")
            if result["top3_hit"]:
                indicators.append("TOP3✓")
            if result["selected_context_hit"]:
                indicators.append("CTX✓")
            if result["irrelevant_document_included"]:
                indicators.append("IRRELEVANT!")
            if result["failure_stage"]:
                indicators.append(f"FAIL:{result['failure_stage']}")
            print(f"         → {' '.join(indicators) or 'MISS'} ({elapsed}ms)")
        except Exception as e:
            print(f"         → [에러] {e}")
            result = {
                "query_id": qid,
                "query": qtext,
                "category": qcase.get("category"),
                "department": qcase.get("department"),
                "error": str(e),
                "top1_hit": False,
                "top3_hit": False,
                "top5_hit": False,
                "selected_context_hit": False,
                "irrelevant_document_included": False,
                "answer_grounded_in_selected_context": False,
                "failure_stage": "pipeline_error",
                "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            }
        results.append(result)

    summary = compute_summary(results)
    print_summary(summary)
    save_results(results, summary, tag=args.tag)


if __name__ == "__main__":
    main()
