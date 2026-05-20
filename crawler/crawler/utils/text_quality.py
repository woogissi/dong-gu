from __future__ import annotations

import re
import string
from typing import Any


TEXT_CONTROL_CHARS = {"\n", "\r", "\t"}
PRINTABLE_ASCII = set(string.printable)
STRONG_BINARY_MARKERS = ("%PDF", "HWP Document File")
DOCUMENT_BINARY_MARKERS = {
    "%PDF": "pdf_header",
    "stream": "pdf_stream",
    "endobj": "pdf_endobj",
    "xref": "pdf_xref",
    "%%EOF": "pdf_eof",
    "HWP Document File": "hwp_binary_marker",
    "\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1": "ole_compound_file_marker",
    "D0 CF 11 E0 A1 B1 1A E1": "ole_compound_file_marker",
}
ESCAPED_NUL_RE = re.compile(r"\\u0000", re.IGNORECASE)
KOREAN_RE = re.compile(r"[가-힣]")
ENGLISH_RE = re.compile(r"[A-Za-z]")
DIGIT_RE = re.compile(r"\d")
REPEATED_CHAR_RE = re.compile(r"(.)\1{4,}", re.DOTALL)

MIN_ATTACHMENT_TEXT_LENGTH = 50
MIN_ATTACHMENT_TEXT_PER_PAGE = 80


def strip_nul_text(text: str | None) -> str | None:
    if text is None:
        return None
    return ESCAPED_NUL_RE.sub("", text.replace("\x00", ""))


def strip_nul_value(value):
    if isinstance(value, str):
        return strip_nul_text(value)
    if isinstance(value, dict):
        return {strip_nul_value(key): strip_nul_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [strip_nul_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(strip_nul_value(item) for item in value)
    return value


def detect_binary_markers(text: str | None) -> list[str]:
    if not text:
        return []

    found = []
    lower_text = text.lower()
    for marker, reason in DOCUMENT_BINARY_MARKERS.items():
        haystack = lower_text if marker.isascii() else text
        needle = marker.lower() if marker.isascii() else marker
        if needle in haystack and reason not in found:
            found.append(reason)
    return found


def text_quality_report(text: str | None) -> dict[str, float | int | bool | str | list[str]]:
    if not text:
        return {
            "length": 0,
            "nul_count": 0,
            "escaped_nul_count": 0,
            "control_ratio": 0.0,
            "replacement_ratio": 0.0,
            "has_binary_marker": False,
            "is_binary_like": False,
            "reason": "empty",
        }

    length = len(text)
    nul_count = text.count("\x00")
    escaped_nul_count = len(ESCAPED_NUL_RE.findall(text))
    replacement_count = text.count("\ufffd")
    control_count = sum(
        1
        for char in text
        if ord(char) < 32 and char not in TEXT_CONTROL_CHARS
    )
    control_ratio = control_count / length
    replacement_ratio = replacement_count / length
    binary_markers = detect_binary_markers(text)
    has_strong_binary_marker = any(marker in text for marker in STRONG_BINARY_MARKERS)
    has_pdf_object_markers = "stream" in text and "endobj" in text

    reasons = []
    if nul_count or escaped_nul_count:
        reasons.append("contains_nul")
    if control_ratio > 0.01:
        reasons.append("high_control_char_ratio")
    if replacement_ratio > 0.02:
        reasons.append("high_replacement_char_ratio")
    if binary_markers or has_strong_binary_marker or has_pdf_object_markers:
        reasons.append("binary_marker")

    return {
        "length": length,
        "nul_count": nul_count,
        "escaped_nul_count": escaped_nul_count,
        "control_ratio": round(control_ratio, 6),
        "replacement_ratio": round(replacement_ratio, 6),
        "has_binary_marker": bool(binary_markers or has_strong_binary_marker or has_pdf_object_markers),
        "binary_markers": binary_markers,
        "is_binary_like": bool(reasons),
        "reason": ",".join(reasons) if reasons else "ok",
    }


def _safe_ratio(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _repeated_char_ratio(text: str) -> float:
    repeated_chars = sum(len(match.group(0)) for match in REPEATED_CHAR_RE.finditer(text))
    return _safe_ratio(repeated_chars, len(text))


def _table_count(tables: Any) -> int:
    if not tables:
        return 0
    if isinstance(tables, (list, tuple, set)):
        return len(tables)
    return 1


def _parser_empty_status(parser_name: str | None, parser_status: str | None) -> str:
    if parser_status:
        return parser_status
    if parser_name and "ocr" in parser_name.lower():
        return "ocr_empty_text"
    return "parser_empty_text"


def attachment_text_quality_report(
    text: str | None,
    *,
    parser_name: str | None = None,
    parser_status: str | None = None,
    page_count: int | None = None,
    tables: Any = None,
    min_text_length: int = MIN_ATTACHMENT_TEXT_LENGTH,
    min_text_per_page: int = MIN_ATTACHMENT_TEXT_PER_PAGE,
) -> dict[str, object]:
    base = text_quality_report(text)
    value = text or ""
    stripped = value.strip()
    length = len(stripped)
    pages = int(page_count or 0)
    text_per_page = round(length / pages, 2) if pages > 0 else length
    table_count = _table_count(tables)
    table_detected = table_count > 0

    korean_count = len(KOREAN_RE.findall(value))
    english_count = len(ENGLISH_RE.findall(value))
    digit_count = len(DIGIT_RE.findall(value))
    meaningful_count = korean_count + english_count + digit_count
    whitespace_count = sum(1 for char in value if char.isspace())

    korean_ratio = _safe_ratio(korean_count, len(value))
    english_ratio = _safe_ratio(english_count, len(value))
    digit_ratio = _safe_ratio(digit_count, len(value))
    meaningful_ratio = _safe_ratio(meaningful_count, len(value))
    whitespace_ratio = _safe_ratio(whitespace_count, len(value))
    repeated_char_ratio = _repeated_char_ratio(value)

    reasons: list[str] = []
    status = parser_status or "parser_success"
    quality_status = "ok"

    if not stripped:
        status = _parser_empty_status(parser_name, parser_status)
        quality_status = "parse_failed"
        reasons.append(status)
    elif base["is_binary_like"]:
        status = "binary_marker_detected" if base["has_binary_marker"] else "parser_failed"
        quality_status = "parse_failed"
        reasons.extend(str(base["reason"]).split(","))
    else:
        if length < min_text_length and not table_detected:
            reasons.append("too_short")
        if pages > 0 and text_per_page < min_text_per_page and not table_detected:
            reasons.append("low_text_per_page")
        if meaningful_ratio < 0.35:
            reasons.append("low_meaningful_char_ratio")
        if repeated_char_ratio > 0.2:
            reasons.append("high_repeated_char_ratio")
        if float(base["replacement_ratio"]) > 0.01:
            reasons.append("high_replacement_char_ratio")
        if float(base["control_ratio"]) > 0.005:
            reasons.append("high_control_char_ratio")
        if whitespace_ratio > 0.65:
            reasons.append("high_whitespace_ratio")

        severe_reasons = {
            "high_repeated_char_ratio",
            "high_replacement_char_ratio",
            "high_control_char_ratio",
        }
        if any(reason in severe_reasons for reason in reasons):
            quality_status = "parse_failed"
        elif reasons:
            quality_status = "needs_review"

    quality_reason = ",".join(dict.fromkeys(reasons)) if reasons else "ok"

    return {
        "parser_name": parser_name,
        "parser_status": status,
        "extracted_text_length": length,
        "page_count": pages,
        "text_per_page": text_per_page,
        "korean_ratio": korean_ratio,
        "english_ratio": english_ratio,
        "digit_ratio": digit_ratio,
        "meaningful_char_ratio": meaningful_ratio,
        "binary_marker_detected": bool(base["has_binary_marker"]),
        "table_detected": table_detected,
        "table_count": table_count,
        "repeated_char_ratio": repeated_char_ratio,
        "replacement_ratio": base["replacement_ratio"],
        "control_ratio": base["control_ratio"],
        "whitespace_ratio": whitespace_ratio,
        "quality_status": quality_status,
        "quality_reason": quality_reason,
        "is_binary_like": bool(base["is_binary_like"]),
        "binary_markers": base.get("binary_markers", []),
    }


def is_binary_like_text(text: str | None) -> bool:
    return bool(text_quality_report(text)["is_binary_like"])


def document_quality_report(doc: dict) -> dict[str, object]:
    fields = {
        "normalize": doc.get("normalize"),
        "clean_text": doc.get("clean_text"),
        "raw_text": doc.get("raw_text"),
        "table_text": doc.get("table_text"),
        "attachment_text": doc.get("attachment_text"),
        "image_text": doc.get("image_text"),
        "html": doc.get("html"),
    }
    for index, item in enumerate(doc.get("downloaded_attachments", []) or [], start=1):
        fields[f"downloaded_attachments[{index}].attachment_text"] = item.get("attachment_text")
    field_reports = {
        name: text_quality_report(value)
        for name, value in fields.items()
        if value
    }
    bad_fields = [
        name
        for name, report in field_reports.items()
        if report["is_binary_like"]
    ]
    return {
        "is_binary_like": bool(bad_fields),
        "bad_fields": bad_fields,
        "fields": field_reports,
    }
