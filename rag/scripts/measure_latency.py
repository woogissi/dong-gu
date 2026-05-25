"""Measure per-stage RAG latency for a single query.

Run inside the RAG container:
    python -m rag.scripts.measure_latency "컴퓨터공학과 2학년 이수표 교육과정"
"""

from __future__ import annotations

import json
import os
import sys
import time
from functools import wraps
from typing import Any

import rag.pipeline.chat_pipeline as chat_pipeline_module
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query


DEFAULT_QUERY = "컴퓨터공학과 2학년 이수표 교육과정"


def _round_ms(seconds: float) -> int:
    return int(round(seconds * 1000))


def main() -> None:
    query_text = " ".join(sys.argv[1:]).strip() or DEFAULT_QUERY
    timings: list[dict[str, Any]] = []
    retrieval_calls: list[dict[str, Any]] = []

    original_retrieve_documents = chat_pipeline_module.retrieve_documents

    @wraps(original_retrieve_documents)
    def timed_retrieve_documents(*args: Any, **kwargs: Any) -> Any:
        request = kwargs.get("request")
        mode = os.getenv("RETRIEVAL_MODE", "")
        started = time.perf_counter()
        result = original_retrieve_documents(*args, **kwargs)
        elapsed = time.perf_counter() - started
        retrieval_calls.append(
            {
                "mode": mode or "default",
                "strategy": getattr(request, "strategy", None),
                "top_k": getattr(request, "top_k", None),
                "result_count": len(result or []),
                "elapsed_ms": _round_ms(elapsed),
            }
        )
        return result

    chat_pipeline_module.retrieve_documents = timed_retrieve_documents

    pipeline = ChatPipeline()
    original_methods = {}

    def wrap_method(name: str) -> None:
        original = getattr(pipeline, name)
        original_methods[name] = original

        @wraps(original)
        def timed(*args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                timings.append({"stage": name, "elapsed_ms": _round_ms(time.perf_counter() - started)})

        setattr(pipeline, name, timed)

    for method_name in (
        "_classify_primary_intent",
        "_embed_query",
        "_retrieve",
        "_select_and_build_context",
        "_generate",
        "_postprocess",
    ):
        wrap_method(method_name)

    original_preprocess_run = pipeline.preprocessor.run

    @wraps(original_preprocess_run)
    def timed_preprocess(*args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return original_preprocess_run(*args, **kwargs)
        finally:
            timings.append({"stage": "preprocessor.run", "elapsed_ms": _round_ms(time.perf_counter() - started)})

    pipeline.preprocessor.run = timed_preprocess

    initialize_started = time.perf_counter()
    pipeline.initialize()
    initialize_ms = _round_ms(time.perf_counter() - initialize_started)

    run_started = time.perf_counter()
    answer = pipeline.run(Query(text=query_text))
    total_ms = _round_ms(time.perf_counter() - run_started)
    state = pipeline.last_state

    print(
        json.dumps(
            {
                "query": query_text,
                "initialize_ms": initialize_ms,
                "total_run_ms": total_ms,
                "stages": timings,
                "retrieval_calls": retrieval_calls,
                "success": answer.success,
                "fallback_used": bool(getattr(state, "fallback_used", False)) if state else None,
                "retrieved_doc_count": len(getattr(state, "retrieved_docs", []) or []) if state else None,
                "reranked_doc_count": len(getattr(state, "reranked_docs", []) or []) if state else None,
                "selected_doc_count": len(getattr(state, "selected_docs", []) or []) if state else None,
                "answer_preview": (answer.answer or "")[:240],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
