"""Temporal query signals and evidence checks for retrieval/reranking."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

_YEAR_PATTERN = re.compile(r"(20\d{2})\s*년?")
# "26년", "25년도" 같은 축약 연도 (2000년대 한정: 20~29)
_YEAR_SHORT_PATTERN = re.compile(r"(?<!\d)(2\d)\s*년")
_SEMESTER_PATTERN = re.compile(r"([12])\s*학기")
_RELATIVE_DATE_TERMS = ("오늘", "내일", "이번학기", "이번 학기", "이번", "지금", "현재")
_RECENCY_TERMS = ("최신", "최근", "최근꺼", "새로", "신규", "올라온", "현재", "오늘", "지금")


def _expand_short_year(short: str) -> str:
    return f"20{short}"


def extract_temporal_signals(
    query: str,
    *,
    keywords: list[str] | None = None,
    filters: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    values = [query or "", *(keywords or [])]
    for field in ("time", "time_scope"):
        values.extend((filters or {}).get(field, []) or [])
    text = " ".join(str(value) for value in values if value)
    normalized = text.replace(" ", "")

    full_years = list(_YEAR_PATTERN.findall(text))
    short_years = [_expand_short_year(y) for y in _YEAR_SHORT_PATTERN.findall(text) if _expand_short_year(y) not in full_years]
    years = _ordered_unique(full_years + short_years)
    semesters = _ordered_unique(f"{match}학기" for match in _SEMESTER_PATTERN.findall(text))
    relative_dates = _ordered_unique(
        term.replace(" ", "") for term in _RELATIVE_DATE_TERMS if term.replace(" ", "") in normalized
    )
    recency_intent = any(term in normalized for term in _RECENCY_TERMS)

    return {
        "years": years,
        "semesters": semesters,
        "relative_dates": relative_dates,
        "recency_intent": recency_intent,
        "has_explicit_temporal": bool(years or semesters or relative_dates or recency_intent),
    }


def temporal_rerank_signals(doc: Any, temporal_signals: dict[str, object] | None) -> dict[str, float]:
    signals = temporal_signals or {}
    years = [str(value) for value in signals.get("years") or [] if value]
    semesters = [str(value) for value in signals.get("semesters") or [] if value]
    recency_intent = bool(signals.get("recency_intent"))
    if not (years or semesters or recency_intent):
        return {
            "temporal_match": 0.0,
            "temporal_mismatch": 0.0,
            "temporal_recency": 0.0,
            "temporal_score": 0.0,
        }

    text = _doc_temporal_text(doc)
    doc_years = _years_for_doc(doc, text)
    doc_semesters = set(_SEMESTER_PATTERN.findall(text))
    expected_semesters = {semester[0] for semester in semesters if semester}

    match = 0.0
    mismatch = 0.0
    year_mismatched = False
    semester_mismatched = False

    if years:
        if any(year in doc_years or year in text for year in years):
            match += 0.9
        elif doc_years:
            mismatch -= 1.5
            year_mismatched = True
    if expected_semesters:
        if expected_semesters & doc_semesters:
            match += 0.65
        elif doc_semesters:
            mismatch -= 1.0
            semester_mismatched = True

    # 연도+학기 모두 명시됐는데 둘 다 불일치 → 추가 패널티
    if years and expected_semesters and year_mismatched and semester_mismatched:
        mismatch -= 0.5

    recency = _recency_score(getattr(doc, "metadata", {}).get("published_at")) * (1.6 if recency_intent else 0.5)
    score = match + mismatch + recency
    return {
        "temporal_match": round(match, 6),
        "temporal_mismatch": round(mismatch, 6),
        "temporal_recency": round(recency, 6),
        "temporal_score": round(score, 6),
    }


def validate_temporal_evidence(docs: list[Any], temporal_signals: dict[str, object] | None) -> dict[str, object]:
    signals = temporal_signals or {}
    years = [str(value) for value in signals.get("years") or [] if value]
    semesters = [str(value) for value in signals.get("semesters") or [] if value]
    needs_validation = bool(years or semesters)
    doc_results = []
    for rank, doc in enumerate(docs, start=1):
        text = _doc_temporal_text(doc)
        doc_years = _years_for_doc(doc, text)
        doc_semesters = set(_SEMESTER_PATTERN.findall(text))
        year_match = not years or any(year in doc_years or year in text for year in years)
        semester_match = not semesters or any(semester[0] in doc_semesters for semester in semesters if semester)
        doc_results.append(
            {
                "rank": rank,
                "doc_id": getattr(doc, "doc_id", None),
                "chunk_id": getattr(doc, "chunk_id", None),
                "title": getattr(doc, "title", ""),
                "years": sorted(doc_years),
                "semesters": sorted(f"{value}학기" for value in doc_semesters),
                "year_match": year_match,
                "semester_match": semester_match,
                "matches": year_match and semester_match,
            }
        )

    matched = any(item["matches"] for item in doc_results)
    # 연도가 명시된 경우, 연도 일치 여부만으로 차단 결정 (학기 불일치는 soft penalty만)
    year_ok = not years or any(item["year_match"] for item in doc_results)
    valid = not needs_validation or year_ok
    missing = []
    if needs_validation and years and not any(item["year_match"] for item in doc_results):
        missing.append("year")
    if needs_validation and semesters and not any(item["semester_match"] for item in doc_results):
        missing.append("semester")
    return {
        "valid": valid,
        "needs_validation": needs_validation,
        "matched": matched,
        "reason": "" if valid else "missing_temporal_evidence",
        "missing": missing,
        "temporal_signals": signals,
        "doc_results": doc_results,
    }


def _doc_temporal_text(doc: Any) -> str:
    metadata = getattr(doc, "metadata", {}) or {}
    values = [
        getattr(doc, "title", ""),
        metadata.get("section_title"),
        getattr(doc, "content", ""),
        metadata.get("published_at"),
        metadata.get("canonical_title"),
    ]
    return " ".join(str(value) for value in values if value).replace(" ", "")


def _years_for_doc(doc: Any, text: str) -> set[str]:
    metadata = getattr(doc, "metadata", {}) or {}
    years = set(_YEAR_PATTERN.findall(text))
    published_at = _parse_date(metadata.get("published_at"))
    if published_at:
        years.add(str(published_at.year))
    return years


def _recency_score(value: Any) -> float:
    published_at = _parse_date(value)
    if published_at is None:
        return 0.0
    age_days = max((date.today() - published_at).days, 0)
    return 0.4 * math.exp(-age_days / 365.0)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    raw_value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw_value[:10], fmt).date()
        except ValueError:
            continue
    return None


def _ordered_unique(values: Any) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
