from __future__ import annotations

import re
from hashlib import sha1
from typing import Any
from urllib.parse import urlparse


CENTRAL_SOURCE_TYPES = {
    "academic",
    "academic_notice",
    "academic_calendar",
    "academic_support",
    "homepage",
    "institution",
    "notice",
}

DEPARTMENT_COPY_PATH = re.compile(r"/[a-z0-9_-]+/sub0[567]_\d+\.do", re.IGNORECASE)
TITLE_NOISE_PREFIX = re.compile(r"^\s*(?:\[[^\]]+\]\s*)+")
TITLE_BRACKET_NOTE = re.compile(r"\s*\([^)]*\)\s*$")


def canonical_notice_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    title = str(doc.get("title") or "")
    source_url = str(doc.get("source_url") or "")
    source_type = str(doc.get("source_type") or "")
    content_hash = str(doc.get("content_hash") or "")
    normalized_title = normalize_notice_title(title)
    source_rank = canonical_source_rank(source_url=source_url, source_type=source_type)
    notice_family = infer_notice_family(normalized_title, source_url)
    duplicate_kind = "department_copy" if source_rank >= 80 else ""
    canonical_group = build_canonical_group(
        normalized_title=normalized_title,
        notice_family=notice_family,
        content_hash=content_hash,
    )
    return {
        "canonical_title": normalized_title,
        "canonical_group": canonical_group,
        "canonical_notice_family": notice_family,
        "canonical_source_rank": source_rank,
        "is_canonical_notice": bool(notice_family and source_rank <= 30),
        "duplicate_kind": duplicate_kind,
    }


def normalize_notice_title(title: str) -> str:
    value = re.sub(r"\s+", " ", title or "").strip()
    value = TITLE_NOISE_PREFIX.sub("", value)
    value = re.sub(r"\s*\|\s*.*$", "", value).strip()
    value = TITLE_BRACKET_NOTE.sub("", value).strip()
    value = value.replace("2026-1학기", "2026학년도 1학기")
    value = value.replace("2026-하계", "2026학년도 하계")
    return value


def infer_notice_family(title: str, source_url: str = "") -> str:
    text = f"{title} {source_url}"
    if "수강신청" in text:
        return "course_registration"
    if "계절수업" in text or "계절학기" in text:
        return "seasonal_course_registration"
    if "학사일정" in text or "보강일정" in text or "scheduleList" in text:
        return "academic_schedule"
    return ""


def canonical_source_rank(*, source_url: str, source_type: str) -> int:
    parsed = urlparse(source_url or "")
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    source_type = (source_type or "").lower()

    if host == "dess.deu.ac.kr":
        return 5
    if host in {"www.deu.ac.kr", "deu.ac.kr"} and path.startswith("/www/"):
        if "schedule" in path:
            return 8
        if source_type in {"academic_notice", "academic_support", "academic", "notice"}:
            return 10
        return 20
    if source_type in {"academic_notice", "academic_support", "academic_calendar"}:
        return 15
    if source_type in CENTRAL_SOURCE_TYPES:
        return 30
    if source_type == "department" or DEPARTMENT_COPY_PATH.search(path):
        return 90
    return 60


def build_canonical_group(*, normalized_title: str, notice_family: str, content_hash: str = "") -> str:
    if not notice_family:
        return ""
    title_key = re.sub(r"[^0-9A-Za-z가-힣]+", "", normalized_title).casefold()
    if not title_key and content_hash:
        title_key = content_hash[:16]
    digest = sha1(title_key.encode("utf-8")).hexdigest()[:12] if title_key else "unknown"
    return f"{notice_family}:{digest}"
