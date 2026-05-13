"""Shared Korean tokenization and fallback normalization rules."""

from __future__ import annotations

import re
from typing import Iterable

TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")
ASCII_OR_DIGIT_RE = re.compile(r"[a-z0-9]")
PARTICLE_SUFFIX_RE = re.compile(
    r"(으로써|으로서|에게서|으로|에서|부터|까지|에게|께서|하고|거나|라도|"
    r"은|는|이|가|을|를|의|에|로|도|만|와|과|랑)$"
)
ENDING_SUFFIX_RE = re.compile(r"(인가요|나요|어요|예요|이에요|야|요)$")

QUERY_FILLERS = {
    "알려줘",
    "알려주세요",
    "궁금해",
    "궁금합니다",
    "뭐야",
    "뭐",
    "무엇",
    "무슨",
    "어떤",
    "어떻게해",
    "어떻게",
    "언제야",
    "언제",
    "어디서",
    "어디",
    "봐",
    "보나요",
    "좀",
    "좀요",
    "요",
    "해",
    "줘",
    "주세요",
    "알려줄래",
    "가능",
    "가능해",
    "있나요",
    "있어",
}

CANDIDATE_STOPWORDS = {
    "관련",
    "문서",
    "보고서",
    "발표",
    "의무",
    "방법",
    "내용",
    "안내",
    "경우",
}


def regex_tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def normalize_token(token: str) -> str:
    normalized = token.strip().lower()
    if len(normalized) > 1:
        normalized = PARTICLE_SUFFIX_RE.sub("", normalized)
    if len(normalized) > 1:
        normalized = ENDING_SUFFIX_RE.sub("", normalized)
    if normalized == "어떻게해":
        return "어떻게"
    return normalized


def normalize_candidate(term: str) -> str:
    normalized = normalize_token(term)
    if not normalized or normalized in CANDIDATE_STOPWORDS:
        return ""
    if is_weak_token(normalized):
        return ""
    if not TOKEN_RE.fullmatch(normalized):
        return ""
    return normalized


def regex_lexical_terms(text: str) -> list[str]:
    return [
        token
        for token in ordered_unique(normalize_token(token) for token in regex_tokens(text))
        if token and token not in QUERY_FILLERS and not is_weak_token(token)
    ]


def is_weak_token(token: str) -> bool:
    return len(token) <= 1 and not ASCII_OR_DIGIT_RE.fullmatch(token)


def ordered_unique(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped
