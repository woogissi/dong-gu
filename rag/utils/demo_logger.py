"""Console logging helpers for pipeline demo runs."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any


_ENV_NAME = "RAG_DEMO_LOG"
_MAX_TEXT_LENGTH = 3000
_MAX_LINE_LENGTH = 500


def demo_log_enabled() -> bool:
    value = os.getenv(_ENV_NAME, "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def demo_log(stage: str, payload: Any | None = None) -> None:
    if not demo_log_enabled():
        return

    timestamp = datetime.now().isoformat(timespec="seconds")
    print("\n" + "=" * 88)
    print(f"[DEMO PIPELINE] {timestamp} | {stage}")
    print("-" * 88)
    if payload is not None:
        for line in _format_payload_lines(payload):
            print(line)
    print("=" * 88)


def summarize_docs(
    docs: list[Any],
    limit: int = 3,
) -> list[dict[str, Any]]:
    return [summarize_doc(doc, rank=index + 1) for index, doc in enumerate(docs[:limit])]


def summarize_doc(doc: Any, *, rank: int | None = None) -> dict[str, Any]:
    return {
        "rank": rank,
        "doc_id": _get_value(doc, "doc_id"),
        "chunk_id": _get_value(doc, "chunk_id"),
        "score": _get_value(doc, "score"),
    }


def preview_text(text: str | None, *, max_length: int = _MAX_TEXT_LENGTH) -> str:
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}... [truncated {len(text) - max_length} chars]"


def _format_payload_lines(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return [_compact_value(payload)]
    return [f"{key}: {_compact_value(value)}" for key, value in payload.items()]


def _compact_value(value: Any) -> str:
    jsonable = _to_jsonable(value)
    if isinstance(jsonable, str):
        return preview_text(jsonable, max_length=_MAX_LINE_LENGTH)
    if isinstance(jsonable, (int, float, bool)) or jsonable is None:
        return str(jsonable)
    encoded = json.dumps(jsonable, ensure_ascii=False, default=str)
    return preview_text(encoded, max_length=_MAX_LINE_LENGTH)


def _get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
