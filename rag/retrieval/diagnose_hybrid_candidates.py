from __future__ import annotations

import argparse
import json
import os
from typing import Any

from rag.embedding.koe5_embedder import KoE5Embedder
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request
from rag.schemas.retrieval import RetrievalRequest


DEFAULT_QUERIES = [
    "\uc218\uac15\uc2e0\uccad \uae30\uac04",
    "\uae30\uc219\uc0ac \uc2e0\uccad \uae30\uac04",
    "\uc878\uc5c5\uc694\uac74",
    "\uc7a5\ud559\uae08 \uc2e0\uccad \ubc29\ubc95",
    "\ud1b5\ud559\ubc84\uc2a4 \uc2dc\uac04",
    "\ub3c4\uc11c\uad00 \uc6b4\uc601\uc2dc\uac04",
]

RETRIEVAL_MODE_ENV = "RETRIEVAL_MODE"


def summarize_doc(doc: Any) -> dict[str, Any]:
    return {
        "doc_id": doc.doc_id,
        "chunk_id": doc.chunk_id,
        "title": doc.title,
        "source": doc.source,
        "source_type": doc.metadata.get("source_type"),
        "department": doc.metadata.get("department"),
        "score": doc.score,
        "ts_rank_score": doc.metadata.get("ts_rank_score"),
        "exact_phrase_score": doc.metadata.get("exact_phrase_score"),
        "term_match_score": doc.metadata.get("term_match_score"),
        "ilike_score": doc.metadata.get("ilike_score"),
        "title_match_score": doc.metadata.get("title_match_score"),
        "section_match_score": doc.metadata.get("section_match_score"),
        "category_bonus": doc.metadata.get("category_bonus"),
        "noise_penalty": doc.metadata.get("noise_penalty"),
        "raw_lexical_score": doc.metadata.get("raw_lexical_score"),
        "lexical_score": doc.metadata.get("lexical_score"),
        "lexical_norm_score": doc.metadata.get("lexical_norm_score"),
        "vector_score": doc.metadata.get("vector_score"),
        "rrf_score": doc.metadata.get("rrf_score"),
        "final_score": doc.metadata.get("final_score"),
        "search_mode": doc.metadata.get("search_mode"),
        "content_preview": (doc.content or "")[:220],
    }


def build_base_request(preprocessor: QueryPreprocessor, query: str) -> RetrievalRequest:
    state = PipelineState.from_query(query)
    preprocessor.run(state)
    return build_retrieval_request(state)


def diagnose_query(
    *,
    preprocessor: QueryPreprocessor,
    embedder: KoE5Embedder,
    query: str,
    top_n: int,
) -> dict[str, Any]:
    lexical_request = build_base_request(preprocessor, query)
    lexical_request = lexical_request.model_copy(update={"top_k": top_n})
    lexical_docs = retrieve_with_mode(lexical_request, "lexical")

    query_vector = embedder.embed_query(query)
    vector_request = lexical_request.model_copy(
        update={
            "strategy": "vector",
            "query_vector": list(query_vector),
            "top_k": top_n,
        }
    )
    vector_docs = retrieve_with_mode(vector_request, "vector")
    hybrid_request = lexical_request.model_copy(
        update={
            "strategy": "hybrid",
            "query_vector": list(query_vector),
            "top_k": top_n,
        }
    )
    hybrid_docs = retrieve_with_mode(hybrid_request, "hybrid")

    return {
        "query": query,
        "normalized_query": lexical_request.query,
        "keywords": lexical_request.keywords,
        "filters": lexical_request.filters,
        "lexical_top": [summarize_doc(doc) for doc in lexical_docs[:top_n]],
        "vector_top": [summarize_doc(doc) for doc in vector_docs[:top_n]],
        "hybrid_top": [summarize_doc(doc) for doc in hybrid_docs[:top_n]],
    }


def retrieve_with_mode(request: RetrievalRequest, mode: str) -> list[Any]:
    previous_mode = os.getenv(RETRIEVAL_MODE_ENV)
    os.environ[RETRIEVAL_MODE_ENV] = mode
    try:
        return retrieve_documents(request=request)
    finally:
        if previous_mode is None:
            os.environ.pop(RETRIEVAL_MODE_ENV, None)
        else:
            os.environ[RETRIEVAL_MODE_ENV] = previous_mode


def diagnose(queries: list[str], top_n: int) -> list[dict[str, Any]]:
    preprocessor = QueryPreprocessor()
    embedder = KoE5Embedder()
    return [
        diagnose_query(
            preprocessor=preprocessor,
            embedder=embedder,
            query=query,
            top_n=top_n,
        )
        for query in queries
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare RAG lexical and pgvector candidates before enabling hybrid ranking.",
    )
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--query", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    queries = args.query or DEFAULT_QUERIES
    print(json.dumps(diagnose(queries, args.top_n), ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
