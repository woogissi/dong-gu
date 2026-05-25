"""Inspect retrieval candidates and target document presence for a query."""

from __future__ import annotations

import argparse
import os
from typing import Any

import psycopg2
from psycopg2.extras import DictCursor

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request


DEFAULT_QUERY = "컴퓨터공학과 2학년 이수표 교육과정"
DEFAULT_TARGET_DOC_ID = "static_06b9d3809cb12e19"


def print_target_db_state(target_doc_id: str) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("[db] DATABASE_URL is not set")
        return

    with psycopg2.connect(database_url) as conn:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                """
                SELECT
                    d.doc_id,
                    d.title,
                    d.source_url,
                    d.source_type,
                    d.department,
                    count(DISTINCT c.chunk_id) AS chunk_count,
                    count(DISTINCT e.chunk_id) AS embedding_count
                FROM documents d
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
                WHERE d.doc_id = %s
                GROUP BY d.doc_id, d.title, d.source_url, d.source_type, d.department
                """,
                (target_doc_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
            print("[db target]", rows)

            cur.execute(
                """
                SELECT
                    c.chunk_id,
                    c.section_type,
                    c.section_title,
                    c.content_length,
                    e.chunk_id IS NOT NULL AS has_embedding,
                    left(c.content, 260) AS preview
                FROM chunks c
                LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
                WHERE c.doc_id = %s
                ORDER BY c.chunk_id
                """,
                (target_doc_id,),
            )
            for row in cur.fetchall():
                item = dict(row)
                preview = " ".join(str(item.pop("preview") or "").split())
                print("[db chunk]", item, "preview=", preview)


def prepare_request(query: str, *, strategy: str, top_k: int):
    pipeline = ChatPipeline()
    pipeline.initialize()

    state = PipelineState.from_query(query)
    pipeline._classify_primary_intent(state)
    pipeline.preprocessor.run(state)
    pipeline._embed_query(state)
    request = build_retrieval_request(state).model_copy(
        update={"strategy": strategy, "top_k": top_k}
    )
    return request


def doc_line(rank: int, doc: Any) -> str:
    return (
        f"{rank:>3}. score={float(doc.score or 0):.4f} "
        f"doc={doc.doc_id} chunk={doc.chunk_id} "
        f"title={doc.title!r} section={doc.metadata.get('section_title')!r} "
        f"source={doc.source}"
    )


def print_retrieval_state(query: str, target_doc_id: str, strategy: str, top_k: int) -> None:
    request = prepare_request(query, strategy=strategy, top_k=top_k)
    docs = retrieve_documents(request=request)
    print(
        "[request]",
        {
            "query": request.query,
            "strategy": request.strategy,
            "top_k": request.top_k,
            "category": request.category,
            "filters": request.filters,
            "query_family": request.log_fields.get("query_family"),
            "strong_terms": request.log_fields.get("strong_terms"),
        },
    )
    print(f"[retrieval] count={len(docs)} strategy={strategy}")

    target_ranks = []
    computer_rows = []
    for rank, doc in enumerate(docs, start=1):
        if doc.doc_id == target_doc_id:
            target_ranks.append(rank)
        if "컴퓨터공학과" in (doc.title or "") or doc.doc_id == target_doc_id:
            computer_rows.append((rank, doc))

    print("[target ranks]", target_ranks or "not in returned candidates")
    print("[top 20]")
    for rank, doc in enumerate(docs[:20], start=1):
        print(doc_line(rank, doc))

    print("[computer department rows]")
    if not computer_rows:
        print("none")
    for rank, doc in computer_rows[:30]:
        print(doc_line(rank, doc))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY)
    parser.add_argument("--target-doc-id", default=DEFAULT_TARGET_DOC_ID)
    parser.add_argument("--strategy", default="vector", choices=["vector", "hybrid", "lexical"])
    parser.add_argument("--top-k", type=int, default=200)
    args = parser.parse_args()

    print_target_db_state(args.target_doc_id)
    print_retrieval_state(args.query, args.target_doc_id, args.strategy, args.top_k)


if __name__ == "__main__":
    main()
