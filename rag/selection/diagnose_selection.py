from __future__ import annotations

import argparse
import json
from typing import Any

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState


DEFAULT_QUERIES = [
    "23번 건물 이름",
    "역대 총장 알려줘",
    "도서관 운영시간",
    "장학금 신청 방법",
    "통학버스 시간",
]


def summarize_doc(rank: int, doc: Any) -> dict[str, Any]:
    metadata = doc.metadata or {}
    signals = metadata.get("rerank_signals") or {}
    return {
        "rank": rank,
        "doc_id": doc.doc_id,
        "chunk_id": doc.chunk_id,
        "title": doc.title,
        "section_title": metadata.get("section_title"),
        "source_type": metadata.get("source_type"),
        "document_type": metadata.get("document_type"),
        "is_attachment": metadata.get("section_type") == "attachment",
        "lexical_score": metadata.get("lexical_score"),
        "vector_score": metadata.get("vector_score"),
        "base_score": signals.get("base_score"),
        "rerank_score": metadata.get("rerank_score", doc.score),
        "final_score": metadata.get("final_score"),
        "noise_score": signals.get("noise_score"),
        "boost_signals": {
            "title_match": signals.get("title_match"),
            "section_title_match": signals.get("section_title_match"),
            "content_match": signals.get("content_match"),
            "strong_term_match": signals.get("strong_term_match"),
            "exact_query_match": signals.get("exact_query_match"),
            "query_family_boost": signals.get("query_family_boost"),
            "required_heading_match": signals.get("required_heading_match"),
            "category_match": signals.get("category_match"),
            "recency": signals.get("recency"),
        },
        "penalty_signals": {
            "missing_strong_terms": signals.get("missing_strong_terms"),
            "attachment_noise": signals.get("attachment_noise"),
            "exif_noise": signals.get("exif_noise"),
            "query_family_penalty": signals.get("query_family_penalty"),
        },
    }


def diagnose_query(
    pipeline: ChatPipeline,
    query: str,
    top_n: int,
    selected_only: bool,
) -> dict[str, Any]:
    state = PipelineState.from_query(query)
    pipeline._classify_primary_intent(state)
    if state.primary_intent != "INFO":
        return {
            "query": query,
            "primary_intent": state.primary_intent,
            "skipped": "non_info_intent",
        }

    pipeline.preprocessor.run(state)
    pipeline._embed_query(state)
    pipeline._retrieve(state)
    pipeline._select_and_build_context(state)

    result = {
        "query": query,
        "primary_intent": state.primary_intent,
        "normalized_query": state.normalized_query,
        "keywords": state.keywords,
        "retrieval_strategy": state.retrieval_strategy,
        "retrieved_doc_count": len(state.retrieved_docs),
        "selected_docs": [
            summarize_doc(rank, doc)
            for rank, doc in enumerate(state.selected_docs, start=1)
        ],
        "selection_quality": state.metadata.get("selection_quality"),
    }
    if not selected_only:
        result["reranked_top"] = [
            summarize_doc(rank, doc)
            for rank, doc in enumerate(state.reranked_docs[:top_n], start=1)
        ]
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose reranking and selected RAG context.")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--selected-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = args.query or DEFAULT_QUERIES
    pipeline = ChatPipeline()
    pipeline.initialize()
    result = [
        diagnose_query(pipeline, query, args.top_n, args.selected_only)
        for query in queries
    ]
    print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
