"""Retrieval quality policy shared by pipeline orchestration."""

from __future__ import annotations

BLOCKING_RETRIEVAL_QUALITY_REASONS = {
    "empty_result",
    "low_top1_score",
    "low_avg_score",
    "short_context",
    "excessive_duplicate_doc_ids",
    "top_candidate_noise",
    "no_required_entity_match",
}


def retrieval_quality_result(diagnostic_reason: str, **fields) -> dict:
    blocking = diagnostic_reason in BLOCKING_RETRIEVAL_QUALITY_REASONS
    return {
        "ok": not blocking,
        "blocking": blocking,
        "reason": diagnostic_reason if blocking else "",
        "diagnostic_ok": not diagnostic_reason,
        "diagnostic_reason": diagnostic_reason,
        **fields,
    }


def set_retrieval_quality_status(retrieval_quality: dict, diagnostic_reason: str) -> None:
    blocking = diagnostic_reason in BLOCKING_RETRIEVAL_QUALITY_REASONS
    retrieval_quality.update(
        {
            "ok": not blocking,
            "blocking": blocking,
            "reason": diagnostic_reason if blocking else "",
            "diagnostic_ok": not diagnostic_reason,
            "diagnostic_reason": diagnostic_reason,
        }
    )
