# crawler/discovery/board_candidate_policy.py

from __future__ import annotations

from urllib.parse import parse_qs, urlparse


BOARD_PAGE_KINDS = {"board_list", "board_detail"}
BOARD_PATH_HINTS = (
    "notice",
    "board",
    "bbs",
    "qna",
    "faq",
    "archive",
)
BOARD_QUERY_KEYS = {
    "articleNo",
    "article.offset",
    "articleLimit",
    "boardNo",
    "bbsId",
}


def board_candidate_reason(url: str, page_kind: str) -> str | None:
    if page_kind in BOARD_PAGE_KINDS:
        return page_kind

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    path = parsed.path.lower()
    query = parse_qs(parsed.query)
    if any(hint in path for hint in BOARD_PATH_HINTS):
        return "board_path_hint"

    mode = query.get("mode", [""])[0].lower()
    if mode in {"list", "view"}:
        return "board_mode_hint"

    if set(query).intersection(BOARD_QUERY_KEYS):
        return "board_query_hint"

    return None


def build_board_candidate_record(
    *,
    url: str,
    page_kind: str,
    discovered_from: str,
    source_type: str,
    source_group: str | None,
    depth: int,
) -> dict | None:
    reason = board_candidate_reason(url, page_kind)
    if not reason:
        return None

    return {
        "url": url,
        "page_kind": page_kind,
        "reason": reason,
        "discovered_from": discovered_from,
        "source_type_hint": source_type,
        "source_group": source_group or source_type,
        "depth": depth,
        "status": "candidate_only",
    }
