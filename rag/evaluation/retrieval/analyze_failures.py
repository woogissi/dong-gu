"""실패 케이스 자동 분류 및 분석 스크립트.

실행:
    docker compose run --rm rag python -m rag.evaluation.retrieval.analyze_failures
    docker compose run --rm rag python -m rag.evaluation.retrieval.analyze_failures --input results/retrieval_eval_latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_RESULTS_DIR = Path(__file__).parent / "results"

FAILURE_STAGE_DESCRIPTIONS = {
    "query_preprocessing_issue": (
        "질문 전처리 문제: normalized_query 또는 rewritten_query가 이상하거나 키워드 추출이 실패함. "
        "preprocessor.py, domain_knowledge.py, query_features.py를 점검하라."
    ),
    "db_data_quality_issue": (
        "DB 데이터 품질 문제: 정답 문서/본문/첨부 텍스트가 DB에 없음. "
        "크롤러 재실행 또는 해당 URL 직접 재파싱이 필요함."
    ),
    "lexical_search_issue": (
        "Lexical 검색 문제: BM25/full-text search로 정답을 찾지 못함. "
        "retriever.py의 토큰화, stopwords, 쿼리 확장을 점검하라."
    ),
    "vector_search_issue": (
        "Vector 검색 문제: 임베딩 검색으로 정답을 찾지 못함. "
        "임베딩 모델, 쿼리 전처리, DB 벡터 품질을 점검하라."
    ),
    "hybrid_merge_issue": (
        "Hybrid 병합 문제: lexical/vector 개별 결과에는 있지만 병합 후 순위에서 밀림. "
        "RRF 가중치, HYBRID_SCORE_MODE 설정을 점검하라."
    ),
    "rerank_issue": (
        "Reranking 문제: retrieved에는 있지만 rerank 후 순위가 내려감. "
        "reranker.py의 감점/가점 규칙, 노이즈 패널티를 점검하라."
    ),
    "topk_selector_issue": (
        "TopK 선택 문제: reranked 상위에 있지만 selected에서 제외됨. "
        "topk_selector.py의 중복 제거, 오염 감지 규칙을 점검하라."
    ),
    "answer_generation_issue": (
        "답변 생성 문제: selected context에 근거가 있지만 답변이 틀리거나 모른다고 답변함. "
        "prompt_builder.py, answer_generator.py를 점검하라."
    ),
    "pipeline_error": (
        "파이프라인 실행 오류: 예외가 발생하여 평가 자체가 불가능함."
    ),
}

RECOMMENDED_CHANGES: dict[str, list[str]] = {
    "query_preprocessing_issue": [
        "rag/pipeline/preprocessor.py: 정규화 규칙 확인",
        "rag/preprocess/domain_knowledge.py: 동의어/별칭 등록 확인",
        "rag/preprocess/query_features.py: 키워드 추출 로직 확인",
    ],
    "db_data_quality_issue": [
        "크롤러: 해당 URL 재크롤링 필요",
        "crawler/crawler/run/run_retry_failed_documents.py: 실패 문서 재처리",
        "DB 점검: SELECT * FROM chunks WHERE source_url LIKE '%<url>%'",
    ],
    "lexical_search_issue": [
        "rag/retrieval/retriever.py: _DB_SEARCH_STOPWORDS 조정",
        "rag/retrieval/retriever.py: _FAMILY_SEARCH_EXPANSIONS 키워드 추가",
        "rag/pipeline/preprocessor.py: 키워드 확장 강화",
    ],
    "vector_search_issue": [
        "rag/embedding/koe5_embedder.py: 임베딩 쿼리 텍스트 확인",
        "rag/pipeline/chat_pipeline.py: _embed_query에서 사용하는 query_text 확인",
        "DB: 해당 chunk의 embedding이 NULL인지 확인",
    ],
    "hybrid_merge_issue": [
        "rag/retrieval/retriever.py: _HYBRID_* 가중치 조정",
        ".env: HYBRID_SCORE_MODE, HYBRID_LEXICAL_WEIGHT 튜닝",
        "rag/retrieval/retriever.py: RRF k 파라미터 조정",
    ],
    "rerank_issue": [
        "rag/selection/reranker.py: 감점 규칙 완화 또는 가점 규칙 강화",
        "rag/selection/reranker.py: query_family_boost 점수 조정",
        "rag/selection/reranker.py: 노이즈 패널티 임계값 조정",
    ],
    "topk_selector_issue": [
        "rag/selection/topk_selector.py: context_contamination 임계값 조정",
        "rag/selection/topk_selector.py: source_type_diversity 규칙 완화",
        "rag/selection/topk_selector.py: max_chunks_per_doc 값 확인",
    ],
    "answer_generation_issue": [
        "rag/prompt/prompt_builder.py: 프롬프트 지시사항 보강",
        "rag/generation/answer_postprocessor.py: negative repair 조건 점검",
        "rag/llm/answer_generator.py: system_prompt 근거 강조 문구 추가",
    ],
}


def load_results(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def analyze_failures(results: list[dict]) -> list[dict]:
    failures = []
    for r in results:
        if r.get("failure_stage") or not r.get("selected_context_hit"):
            failures.append(r)
    return failures


def format_failure_report(failure: dict) -> str:
    lines = []
    lines.append(f"Query ID  : {failure.get('query_id', '-')}")
    lines.append(f"Query     : {failure.get('query', '-')}")
    lines.append(f"Category  : {failure.get('category', '-')}")
    lines.append(f"Department: {failure.get('department', '-')}")
    lines.append(f"Intent    : {failure.get('intent', '-')}")
    lines.append(f"Strategy  : {failure.get('retrieval_strategy', '-')}")
    lines.append(f"Fallback  : {failure.get('fallback_used', False)}")
    lines.append(f"Normalized: {failure.get('normalized_query', '-')}")
    lines.append(f"Rewritten : {failure.get('rewritten_query', '-')}")
    lines.append(f"Keywords  : {failure.get('keywords', [])}")
    lines.append(f"Filters   : {failure.get('filters', {})}")
    lines.append("")

    lines.append("Top 5 Retrieved:")
    for doc in (failure.get("top5_retrieved") or [])[:5]:
        lines.append(
            f"  [{doc.get('rank')}] {doc.get('chunk_id', '-')} | {doc.get('title', '-')[:40]} "
            f"| score={doc.get('score', 0):.4f} | {doc.get('source_type', '-')}"
        )

    lines.append("")
    lines.append("Selected Chunks:")
    for doc in (failure.get("selected_chunks") or []):
        lines.append(
            f"  [{doc.get('rank')}] {doc.get('chunk_id', '-')} | {doc.get('title', '-')[:40]} "
            f"| rerank_score={doc.get('rerank_score', 0)}"
        )

    lines.append("")
    lines.append(f"Top-1 Hit : {failure.get('top1_hit', False)}")
    lines.append(f"Top-3 Hit : {failure.get('top3_hit', False)}")
    lines.append(f"Top-5 Hit : {failure.get('top5_hit', False)}")
    lines.append(f"CTX Hit   : {failure.get('selected_context_hit', False)}")
    lines.append(f"Irrelevant: {failure.get('irrelevant_document_included', False)}")
    lines.append(f"Grounded  : {failure.get('answer_grounded_in_selected_context', False)}")

    stage = failure.get("failure_stage")
    lines.append("")
    lines.append(f"Failure Stage: {stage or 'None (soft miss)'}")
    if failure.get("error"):
        lines.append(f"Error: {failure['error']}")
    if stage and stage in FAILURE_STAGE_DESCRIPTIONS:
        lines.append(f"Root Cause: {FAILURE_STAGE_DESCRIPTIONS[stage]}")
    if stage and stage in RECOMMENDED_CHANGES:
        lines.append("Recommended Changes:")
        for change in RECOMMENDED_CHANGES[stage]:
            lines.append(f"  - {change}")

    lines.append(f"Answer Preview: {failure.get('answer_preview', '-')[:200]}")
    return "\n".join(lines)


def group_by_stage(failures: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for f in failures:
        stage = f.get("failure_stage") or "soft_miss"
        groups.setdefault(stage, []).append(f)
    return groups


def print_analysis(data: dict) -> None:
    summary = data.get("summary", {})
    results = data.get("results", [])
    failures = analyze_failures(results)

    print("\n" + "=" * 70)
    print("=== Retrieval 실패 케이스 분석 보고서 ===")
    print("=" * 70)
    print(f"총 평가 질문수  : {summary.get('total', len(results))}")
    print(f"실패/누락 케이스: {len(failures)}")
    print(f"Top-1 Hit Rate  : {summary.get('top1_hit_rate', 0):.1%}")
    print(f"Top-5 Hit Rate  : {summary.get('top5_hit_rate', 0):.1%}")
    print(f"Context Hit     : {summary.get('selected_context_hit_rate', 0):.1%}")
    print()

    groups = group_by_stage(failures)
    print("=== 실패 단계별 분류 ===")
    for stage, cases in sorted(groups.items(), key=lambda x: -len(x[1])):
        desc = FAILURE_STAGE_DESCRIPTIONS.get(stage, "")
        print(f"\n[{stage}] — {len(cases)}건")
        if desc:
            print(f"  설명: {desc[:120]}")
        if stage in RECOMMENDED_CHANGES:
            print("  권장 수정:")
            for ch in RECOMMENDED_CHANGES[stage]:
                print(f"    - {ch}")
        for f in cases[:3]:  # 최대 3건만 상세 출력
            print(f"\n  --- {f.get('query_id')}: {f.get('query')!r} ---")
            print(f"  Strategy={f.get('retrieval_strategy')} Fallback={f.get('fallback_used')}")
            print(f"  Retrieved={f.get('retrieved_count', 0)} Selected={f.get('selected_count', 0)}")
            top5 = f.get("top5_retrieved") or []
            if top5:
                print(f"  Top-1: {top5[0].get('chunk_id', '-')} | {top5[0].get('title', '-')[:40]}")
            selected = f.get("selected_chunks") or []
            if selected:
                print(f"  Selected[0]: {selected[0].get('chunk_id', '-')} | {selected[0].get('title', '-')[:40]}")

    print("\n" + "=" * 70)
    print("=== 전체 실패 케이스 상세 ===")
    print("=" * 70)
    for i, failure in enumerate(failures, 1):
        print(f"\n{'='*60}")
        print(f"[실패 케이스 #{i}]")
        print(format_failure_report(failure))


def save_failure_report(failures: list[dict], tag: str = "latest") -> None:
    out_path = _RESULTS_DIR / f"failure_analysis_{tag}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "failure_count": len(failures),
                "failures": failures,
                "stage_descriptions": FAILURE_STAGE_DESCRIPTIONS,
                "recommended_changes": RECOMMENDED_CHANGES,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n[분석] 실패 케이스 저장: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="실패 케이스 분석")
    parser.add_argument(
        "--input",
        default=str(_RESULTS_DIR / "retrieval_eval_latest.json"),
        help="평가 결과 JSON 경로",
    )
    parser.add_argument("--tag", default="latest", help="출력 파일 태그")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[오류] 결과 파일이 없습니다: {input_path}")
        print("먼저 evaluate_retrieval.py를 실행하세요.")
        sys.exit(1)

    data = load_results(input_path)
    results = data.get("results", [])
    failures = analyze_failures(results)

    print_analysis(data)
    save_failure_report(failures, tag=args.tag)


if __name__ == "__main__":
    main()
