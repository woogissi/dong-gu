from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from diagnose_supabase_rag_quality import analyze_cases, failure_cases, open_connection, precise_probe, precise_terms  # noqa: E402
from rag.embedding.koe5_embedder import KoE5Embedder  # noqa: E402
from rag.pipeline.preprocessor import QueryPreprocessor  # noqa: E402
from rag.pipeline.state import PipelineState  # noqa: E402
from rag.retrieval.retriever import retrieve_documents  # noqa: E402
from rag.retrieval.search_strategy import build_retrieval_request  # noqa: E402


DEFAULT_BETAS = (2.0, 5.0, 10.0, 20.0, 50.0, 100.0)


def build_request(preprocessor: QueryPreprocessor, embedder: KoE5Embedder, query: str, top_k: int) -> tuple[Any, dict[str, Any]]:
    state = PipelineState.from_query(query)
    preprocessor.run(state)
    request = build_retrieval_request(state)
    query_vector = embedder.embed_query(request.query)
    request = request.model_copy(update={"top_k": top_k, "query_vector": list(query_vector or [])})
    terms = list(dict.fromkeys([*(state.keywords or []), state.rewritten_query, state.normalized_query, query]))
    return request, {
        "query": query,
        "normalized_query": state.normalized_query,
        "rewritten_query": state.rewritten_query,
        "keywords": state.keywords,
        "category": state.category,
        "filters": state.filters,
        "terms": [term for term in terms if term],
    }


def run_hybrid(request: Any, *, mode: str, beta: float | None = None) -> list[Any]:
    previous_retrieval_mode = os.getenv("RETRIEVAL_MODE")
    previous_score_mode = os.getenv("HYBRID_SCORE_MODE")
    previous_beta = os.getenv("HYBRID_SRRF_BETA")
    os.environ["RETRIEVAL_MODE"] = "hybrid"
    os.environ["HYBRID_SCORE_MODE"] = mode
    if beta is not None:
        os.environ["HYBRID_SRRF_BETA"] = str(beta)
    try:
        return retrieve_documents(request=request)
    finally:
        restore_env("RETRIEVAL_MODE", previous_retrieval_mode)
        restore_env("HYBRID_SCORE_MODE", previous_score_mode)
        restore_env("HYBRID_SRRF_BETA", previous_beta)


def restore_env(key: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = previous


def summarize_doc(doc: Any, rank: int) -> dict[str, Any]:
    metadata = getattr(doc, "metadata", {}) or {}
    return {
        "rank": rank,
        "chunk_id": getattr(doc, "chunk_id", None),
        "doc_id": getattr(doc, "doc_id", None),
        "title": getattr(doc, "title", ""),
        "source_type": metadata.get("source_type"),
        "lexical_score": metadata.get("lexical_score"),
        "vector_score": metadata.get("vector_score"),
        "rrf_score": metadata.get("rrf_score"),
        "srrf_score": metadata.get("srrf_score"),
        "final_score": metadata.get("final_score"),
        "hybrid_adjustment": metadata.get("hybrid_adjustment"),
    }


def rank_of_evidence(docs: list[Any], evidence_chunk_ids: set[str], evidence_doc_ids: set[str]) -> int | None:
    for rank, doc in enumerate(docs, start=1):
        if doc.chunk_id in evidence_chunk_ids or doc.doc_id in evidence_doc_ids:
            return rank
    return None


def top_overlap(left: list[Any], right: list[Any], k: int) -> float:
    left_ids = {doc.chunk_id for doc in left[:k]}
    right_ids = {doc.chunk_id for doc in right[:k]}
    if not left_ids and not right_ids:
        return 1.0
    return len(left_ids & right_ids) / max(len(left_ids | right_ids), 1)


def rank_delta(left: list[Any], right: list[Any], k: int) -> float | None:
    left_ranks = {doc.chunk_id: rank for rank, doc in enumerate(left[:k], start=1)}
    right_ranks = {doc.chunk_id: rank for rank, doc in enumerate(right[:k], start=1)}
    common = set(left_ranks) & set(right_ranks)
    if not common:
        return None
    return mean(abs(left_ranks[chunk_id] - right_ranks[chunk_id]) for chunk_id in common)


def branch_mix(docs: list[Any], k: int) -> dict[str, int]:
    counts = Counter()
    for doc in docs[:k]:
        metadata = getattr(doc, "metadata", {}) or {}
        has_lexical = metadata.get("lexical_score") is not None
        has_vector = metadata.get("vector_score") is not None
        if has_lexical and has_vector:
            counts["both"] += 1
        elif has_lexical:
            counts["lexical_only"] += 1
        elif has_vector:
            counts["vector_only"] += 1
        else:
            counts["unknown"] += 1
    return dict(counts)


def score_setting(rows: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_rows = [row for row in rows if row["evidence_exists"]]
    evidence_ranks = [row["evidence_rank"] for row in evidence_rows if row["evidence_rank"] is not None]
    return {
        "queries": len(rows),
        "evidence_queries": len(evidence_rows),
        "hit_at_1": hit_rate(evidence_rows, 1),
        "hit_at_3": hit_rate(evidence_rows, 3),
        "hit_at_5": hit_rate(evidence_rows, 5),
        "hit_at_10": hit_rate(evidence_rows, 10),
        "avg_evidence_rank": round(mean(evidence_ranks), 3) if evidence_ranks else None,
        "avg_overlap_top5_vs_rrf": rounded_mean(row["overlap_top5_vs_rrf"] for row in rows),
        "avg_overlap_top10_vs_rrf": rounded_mean(row["overlap_top10_vs_rrf"] for row in rows),
        "avg_rank_delta_top10_vs_rrf": rounded_mean(row["rank_delta_top10_vs_rrf"] for row in rows),
        "top1_changed_vs_rrf": sum(1 for row in rows if row["top1_chunk_id"] != row["rrf_top1_chunk_id"]),
        "top1_changed_vs_weighted": sum(1 for row in rows if row["top1_chunk_id"] != row["weighted_top1_chunk_id"]),
    }


def hit_rate(rows: list[dict[str, Any]], k: int) -> float | None:
    if not rows:
        return None
    return round(sum(1 for row in rows if row["evidence_rank"] is not None and row["evidence_rank"] <= k) / len(rows), 3)


def rounded_mean(values: Any) -> float | None:
    present = [value for value in values if value is not None]
    return round(mean(present), 3) if present else None


def recommendation(summary: dict[str, dict[str, Any]]) -> dict[str, Any]:
    candidates = {name: metrics for name, metrics in summary.items() if name.startswith("srrf_beta_")}
    if not candidates:
        return {"setting": None, "reason": "No SRRF candidates were evaluated."}

    def key(item: tuple[str, dict[str, Any]]) -> tuple[float, float, float, float]:
        _, metrics = item
        return (
            metrics.get("hit_at_5") or 0.0,
            -(metrics.get("avg_evidence_rank") or 999.0),
            metrics.get("avg_overlap_top10_vs_rrf") or 0.0,
            -(metrics.get("top1_changed_vs_rrf") or 999.0),
        )

    best_name, best_metrics = max(candidates.items(), key=key)
    return {
        "setting": best_name,
        "env": {
            "HYBRID_SCORE_MODE": "srrf",
            "HYBRID_SRRF_BETA": best_name.replace("srrf_beta_", ""),
        },
        "reason": (
            "Selected by hit@5 first, then lower evidence rank, then stability against RRF top10 overlap."
        ),
        "metrics": best_metrics,
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Sweep SRRF beta values and compare rrf_score/srrf_score/final_score ranking changes.")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--betas", default=",".join(str(beta) for beta in DEFAULT_BETAS))
    parser.add_argument("--output", default="reports/srrf_tuning_report.json")
    args = parser.parse_args()

    betas = [float(value.strip()) for value in args.betas.split(",") if value.strip()]
    settings: list[tuple[str, str, float | None]] = [("weighted", "weighted", None), ("rrf", "rrf", None)]
    settings.extend((f"srrf_beta_{format_beta(beta)}", "srrf", beta) for beta in betas)

    preprocessor = QueryPreprocessor()
    embedder = KoE5Embedder()
    case_results: list[dict[str, Any]] = []
    per_setting_rows: dict[str, list[dict[str, Any]]] = {name: [] for name, _, _ in settings}

    with open_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cases = analyze_cases(cur, failure_cases(cur, args.limit), per_case_probe_limit=5)
            for index, case in enumerate(cases, start=1):
                query = case.get("user_query") or case.get("question") or ""
                if not query:
                    continue
                request, query_analysis = build_request(preprocessor, embedder, query, args.top_k)
                evidence_rows = precise_probe(cur, query_analysis["terms"], limit=8)
                evidence_chunk_ids = {row["chunk_id"] for row in evidence_rows if row.get("chunk_id")}
                evidence_doc_ids = {row["doc_id"] for row in evidence_rows if row.get("doc_id")}

                docs_by_setting = {
                    name: run_hybrid(request, mode=mode, beta=beta)
                    for name, mode, beta in settings
                }
                rrf_docs = docs_by_setting["rrf"]
                weighted_docs = docs_by_setting["weighted"]
                case_settings: dict[str, Any] = {}
                for name, docs in docs_by_setting.items():
                    evidence_rank = rank_of_evidence(docs, evidence_chunk_ids, evidence_doc_ids)
                    row = {
                        "query_index": index,
                        "query": query,
                        "setting": name,
                        "evidence_exists": bool(evidence_rows),
                        "evidence_rank": evidence_rank,
                        "top1_chunk_id": docs[0].chunk_id if docs else None,
                        "rrf_top1_chunk_id": rrf_docs[0].chunk_id if rrf_docs else None,
                        "weighted_top1_chunk_id": weighted_docs[0].chunk_id if weighted_docs else None,
                        "overlap_top5_vs_rrf": top_overlap(docs, rrf_docs, 5),
                        "overlap_top10_vs_rrf": top_overlap(docs, rrf_docs, 10),
                        "rank_delta_top10_vs_rrf": rank_delta(docs, rrf_docs, 10),
                    }
                    per_setting_rows[name].append(row)
                    case_settings[name] = {
                        **row,
                        "branch_mix_top10": branch_mix(docs, 10),
                        "top5": [summarize_doc(doc, rank) for rank, doc in enumerate(docs[:5], start=1)],
                    }
                case_results.append(
                    {
                        "query": query,
                        "query_analysis": query_analysis,
                        "evidence_exists": bool(evidence_rows),
                        "evidence_top": evidence_rows[:3],
                        "settings": case_settings,
                    }
                )

    summary = {name: score_setting(rows) for name, rows in per_setting_rows.items()}
    result = {
        "summary": summary,
        "recommendation": recommendation(summary),
        "cases": case_results,
    }
    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), **result["recommendation"]}, ensure_ascii=False, indent=2))


def format_beta(beta: float) -> str:
    return str(int(beta)) if beta.is_integer() else str(beta).replace(".", "_")


if __name__ == "__main__":
    main()
