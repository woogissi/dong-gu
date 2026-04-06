"""Rule-based keyword extraction for Korean campus Q&A."""

from __future__ import annotations

import re
from collections import OrderedDict

from rag.preprocess.domain_knowledge import ENTITY_LEXICON


_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "에", "의",
    "좀", "좀요", "요", "해", "줘", "주세요",
    "알려줘", "알려주세요", "궁금해", "궁금합니다",
    "가능", "있어", "있나요", "뭐", "무엇", "어디",
}

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]+", text)


def extract_keywords(query: str) -> list[str]:
    if not query:
        return []

    ordered: OrderedDict[str, None] = OrderedDict()

    for token in _tokenize(query):
        normalized = token.lower().strip()
        if len(normalized) <= 1 or normalized in _STOPWORDS:
            continue
        ordered.setdefault(normalized, None)

    for entity, lexemes in ENTITY_LEXICON.items():
        if any(lexeme in query for lexeme in lexemes):
            ordered.setdefault(entity, None)

    return list(ordered.keys())[:12]
