"""Rewrite query with intent/entity expansion for better retrieval."""

from __future__ import annotations

from rag.preprocess.domain_knowledge import ENTITY_LEXICON

_INTENT_EXPANSION_RULES: dict[tuple[str, ...], list[str]] = {
    ("언제", "기간", "마감", "기한", "일까지", "까지"): ["기간", "일정", "마감일", "시점"],
    ("어디", "어떻게", "방법", "절차"): ["방법", "절차", "안내", "제출처"],
    ("확인", "조회", "알려줘", "알려주세요", "궁금", "뭐", "무엇"): ["확인", "조회", "안내"],
    ("신청", "접수", "지원"): ["신청", "접수", "제출"],
    ("취소", "철회"): ["취소", "철회", "변경"],
}

_ENTITY_EXPANSION_RULES: dict[str, list[str]] = {
    "신청": ["신청", "접수", "제출"],
    "장학": ["장학금", "선발", "지급"],
    "수강": ["수강신청", "정정", "학사공지"],
    "학사": ["수강신청", "정정", "학사공지"],
    "등록": ["등록금", "납부", "고지서"],
    "졸업": ["졸업요건", "졸업학점", "제출서류"],
    "휴학": ["신청기간", "복학절차", "학적변동"],
    "복학": ["신청기간", "복학절차", "학적변동"],
}

_ENTITY_MAP_FIELDS = ("category", "action", "target")


def _has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _collect_entities(query: str, keywords: list[str]) -> set[str]:
    entities: set[str] = set()
    keyword_set = set(keywords)

    for entity, lexemes in ENTITY_LEXICON.items():
        if entity in keyword_set or _has_any(query, lexemes):
            entities.add(entity)

    return entities


def _ordered_unique(terms: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()

    for term in terms:
        normalized = term.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)

    return deduped


def _intent_expansions(query: str, entities: set[str], entity_map: dict[str, list[str]]) -> list[str]:
    expanded_terms: list[str] = []

    for triggers, expansions in _INTENT_EXPANSION_RULES.items():
        if _has_any(query, list(triggers)):
            expanded_terms.extend(expansions)

    for entity, expansions in _ENTITY_EXPANSION_RULES.items():
        if entity in entities:
            expanded_terms.extend(expansions)

    for field in _ENTITY_MAP_FIELDS:
        expanded_terms.extend(entity_map.get(field, []))

    return _ordered_unique(expanded_terms)


def rewrite_queries(
    query: str,
    keywords: list[str],
    entities: dict[str, list[str]] | None = None,
) -> list[str]:
    if not query:
        return []

    collected_entities = _collect_entities(query, keywords)
    entity_map = entities or {}
    compact_terms = _ordered_unique([*keywords, *sorted(collected_entities)])
    expansion_terms = _intent_expansions(query, collected_entities, entity_map)

    queries = [query]

    if compact_terms:
        queries.append(f"{query} {' '.join(compact_terms)}".strip())

    if expansion_terms:
        queries.append(f"{query} {' '.join(expansion_terms)}".strip())

    if compact_terms and expansion_terms:
        queries.append(
            f"{query} {' '.join(_ordered_unique([*compact_terms, *expansion_terms]))}".strip()
        )

    return _ordered_unique(queries)


def rewrite_query(
    query: str,
    keywords: list[str],
    entities: dict[str, list[str]] | None = None,
) -> str:
    rewritten_queries = rewrite_queries(
        query=query,
        keywords=keywords,
        entities=entities,
    )
    if not rewritten_queries:
        return ""
    return rewritten_queries[-1]
