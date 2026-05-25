"""Run representative RAG regression cases against the RAG API."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.evaluation.regression_cases import (  # noqa: E402
    REGRESSION_CASES,
    selected_context_has_not_found_mismatch,
)


def call_rag_api(base_url: str, query: str, timeout: float) -> dict:
    payload = json.dumps({"text": query}).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/rag/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize_sources(result: dict) -> tuple[set[str], str]:
    selected = (result.get("retrieval_log") or {}).get("selected_docs") or []
    source_types = {
        str((doc.get("metadata") or {}).get("source_type") or "")
        for doc in selected[:3]
        if isinstance(doc, dict)
    }
    titles = " ".join(str(doc.get("title") or "") for doc in selected[:3] if isinstance(doc, dict))
    return source_types, titles


def selected_source_urls(result: dict) -> list[str]:
    selected = (result.get("retrieval_log") or {}).get("selected_docs") or []
    urls: list[str] = []
    for doc in selected[:3]:
        if not isinstance(doc, dict):
            continue
        url = str(doc.get("source") or doc.get("source_url") or "").strip()
        if url and url not in urls:
            urls.append(url)
    return urls


def answer_source_urls(result: dict) -> list[str]:
    answer = str(result.get("answer") or result.get("answer_text") or "")
    urls = re.findall(r"https?://[^\s)]+", answer)
    return [url.rstrip(".,") for url in urls]


def source_url_mismatch(result: dict) -> str:
    selected_urls = selected_source_urls(result)
    answer_urls = answer_source_urls(result)
    if answer_urls and not selected_urls:
        return f"answer has source URL but no selected source URL: {answer_urls[0]}"
    if answer_urls and selected_urls and not any(url in selected_urls for url in answer_urls):
        return f"answer source URLs {answer_urls[:2]} not in selected URLs {selected_urls[:3]}"
    sources = result.get("sources") or []
    if selected_urls and sources:
        first_source = sources[0] if isinstance(sources[0], dict) else {}
        returned_url = str(first_source.get("source") or first_source.get("source_url") or "").strip()
        if returned_url and returned_url != selected_urls[0]:
            return f"sources[0] URL {returned_url} does not match selected top URL {selected_urls[0]}"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    failures: list[str] = []
    rows: list[dict] = []
    for case in REGRESSION_CASES:
        result = call_rag_api(args.base_url, case["query"], args.timeout)
        source_types, titles = summarize_sources(result)
        mismatch = selected_context_has_not_found_mismatch(result)
        citation_mismatch = source_url_mismatch(result)
        forbidden = source_types & case["forbidden_source_types"]
        expected_source_hit = bool(source_types & case["expected_source_types"])
        expected_title_hit = any(term in titles for term in case["expected_title_terms"])
        row = {
            "id": case["id"],
            "query": case["query"],
            "success": result.get("success"),
            "source_types": sorted(source_types),
            "selected_titles": titles[:180],
            "not_found_mismatch": mismatch,
            "source_url_mismatch": citation_mismatch,
        }
        rows.append(row)
        if mismatch:
            failures.append(f"{case['id']}: selected context exists but answer says not found")
        if forbidden:
            failures.append(f"{case['id']}: forbidden source types {sorted(forbidden)}")
        if not expected_source_hit:
            failures.append(f"{case['id']}: expected one of {sorted(case['expected_source_types'])}, got {sorted(source_types)}")
        if not expected_title_hit:
            failures.append(f"{case['id']}: expected title terms {sorted(case['expected_title_terms'])}, got {titles[:180]}")
        if citation_mismatch:
            failures.append(f"{case['id']}: {citation_mismatch}")

    print(json.dumps({"rows": rows, "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
