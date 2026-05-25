from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from rag.embedding.koe5_embedder import KoE5Embedder
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.preprocess.query_features import extract_query_features
from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request
from rag.retrieval.source_policy import allowed_source_types_for_values
from rag.selection.reranker import rerank_documents
from rag.selection.topk_selector import select_topk_with_diagnostics


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "reports" / "e2e_recent_query_log_diagnosis.json"
DEFAULT_MD = ROOT / "reports" / "e2e_recent_query_log_diagnosis.md"


def clean(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {str(key): clean(item) for key, item in value.items()}
    return value


def connect():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
        cursor_factory=RealDictCursor,
    )


def fetch_recent_cases(cur, limit: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        WITH latest_retrieval AS (
            SELECT DISTINCT ON (request_id) *
            FROM retrieval_logs
            ORDER BY request_id, created_at DESC, id DESC
        ),
        selected AS (
            SELECT
                retrieval_log_id,
                jsonb_agg(
                    jsonb_build_object(
                        'rank', rsc.rank,
                        'chunk_id', rsc.chunk_id,
                        'doc_id', rsc.doc_id,
                        'score', rsc.score,
                        'rerank_score', rsc.rerank_score,
                        'title', coalesce(d.title, rsc.title_snapshot),
                        'source', coalesce(d.source_url, rsc.source_snapshot),
                        'source_type', d.source_type,
                        'section_type', c.section_type,
                        'section_title', c.section_title,
                        'preview', left(coalesce(c.content, rsc.content_snapshot, ''), 240),
                        'metadata', rsc.metadata
                    )
                    ORDER BY rsc.rank
                ) AS selected_chunks
            FROM retrieval_selected_chunks rsc
            LEFT JOIN chunks c ON c.chunk_id = rsc.chunk_id
            LEFT JOIN documents d ON d.doc_id = coalesce(c.doc_id, rsc.doc_id)
            GROUP BY retrieval_log_id
        )
        SELECT
            q.id AS query_id,
            q.request_id::text AS request_id,
            q.question,
            q.intent_type::text AS intent_type,
            q.created_at AS query_created_at,
            rl.id AS retrieval_log_id,
            rl.original_query,
            rl.normalized_query,
            rl.rewritten_query,
            rl.rewritten_queries,
            rl.keywords,
            rl.filters,
            rl.category,
            rl.retrieval_strategy::text AS retrieval_strategy,
            rl.retrieval_top_k,
            rl.retrieval_strategy_log,
            rl.fallback_used,
            rl.retrieved_doc_count,
            rl.reranked_doc_count,
            rl.selected_doc_count,
            rl.success AS retrieval_success,
            rl.error_message AS retrieval_error,
            rl.metadata AS retrieval_metadata,
            s.selected_chunks,
            r.answer_text,
            r.success AS response_success,
            r.error_message AS response_error,
            r.response_time_ms
        FROM query_logs q
        LEFT JOIN latest_retrieval rl ON rl.request_id = q.request_id
        LEFT JOIN selected s ON s.retrieval_log_id = rl.id
        LEFT JOIN response_logs r ON r.request_id = q.request_id
        ORDER BY q.created_at DESC, q.id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [clean(dict(row)) for row in cur.fetchall()]


def doc_summary(doc: Any, rank: int) -> dict[str, Any]:
    metadata = getattr(doc, "metadata", {}) or {}
    signals = metadata.get("rerank_signals") or {}
    return clean(
        {
            "rank": rank,
            "doc_id": getattr(doc, "doc_id", None),
            "chunk_id": getattr(doc, "chunk_id", None),
            "title": getattr(doc, "title", ""),
            "source": getattr(doc, "source", ""),
            "score": getattr(doc, "score", None),
            "source_type": metadata.get("source_type"),
            "section_type": metadata.get("section_type"),
            "section_title": metadata.get("section_title"),
            "lexical_score": metadata.get("lexical_score"),
            "vector_score": metadata.get("vector_score"),
            "final_score": metadata.get("final_score"),
            "rerank_score": metadata.get("rerank_score", getattr(doc, "score", None)),
            "query_family_boost": signals.get("query_family_boost"),
            "query_family_penalty": signals.get("query_family_penalty"),
            "strong_term_match": signals.get("strong_term_match"),
            "required_entity_match": signals.get("required_entity_match"),
            "noise_score": signals.get("noise_score"),
            "content_preview": (getattr(doc, "content", "") or "")[:240],
        }
    )


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


def effective_mode(request: Any) -> str:
    configured_mode = os.getenv("RETRIEVAL_MODE", "").strip().lower()
    if configured_mode in {"lexical", "vector", "hybrid"}:
        return configured_mode
    query_family = ""
    if isinstance(request.log_fields, dict):
        query_family = str(request.log_fields.get("query_family") or "")
    vector_only = {
        value.strip()
        for value in os.getenv(
            "RAG_VECTOR_ONLY_FAMILIES",
            "department_curriculum,building_location,welfare_facility,campus_address,person_title,"
            "course_registration,academic_schedule,seasonal_course_registration,specific_scholarship,"
            "graduation,certificate",
        ).split(",")
        if value.strip()
    }
    if query_family in vector_only:
        return "vector"
    if request.strategy in {"dense", "vector"}:
        return "vector"
    return "hybrid" if request.strategy == "lexical" else request.strategy


def max_chunks_per_doc_for_family(family: str) -> int:
    if family == "department_curriculum":
        return 4
    if family in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
        return 3
    return 1


def analyze_query(
    preprocessor: QueryPreprocessor,
    embedder: KoE5Embedder,
    question: str,
    top_k: int,
    *,
    branch_replay: bool,
) -> dict[str, Any]:
    state = PipelineState.from_query(question)
    preprocessor.run(state)
    request = build_retrieval_request(state)
    vector = embedder.embed_query(request.query)
    request = request.model_copy(update={"query_vector": list(vector or []), "top_k": top_k})

    mode = effective_mode(request)
    current_docs = run_with_mode(request.model_copy(update={"strategy": mode}), mode)
    reranked_docs = rerank_documents(
        current_docs,
        query=request.query,
        keywords=request.keywords,
        category=request.category,
        filters=request.filters,
    )
    query_features = request.log_fields.get("query_features") if isinstance(request.log_fields, dict) else {}
    family = str((query_features or {}).get("family") or "")
    selection = select_topk_with_diagnostics(
        reranked_docs,
        max_chunks_per_doc=max_chunks_per_doc_for_family(family),
    )

    lexical_docs: list[Any] = []
    vector_docs: list[Any] = []
    hybrid_docs: list[Any] = []
    relaxed_hybrid_docs: list[Any] = []
    if branch_replay:
        lexical_docs = run_with_mode(request.model_copy(update={"strategy": "keyword"}), "lexical")
        vector_docs = run_with_mode(request.model_copy(update={"strategy": "vector"}), "vector")
        hybrid_docs = run_with_mode(request.model_copy(update={"strategy": "hybrid"}), "hybrid")
        relaxed_request = request.model_copy(update={"filters": {}, "category": None})
        relaxed_hybrid_docs = run_with_mode(relaxed_request.model_copy(update={"strategy": "hybrid"}), "hybrid")

    source_filter_values = []
    for field in ("document_category", "category"):
        source_filter_values.extend(request.filters.get(field, []) or [])

    return {
        "preprocess": {
            "normalized_query": state.normalized_query,
            "rewritten_query": state.rewritten_query,
            "rewritten_queries": state.rewritten_queries,
            "keywords": state.keywords,
            "category": state.category,
            "filters": state.filters,
            "query_features": query_features,
        },
        "request": clean(
            {
                "query": request.query,
                "query_variants": request.query_variants,
                "keywords": request.keywords,
                "filters": request.filters,
                "category": request.category,
                "strategy": request.strategy,
                "top_k": request.top_k,
                "fallback_triggers": request.fallback_triggers,
                "query_vector_size": len(request.query_vector or []),
                "effective_mode": mode,
                "log_fields": request.log_fields,
                "source_type_filter_values": allowed_source_types_for_values(source_filter_values),
                "source_type_hint_values": allowed_source_types_for_values(source_filter_values),
            }
        ),
        "counts": {
            "current": len(current_docs),
            "lexical": len(lexical_docs) if branch_replay else None,
            "vector": len(vector_docs) if branch_replay else None,
            "hybrid": len(hybrid_docs) if branch_replay else None,
            "reranked": len(reranked_docs),
            "selected": len(selection["selected"]),
            "relaxed_hybrid": len(relaxed_hybrid_docs) if branch_replay else None,
        },
        "current_top": [doc_summary(doc, rank) for rank, doc in enumerate(current_docs[:8], start=1)],
        "lexical_top": [doc_summary(doc, rank) for rank, doc in enumerate(lexical_docs[:8], start=1)],
        "vector_top": [doc_summary(doc, rank) for rank, doc in enumerate(vector_docs[:8], start=1)],
        "hybrid_top": [doc_summary(doc, rank) for rank, doc in enumerate(hybrid_docs[:8], start=1)],
        "reranked_top": [doc_summary(doc, rank) for rank, doc in enumerate(reranked_docs[:8], start=1)],
        "selected": [doc_summary(doc, rank) for rank, doc in enumerate(selection["selected"], start=1)],
        "selection_diagnostics": clean(
            {
                "selection_policy": selection.get("selection_policy"),
                "rejected_chunks": selection.get("rejected_chunks", [])[:20],
            }
        ),
        "relaxed_hybrid_top": [doc_summary(doc, rank) for rank, doc in enumerate(relaxed_hybrid_docs[:5], start=1)],
    }


def classify(case: dict[str, Any], replay: dict[str, Any]) -> dict[str, str]:
    intent = case.get("intent_type")
    if intent != "INFO":
        return {"stage": "route", "problem": "non_info_query", "detail": f"intent={intent}, RAG 대상이 아닐 수 있음"}
    if not case.get("retrieval_log_id"):
        return {"stage": "route/logging", "problem": "missing_retrieval_log", "detail": "INFO인데 retrieval_logs가 없음"}

    counts = replay["counts"]
    request = replay["request"]
    family = ((replay["preprocess"].get("query_features") or {}).get("family") or "general")
    source_hints = request.get("source_type_hint_values") or request.get("source_type_filter_values") or []

    if counts.get("hybrid") == 0 and (counts.get("relaxed_hybrid") or 0) > 0:
        return {
            "stage": "filter",
            "problem": "over_constrained_filter",
            "detail": f"filters={request.get('filters')} source_type_hints={source_hints}",
        }
    if counts.get("lexical") and counts.get("vector") == 0:
        return {"stage": "vector", "problem": "vector_branch_miss", "detail": "lexical 후보는 있으나 vector 후보가 없음"}
    if counts.get("lexical") == 0 and counts.get("vector"):
        return {"stage": "lexical", "problem": "lexical_branch_miss", "detail": "vector 후보는 있으나 lexical 후보가 없음"}
    if counts["current"] == 0:
        return {"stage": "retrieval", "problem": "no_candidates", "detail": "lexical/vector/hybrid 재실행 결과 후보가 없음"}
    if counts["selected"] == 0:
        return {"stage": "selection", "problem": "selection_dropped_all", "detail": "rerank 이후 top-k 선택 결과가 비어 있음"}

    top = replay["selected"][0] if replay["selected"] else {}
    if top.get("noise_score") and float(top.get("noise_score") or 0) >= 1.0:
        return {"stage": "selection", "problem": "noisy_top_context", "detail": f"top noise_score={top.get('noise_score')}"}
    if case.get("selected_doc_count") == 0 and counts["selected"] > 0:
        return {"stage": "runtime/config", "problem": "current_replay_better_than_log", "detail": "현재 코드 재실행은 선택 문서를 만들지만 기존 로그는 0건"}
    if case.get("answer_text") and "찾" in str(case.get("answer_text"))[:120] and counts["selected"] > 0:
        return {"stage": "generation", "problem": "negative_answer_with_context", "detail": "선택 컨텍스트가 있는데 답변은 부정형으로 보임"}
    return {"stage": "mixed", "problem": "manual_review", "detail": "후보/선택/로그를 함께 확인 필요"}


def top_titles(items: list[dict[str, Any]], limit: int = 3) -> str:
    if not items:
        return "-"
    return "; ".join(f"{item.get('rank')}. {item.get('title')} [{item.get('source_type')}] score={item.get('score')}" for item in items[:limit])


def write_markdown(path: Path, result: dict[str, Any]) -> None:
    rows = result["cases"]
    counts = Counter(case["diagnosis"]["problem"] for case in rows)
    lines = [
        "# Recent Query Logs E2E RAG Diagnosis",
        "",
        f"- analyzed_queries: {len(rows)}",
        f"- generated_at: {result['generated_at']}",
        "",
        "## Problem Distribution",
        "",
    ]
    for problem, count in counts.most_common():
        lines.append(f"- {problem}: {count}")
    lines.extend(["", "## Cases", ""])
    for case in rows:
        replay = case["replay"]
        diag = case["diagnosis"]
        lines.extend(
            [
                f"### query_id={case['query_id']} request_id={case['request_id']}",
                "",
                f"- question: {case['question']}",
                f"- intent: {case['intent_type']}",
                f"- family/domain: {(replay['preprocess'].get('query_features') or {}).get('family')} / {(replay['preprocess'].get('query_features') or {}).get('domain')}",
                f"- keywords: {replay['preprocess'].get('keywords')}",
                f"- filters: {replay['request'].get('filters')}",
                f"- source_type_hint_values: {replay['request'].get('source_type_hint_values') or replay['request'].get('source_type_filter_values')}",
                f"- logged counts: retrieved={case.get('retrieved_doc_count')} reranked={case.get('reranked_doc_count')} selected={case.get('selected_doc_count')} fallback={case.get('fallback_used')}",
                f"- replay counts: {replay['counts']}",
                f"- diagnosis: {diag['problem']} ({diag['stage']}) - {diag['detail']}",
                f"- current mode/top: {replay['request'].get('effective_mode')} / {top_titles(replay['current_top'])}",
                f"- lexical top: {top_titles(replay['lexical_top'])}",
                f"- vector top: {top_titles(replay['vector_top'])}",
                f"- hybrid top: {top_titles(replay['hybrid_top'])}",
                f"- reranked top: {top_titles(replay['reranked_top'])}",
                f"- selected: {top_titles(replay['selected'])}",
                f"- logged answer: {(case.get('answer_text') or '')[:260]}",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--top-k", type=int, default=30)
    parser.add_argument("--branch-replay", action="store_true")
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--markdown", default=str(DEFAULT_MD))
    args = parser.parse_args()

    preprocessor = QueryPreprocessor()
    embedder = KoE5Embedder()

    with connect() as conn:
        with conn.cursor() as cur:
            cases = fetch_recent_cases(cur, args.limit)

    analyzed = []
    for case in cases:
        question = case.get("question") or ""
        replay = analyze_query(preprocessor, embedder, question, args.top_k, branch_replay=args.branch_replay)
        diagnosis = classify(case, replay)
        analyzed.append({**case, "replay": replay, "diagnosis": diagnosis})

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "limit": args.limit,
        "top_k": args.top_k,
        "cases": analyzed,
        "summary": {
            "problem_distribution": dict(Counter(case["diagnosis"]["problem"] for case in analyzed)),
            "stage_distribution": dict(Counter(case["diagnosis"]["stage"] for case in analyzed)),
        },
    }

    json_path = Path(args.json)
    md_path = Path(args.markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(clean(result), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(md_path, clean(result))
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), "summary": result["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
