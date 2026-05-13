from __future__ import annotations

import string


TEXT_CONTROL_CHARS = {"\n", "\r", "\t"}
PRINTABLE_ASCII = set(string.printable)
STRONG_BINARY_MARKERS = ("%PDF", "HWP Document File")


def text_quality_report(text: str | None) -> dict[str, float | int | bool | str]:
    if not text:
        return {
            "length": 0,
            "nul_count": 0,
            "control_ratio": 0.0,
            "replacement_ratio": 0.0,
            "has_binary_marker": False,
            "is_binary_like": False,
            "reason": "empty",
        }

    length = len(text)
    nul_count = text.count("\x00")
    replacement_count = text.count("\ufffd")
    control_count = sum(
        1
        for char in text
        if ord(char) < 32 and char not in TEXT_CONTROL_CHARS
    )
    control_ratio = control_count / length
    replacement_ratio = replacement_count / length
    has_strong_binary_marker = any(marker in text for marker in STRONG_BINARY_MARKERS)
    has_pdf_object_markers = "stream" in text and "endobj" in text

    reasons = []
    if nul_count:
        reasons.append("contains_nul")
    if control_ratio > 0.01:
        reasons.append("high_control_char_ratio")
    if replacement_ratio > 0.02:
        reasons.append("high_replacement_char_ratio")
    if has_strong_binary_marker or has_pdf_object_markers:
        reasons.append("binary_marker")

    return {
        "length": length,
        "nul_count": nul_count,
        "control_ratio": round(control_ratio, 6),
        "replacement_ratio": round(replacement_ratio, 6),
        "has_binary_marker": has_strong_binary_marker or has_pdf_object_markers,
        "is_binary_like": bool(reasons),
        "reason": ",".join(reasons) if reasons else "ok",
    }


def is_binary_like_text(text: str | None) -> bool:
    return bool(text_quality_report(text)["is_binary_like"])


def document_quality_report(doc: dict) -> dict[str, object]:
    fields = {
        "normalize": doc.get("normalize"),
        "raw_text": doc.get("raw_text"),
        "attachment_text": doc.get("attachment_text"),
        "image_text": doc.get("image_text"),
    }
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
