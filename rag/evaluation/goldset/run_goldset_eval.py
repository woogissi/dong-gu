"""동의대학교 RAG 골드셋 평가 스크립트.

골드셋을 RAG 파이프라인에 입력하여 retrieval 결과와 답변을 수집하고
질문별 Top-K Hit, Context Hit, Answer Grounded 등을 계산한다.

실행:
    docker compose run --rm rag python -m rag.evaluation.goldset.run_goldset_eval
    docker compose run --rm rag python -m rag.evaluation.goldset.run_goldset_eval --limit 10
    docker compose run --rm rag python -m rag.evaluation.goldset.run_goldset_eval --id G001
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.schemas.query import Query

_GOLDSET_PATH = Path(__file__).parent / "deu_rag_goldset.yaml"
_RESULTS_DIR = Path(__file__).parent
_RESULTS_DIR.mkdir(exist_ok=True)


def load_goldset(path: Path = _GOLDSET_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("goldset", [])


def _normalize_url(url: str) -> str:
    return url.rstrip("/").split("?")[0] if url else ""


def _url_has_path(url: str) -> bool:
    """정규화된 URL에 host 이후 경로가 있는지(= bare 도메인이 아닌지).

    bare 도메인(예: https://www.deu.ac.kr)을 gold_url로 두면 같은 도메인의
    무관한 페이지까지 부분문자열 매칭으로 Hit 처리되는 과대매칭(false positive)이
    발생한다. path가 없는 bare 도메인은 URL 부분매칭에서 제외하고 document_id로만
    매칭하도록 가드한다.
    """
    no_scheme = re.sub(r"^https?://", "", url or "").rstrip("/")
    return "/" in no_scheme


def _check_hit(doc_id: str, source_url: str, chunk_id: str, gold_documents: list[dict]) -> bool:
    for gold in gold_documents:
        gold_doc_id = gold.get("document_id", "")
        gold_url = gold.get("url", "")
        if gold_doc_id and (doc_id == gold_doc_id or chunk_id.startswith(gold_doc_id)):
            return True
        if gold_url:
            gold_url_norm = _normalize_url(gold_url)
            # 가드: bare 도메인(path 없음)은 URL 부분매칭 금지 → document_id로만 매칭
            if gold_url_norm and _url_has_path(gold_url_norm) and gold_url_norm in (source_url or ""):
                return True
    return False


def _extract_docs(docs_list) -> list[dict]:
    result = []
    for i, doc in enumerate(docs_list or []):
        meta = doc.metadata or {}
        signals = meta.get("rerank_signals") or {}
        result.append({
            "rank": i + 1,
            "doc_id": doc.doc_id,
            "chunk_id": doc.chunk_id,
            "title": doc.title,
            "source_url": doc.source,
            "source_type": meta.get("source_type", ""),
            "score": doc.score,
            "lexical_score": meta.get("lexical_score"),
            "vector_score": meta.get("vector_score"),
            "rerank_score": meta.get("rerank_score"),
            "noise_score": signals.get("noise_score"),
            "content_preview": (doc.content or "")[:200],
        })
    return result


_NOT_FOUND_PHRASES = [
    "모릅니다", "찾을 수 없", "알 수 없", "정보는 확인할 수 없",
    "확인되지 않습니다", "제공되지 않", "찾지 못했", "찾을 수 없었",
    "정보를 찾지", "정보가 없", "답변을 제공할 수 없",
    # 정직한 '정보 없음' 변형(거절로 분류돼야 하나 기존 목록에서 누락되던 표현)
    "포함되어 있지 않", "포함하고 있지 않", "나와 있지 않", "나와있지 않",
    "기재되어 있지 않", "언급이 없", "언급은 없", "확인할 수 없",
]

# 구체 정보 없이 다음 단계만 안내하는 상투구 — 실질 내용 판정에서 제외한다.
_GUIDANCE_PHRASES = ["문의", "홈페이지", "웹사이트", "확인해", "확인하시", "방문", "참고하시"]


def _contains_not_found_phrase(text: str) -> bool:
    return any(p in (text or "") for p in _NOT_FOUND_PHRASES)


def _substantive_residual(answer: str) -> str:
    """부정 문장과 안내성 상투구 문장을 제거하고 남은 실질 내용을 반환한다.

    답변에 '찾을 수 없다'가 섞여 있어도, 그 외에 구체 정보가 남아 있으면 부분답변이다.
    반대로 부정 문장과 '부서에 문의하세요' 류만 남으면 실질 내용이 없는 거절이다.
    """
    parts = re.split(r"(?<=[.!?。\n])", answer or "")
    kept: list[str] = []
    for sentence in parts:
        stripped = sentence.strip()
        if not stripped:
            continue
        if _contains_not_found_phrase(stripped):
            continue
        if any(g in stripped for g in _GUIDANCE_PHRASES):
            continue
        kept.append(stripped)
    return re.sub(r"\s+", " ", " ".join(kept)).strip()


def _is_refusal(answer: str) -> bool:
    """답변이 '모른다/찾을 수 없다' 류의 거부 응답인지 판정.

    부정 표현이 없으면 거절이 아니고, 부정 표현이 있어도 부정·안내 문장을 걷어낸
    실질 내용이 충분히 남으면 부분답변으로 보아 거절이 아니다(표현 민감도 완화).
    """
    if not answer:
        return False
    if not _contains_not_found_phrase(answer):
        return False
    return len(_substantive_residual(answer)) < 20


def _check_answer_grounded(answer: str, selected: list[dict]) -> bool:
    """답변이 검색 컨텍스트에 근거하는지 판정.

    RAG 파이프라인은 selected context로만 답변을 생성하므로,
    거부 응답이 아니면서 구체적 답변을 냈다면 grounded로 간주한다.
    거부 응답인데 selected context가 있으면 근거를 활용하지 못한 것이므로 실패.
    """
    if not answer:
        return False
    if _is_refusal(answer):
        # selected가 없으면 정직한 거부(정상), 있으면 근거 미활용(실패)
        return not selected
    # 거부가 아니고 답변이 충분히 구체적이면 근거 기반으로 간주
    return len(answer.strip()) >= 10


def _diagnose_failure(
    gold_documents: list[dict],
    retrieved: list[dict],
    reranked: list[dict],
    selected: list[dict],
    top5_hit: bool,
    context_hit: bool,
    answer_grounded: bool,
    state: PipelineState,
) -> str | None:
    if not gold_documents:
        return None
    if not state.keywords and not state.normalized_query:
        return "query_preprocessing_issue"
    if not retrieved:
        return "db_data_quality_issue"
    if context_hit:
        return None if answer_grounded else "answer_generation_issue"
    if not top5_hit:
        branch = state.metadata.get("retrieval_branch_candidates", {})
        lex = [d for d in (branch.get("lexical") or []) if _check_hit(d.get("doc_id",""), d.get("source_url",""), d.get("chunk_id",""), gold_documents)]
        vec = [d for d in (branch.get("vector") or []) if _check_hit(d.get("doc_id",""), d.get("source_url",""), d.get("chunk_id",""), gold_documents)]
        if lex and not vec:
            return "vector_search_issue"
        if vec and not lex:
            return "lexical_search_issue"
        if lex and vec:
            return "hybrid_merge_issue"
        return "db_data_quality_issue"
    # top5에는 있는데 context_hit 없음
    reranked_hits = [d for d in reranked if _check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold_documents)]
    if not reranked_hits:
        return "rerank_issue"
    if any(d in reranked_hits for d in reranked[:3]):
        return "topk_selector_issue"
    return "rerank_issue"


def _check_answer_correct(answer: str, gold_documents: list[dict]) -> bool:
    """evidence_text의 핵심 토큰이 답변에 포함되는지로 답변 정확도를 근사 판정.

    거부 응답이면 즉시 실패. evidence_text에서 숫자/한글 명사 토큰을 추출해
    30% 이상이 답변에 나타나면 정답으로 간주한다(완벽하지 않은 휴리스틱).
    """
    if not answer or _is_refusal(answer):
        return False

    tokens: list[str] = []
    for gold in gold_documents:
        ev = gold.get("evidence_text") or ""
        # 숫자(날짜/전화/금액 등) + 2글자 이상 한글 단어
        tokens += re.findall(r"\d[\d,~:\-./]*\d|\d", ev)
        tokens += [w for w in re.findall(r"[가-힣]{2,}", ev)]
    # 의미 없는 빈출 조사/접미 제거
    stop = {"포함", "안내", "위치", "방법", "기간", "신청", "확인", "페이지", "문서", "관련"}
    tokens = [t for t in tokens if t not in stop]
    if not tokens:
        return None  # evidence가 비어있으면 판정 불가
    hits = sum(1 for t in set(tokens) if t in answer)
    return hits / len(set(tokens)) >= 0.3


def evaluate_case(case: dict, state: PipelineState, answer_text: str) -> dict:
    gold_documents = case.get("gold_documents") or []
    retrieved = _extract_docs(state.retrieved_docs)
    reranked = _extract_docs(state.reranked_docs)
    selected = _extract_docs(state.selected_docs)

    top1_hit = any(_check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold_documents) for d in retrieved[:1])
    top3_hit = any(_check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold_documents) for d in retrieved[:3])
    top5_hit = any(_check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold_documents) for d in retrieved[:5])
    context_hit = any(_check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold_documents) for d in selected)

    answer_grounded = _check_answer_grounded(answer_text, selected)
    answer_refused = _is_refusal(answer_text)
    answer_correct = _check_answer_correct(answer_text, gold_documents)

    expected_answer_summary = case.get("expected_answer_summary", "")
    answer_contains_expected = bool(expected_answer_summary) and (
        any(kw in answer_text for kw in expected_answer_summary.split()[:5]) if answer_text else False
    )

    failure_stage = _diagnose_failure(
        gold_documents, retrieved, reranked, selected,
        top5_hit, context_hit, answer_grounded, state
    )

    return {
        "id": case["id"],
        "category": case.get("category"),
        "question": case.get("question"),
        "difficulty": case.get("difficulty"),
        "source_type": case.get("source_type"),
        "answer_type": case.get("answer_type"),
        # 파이프라인 정보
        "original_query": state.original_query,
        "normalized_query": state.normalized_query,
        "rewritten_query": state.rewritten_query,
        "intent": state.primary_intent,
        "keywords": state.keywords,
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
        "context_hit": context_hit,
        "answer_grounded": answer_grounded,
        "answer_refused": answer_refused,
        "answer_correct": answer_correct,
        "answer_contains_expected": answer_contains_expected,
        "irrelevant_included": False,
        # 세부 결과
        "top5_retrieved": retrieved[:5],
        "selected_chunks": selected,
        "generated_answer": answer_text,
        "answer_preview": (answer_text or "")[:300],
        # 실패 분류
        "failure_stage": failure_stage,
        # 골드 문서
        "gold_documents": gold_documents,
        # 메타
        "quality_info": state.metadata.get("retrieval_quality", {}),
    }


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

    by_category: dict[str, dict] = {}
    for r in results:
        cat = r.get("category") or "unknown"
        if cat not in by_category:
            by_category[cat] = {"total": 0, "top5_hit": 0, "context_hit": 0}
        by_category[cat]["total"] += 1
        if r.get("top5_hit"):
            by_category[cat]["top5_hit"] += 1
        if r.get("context_hit"):
            by_category[cat]["context_hit"] += 1

    by_difficulty: dict[str, dict] = {}
    for r in results:
        diff = r.get("difficulty") or "unknown"
        if diff not in by_difficulty:
            by_difficulty[diff] = {"total": 0, "context_hit": 0}
        by_difficulty[diff]["total"] += 1
        if r.get("context_hit"):
            by_difficulty[diff]["context_hit"] += 1

    # answer_correct는 None(판정 불가) 제외하고 비율 계산
    correct_judgable = [r for r in results if r.get("answer_correct") is not None]
    answer_correct_rate = (
        round(sum(1 for r in correct_judgable if r.get("answer_correct")) / len(correct_judgable), 3)
        if correct_judgable else None
    )

    return {
        "total": n,
        "top1_hit_rate": rate("top1_hit"),
        "top3_hit_rate": rate("top3_hit"),
        "top5_hit_rate": rate("top5_hit"),
        "context_hit_rate": rate("context_hit"),
        "answer_grounded_rate": rate("answer_grounded"),
        "answer_refused_rate": rate("answer_refused"),
        "answer_correct_rate": answer_correct_rate,
        "answer_correct_judgable": len(correct_judgable),
        "fallback_used_rate": rate("fallback_used"),
        "failure_stage_counts": failure_counts,
        "by_category": by_category,
        "by_difficulty": by_difficulty,
    }


def save_results(results: list[dict], summary: dict) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = _RESULTS_DIR / "goldset_eval_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results, "generated_at": ts}, f, ensure_ascii=False, indent=2)
    print(f"[goldset] JSON 저장: {json_path}")

    csv_path = _RESULTS_DIR / "goldset_eval_results.csv"
    flat_fields = [
        "id", "category", "difficulty", "source_type",
        "question", "intent", "retrieval_strategy", "fallback_used",
        "retrieved_count", "selected_count",
        "top1_hit", "top3_hit", "top5_hit", "context_hit",
        "answer_grounded", "answer_correct", "answer_refused",
        "failure_stage", "answer_preview",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=flat_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    print(f"[goldset] CSV 저장: {csv_path}")

    _generate_report(results, summary)
    _generate_failure_cases(results)


def _generate_report(results: list[dict], summary: dict) -> None:
    lines = [
        "# RAG Goldset Evaluation Report",
        f"",
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## 1. 생성된 테스트셋",
        f"",
        f"- 총 질문 수: {summary['total']}",
        f"- 웹페이지 기반 질문: {sum(1 for r in results if r.get('source_type') == 'web')}",
        f"- DB 기반 질문: {sum(1 for r in results if r.get('source_type') == 'db')}",
        f"- 첨부파일 기반 질문: {sum(1 for r in results if r.get('source_type') == 'attachment')}",
        f"- 카테고리 수: {len(set(r.get('category','') for r in results))}",
        f"",
        f"## 2. 평가 결과",
        f"",
        f"| Metric | Result |",
        f"|---|---:|",
        f"| Top-1 Hit | {summary.get('top1_hit_rate', 0):.1%} |",
        f"| Top-3 Hit | {summary.get('top3_hit_rate', 0):.1%} |",
        f"| Top-5 Hit | {summary.get('top5_hit_rate', 0):.1%} |",
        f"| Context Hit | {summary.get('context_hit_rate', 0):.1%} |",
        f"| Answer Grounded | {summary.get('answer_grounded_rate', 0):.1%} |",
        f"| Answer Correct (evidence 기반) | "
        + (f"{summary.get('answer_correct_rate'):.1%} (판정가능 {summary.get('answer_correct_judgable', 0)}건)" if summary.get('answer_correct_rate') is not None else "N/A")
        + " |",
        f"| Answer Refused | {summary.get('answer_refused_rate', 0):.1%} |",
        f"| Fallback Used | {summary.get('fallback_used_rate', 0):.1%} |",
        f"",
        f"## 3. 카테고리별 결과",
        f"",
        f"| 카테고리 | 총수 | Top5 Hit | Context Hit |",
        f"|---|---:|---:|---:|",
    ]
    for cat, stats in sorted(summary.get("by_category", {}).items()):
        t = stats["total"]
        t5 = stats["top5_hit"]
        ctx = stats["context_hit"]
        lines.append(f"| {cat} | {t} | {t5}/{t} ({t5/t:.0%}) | {ctx}/{t} ({ctx/t:.0%}) |")

    lines += [
        f"",
        f"## 4. 난이도별 결과",
        f"",
        f"| 난이도 | 총수 | Context Hit |",
        f"|---|---:|---:|",
    ]
    for diff, stats in sorted(summary.get("by_difficulty", {}).items()):
        t = stats["total"]
        ctx = stats["context_hit"]
        lines.append(f"| {diff} | {t} | {ctx}/{t} ({ctx/t:.0%}) |")

    lines += [
        f"",
        f"## 5. 주요 실패 원인",
        f"",
        f"| Failure Stage | Count |",
        f"|---|---:|",
    ]
    for stage, cnt in sorted(summary.get("failure_stage_counts", {}).items(), key=lambda x: -x[1]):
        lines.append(f"| {stage} | {cnt} |")

    lines += [
        f"",
        f"## 6. 개선 우선순위",
        f"",
    ]
    failure_counts = summary.get("failure_stage_counts", {})
    sorted_failures = sorted(failure_counts.items(), key=lambda x: -x[1])
    for i, (stage, cnt) in enumerate(sorted_failures[:5], 1):
        lines.append(f"{i}. **{stage}** ({cnt}건) — 해당 단계 검토 필요")

    report_path = Path(__file__).parent / "goldset_eval_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[goldset] 보고서 저장: {report_path}")


def _generate_failure_cases(results: list[dict]) -> None:
    failed = [r for r in results if r.get("failure_stage") or not r.get("context_hit")]
    lines = [
        "# RAG Goldset Failure Cases",
        f"",
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"총 실패 케이스: {len(failed)}",
        f"",
    ]
    for r in failed:
        gold_docs = r.get("gold_documents") or []
        gold_info = "\n".join(
            f"  - [{g.get('title','')}]({g.get('url','')})" + (f" (doc_id: {g.get('document_id','')})" if g.get('document_id') else "")
            for g in gold_docs
        )
        retrieved_info = "\n".join(
            f"  - rank {d['rank']}: [{d.get('title','')}]({d.get('source_url','')}) (score={d.get('score',0):.3f})"
            for d in (r.get("top5_retrieved") or [])[:3]
        )
        lines += [
            f"---",
            f"",
            f"### {r['id']}: {r.get('question','')}",
            f"",
            f"- **카테고리**: {r.get('category','')} | **난이도**: {r.get('difficulty','')} | **소스**: {r.get('source_type','')}",
            f"- **실패 단계**: `{r.get('failure_stage') or 'context_miss'}`",
            f"- **Top5 Hit**: {r.get('top5_hit',False)} | **Context Hit**: {r.get('context_hit',False)}",
            f"",
            f"**정답 문서:**",
            gold_info or "  (없음)",
            f"",
            f"**검색된 문서 (상위 3개):**",
            retrieved_info or "  (검색 결과 없음)",
            f"",
            f"**생성 답변 (앞 200자):**",
            f"```",
            (r.get("answer_preview") or "")[:200],
            f"```",
            f"",
        ]

    failure_path = Path(__file__).parent / "failure_cases.md"
    with open(failure_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[goldset] 실패 케이스 저장: {failure_path}")


def print_summary(summary: dict) -> None:
    print("\n" + "=" * 60)
    print("=== 골드셋 평가 요약 ===")
    print("=" * 60)
    print(f"총 질문 수     : {summary.get('total', 0)}")
    print(f"Top-1 Hit Rate : {summary.get('top1_hit_rate', 0):.1%}")
    print(f"Top-3 Hit Rate : {summary.get('top3_hit_rate', 0):.1%}")
    print(f"Top-5 Hit Rate : {summary.get('top5_hit_rate', 0):.1%}")
    print(f"Context Hit    : {summary.get('context_hit_rate', 0):.1%}")
    print(f"Answer Grounded: {summary.get('answer_grounded_rate', 0):.1%}")
    acr = summary.get('answer_correct_rate')
    if acr is not None:
        print(f"Answer Correct : {acr:.1%} (판정가능 {summary.get('answer_correct_judgable', 0)}건)")
    print(f"Answer Refused : {summary.get('answer_refused_rate', 0):.1%}")
    print(f"Fallback 사용  : {summary.get('fallback_used_rate', 0):.1%}")
    print()
    fc = summary.get("failure_stage_counts", {})
    if fc:
        print("=== 실패 단계 분류 ===")
        for stage, cnt in sorted(fc.items(), key=lambda x: -x[1]):
            print(f"  {stage:<42}: {cnt}")
    print("=" * 60)


def convert_to_jsonl(goldset: list[dict]) -> None:
    jsonl_path = _RESULTS_DIR / "deu_rag_goldset.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for item in goldset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[goldset] JSONL 저장: {jsonl_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="골드셋 평가 스크립트")
    parser.add_argument("--id", help="특정 케이스 ID만 평가 (예: G001)")
    parser.add_argument("--limit", type=int, help="최대 평가 케이스 수")
    parser.add_argument("--jsonl-only", action="store_true", help="JSONL 변환만 수행")
    args = parser.parse_args()

    goldset = load_goldset()
    print(f"[goldset] 로드된 케이스 수: {len(goldset)}")

    convert_to_jsonl(goldset)

    if args.jsonl_only:
        print("[goldset] JSONL 변환 완료. 평가 생략.")
        return

    if args.id:
        goldset = [c for c in goldset if c["id"] == args.id]
        if not goldset:
            print(f"[오류] ID={args.id} 를 찾을 수 없습니다.")
            sys.exit(1)
    if args.limit:
        goldset = goldset[:args.limit]

    print(f"[goldset] 평가 케이스 수: {len(goldset)}")
    print("[goldset] 파이프라인 초기화 중...")

    pipeline = ChatPipeline()
    try:
        pipeline.initialize()
    except Exception as e:
        print(f"[경고] 임베더 초기화 실패 (벡터 검색 불가): {e}")

    results = []
    for i, case in enumerate(goldset, 1):
        cid = case["id"]
        question = case["question"]
        print(f"[goldset] ({i}/{len(goldset)}) {cid}: {question!r}")
        t0 = time.perf_counter()
        try:
            q = Query(text=question)
            answer = pipeline.run(q)
            state = pipeline.last_state
            elapsed = round((time.perf_counter() - t0) * 1000)
            result = evaluate_case(case, state, answer.answer if answer else "")
            result["elapsed_ms"] = elapsed

            indicators = []
            if result["top1_hit"]:
                indicators.append("TOP1✓")
            elif result["top3_hit"]:
                indicators.append("TOP3✓")
            elif result["top5_hit"]:
                indicators.append("TOP5✓")
            if result["context_hit"]:
                indicators.append("CTX✓")
            if result["failure_stage"]:
                indicators.append(f"FAIL:{result['failure_stage']}")
            print(f"         → {' '.join(indicators) or 'MISS'} ({elapsed}ms)")
        except Exception as e:
            elapsed = round((time.perf_counter() - t0) * 1000)
            print(f"         → [에러] {e}")
            result = {
                "id": cid, "category": case.get("category"),
                "question": question, "error": str(e),
                "top1_hit": False, "top3_hit": False, "top5_hit": False,
                "context_hit": False, "answer_grounded": False,
                "failure_stage": "pipeline_error", "elapsed_ms": elapsed,
                "gold_documents": case.get("gold_documents", []),
            }
        results.append(result)

    summary = compute_summary(results)
    print_summary(summary)
    save_results(results, summary)


if __name__ == "__main__":
    main()
