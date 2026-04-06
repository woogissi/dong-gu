"""Rewrite query with intent/entity expansion for better retrieval."""

from __future__ import annotations

from rag.preprocess.domain_knowledge import ENTITY_LEXICON


def _has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _collect_entities(query: str, keywords: list[str]) -> set[str]:
    entities: set[str] = set()
    keyword_set = set(keywords)

    for entity, lexemes in ENTITY_LEXICON.items():
        if entity in keyword_set or _has_any(query, lexemes):
            entities.add(entity)

    return entities


def rewrite_query(query: str, keywords: list[str]) -> str:
    if not query:
        return ""

    entities = _collect_entities(query, keywords)
    expanded_terms: list[str] = []

    if _has_any(query, ["언제", "기간", "마감", "기한", "일까지", "까지"]):
        expanded_terms.extend(["기간", "일정", "마감일", "시점"])

    if _has_any(query, ["어디", "어떻게", "방법", "절차"]):
        expanded_terms.extend(["방법", "절차", "안내", "제출처"])

    if "신청" in entities:
        expanded_terms.extend(["신청", "접수", "제출"])
    if "장학" in entities:
        expanded_terms.extend(["장학금", "선발", "지급"])
    if "수강" in entities or "학사" in entities:
        expanded_terms.extend(["수강신청", "정정", "학사공지"])
    if "등록" in entities:
        expanded_terms.extend(["등록금", "납부", "고지서"])
    if "졸업" in entities:
        expanded_terms.extend(["졸업요건", "졸업학점", "제출서류"])
    if "휴학" in entities or "복학" in entities:
        expanded_terms.extend(["신청기간", "복학절차", "학적변동"])

    deduped: list[str] = []
    seen: set[str] = set()
    for term in [*keywords, *sorted(entities), *expanded_terms]:
        if term and term not in seen:
            deduped.append(term)
            seen.add(term)

    if not deduped:
        return query
    return f"{query} {' '.join(deduped)}".strip()
