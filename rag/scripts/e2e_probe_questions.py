"""Run representative questions through the full RAG pipeline and summarize failures."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query


DEFAULT_QUESTIONS = [
    "컴퓨터공학과 2학년 이수표 교육과정",
    "컴퓨터공학과 3학년 이수표",
    "전자공학과 3학년 이수표",
    "게임공학과 4학년 교육과정",
    "인간공학과 2학년 이수표",
    "존재하지않는학과 2학년 이수표",
    "수강신청 기간 알려줘",
    "26년 1학기 보강일정",
    "동의대학교 주소 알려줘",
    "동의대 정보공학관 위치",
    "정보공학관 편의점 위치",
    "동의대 7대 총장 정보",
    "성적우수장학금 선발기준 알려줘",
    "재학증명서 발급 방법",
]


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))


def _doc_summary(doc: Any) -> dict[str, Any]:
    metadata = getattr(doc, "metadata", {}) or {}
    return {
        "doc_id": getattr(doc, "doc_id", ""),
        "chunk_id": getattr(doc, "chunk_id", ""),
        "title": getattr(doc, "title", ""),
        "source": getattr(doc, "source", ""),
        "source_type": metadata.get("source_type"),
        "section_type": metadata.get("section_type"),
        "section_title": metadata.get("section_title"),
        "score": getattr(doc, "score", None),
        "rerank_score": metadata.get("rerank_score"),
        "vector_score": metadata.get("vector_score"),
        "lexical_score": metadata.get("lexical_score"),
    }


def _run_one(pipeline: ChatPipeline, question: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        answer = pipeline.run(Query(text=question))
        state = pipeline.last_state
        metadata = getattr(state, "metadata", {}) if state else {}
        selection_quality = metadata.get("selection_quality") if isinstance(metadata, dict) else None
        retrieval_quality = metadata.get("retrieval_quality") if isinstance(metadata, dict) else None
        selected_docs = getattr(state, "selected_docs", []) if state else []
        retrieved_docs = getattr(state, "retrieved_docs", []) if state else []
        answer_text = getattr(answer, "answer", "") or ""
        status = "ok"
        issues: list[str] = []
        if not getattr(answer, "success", False):
            status = "failed"
            issues.append("answer_success_false")
        no_answer_markers = (
            "관련 정보를 찾지 못",
            "확인할 수 없습니다",
            "확인되지 않습니다",
            "공식 웹사이트를 통해 확인",
        )
        if any(marker in answer_text for marker in no_answer_markers):
            status = "needs_review"
            issues.append("no_relevant_info_answer")
        if not selected_docs and getattr(state, "primary_intent", "INFO") == "INFO":
            status = "failed"
            issues.append("no_selected_docs")
        if isinstance(selection_quality, dict) and selection_quality.get("selected_context_contamination"):
            status = "needs_review"
            issues.append("selected_context_contamination")

        return {
            "question": question,
            "status": status,
            "issues": issues,
            "elapsed_ms": _elapsed_ms(started),
            "success": getattr(answer, "success", None),
            "primary_intent": getattr(state, "primary_intent", None) if state else None,
            "retrieval_strategy": getattr(state, "retrieval_strategy", None) if state else None,
            "fallback_used": bool(getattr(state, "fallback_used", False)) if state else None,
            "retrieved_doc_count": len(retrieved_docs or []),
            "selected_doc_count": len(selected_docs or []),
            "retrieval_quality": retrieval_quality,
            "selection_quality": selection_quality,
            "selected_docs": [_doc_summary(doc) for doc in selected_docs],
            "answer_preview": answer_text[:500],
        }
    except Exception as exc:
        return {
            "question": question,
            "status": "error",
            "issues": ["exception"],
            "elapsed_ms": _elapsed_ms(started),
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run representative E2E RAG questions.")
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    questions = args.question or DEFAULT_QUESTIONS
    pipeline = ChatPipeline()
    init_started = time.perf_counter()
    pipeline.initialize()
    initialize_ms = _elapsed_ms(init_started)

    results = [_run_one(pipeline, question) for question in questions]
    summary = {
        "initialize_ms": initialize_ms,
        "total_questions": len(results),
        "ok": sum(1 for item in results if item["status"] == "ok"),
        "needs_review": sum(1 for item in results if item["status"] == "needs_review"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "error": sum(1 for item in results if item["status"] == "error"),
        "results": results,
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
