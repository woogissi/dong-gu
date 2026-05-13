"""질문 리라이팅 모듈.

검색 역할별 쿼리를 분리하고, 원문에 드러난 intent/entity 조합에만
조건부 확장을 적용한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from rag.preprocess.domain_knowledge import (
    CATEGORY_BY_REWRITE_ENTITY,
    CONDITIONAL_EXPANSION_RULES,
    ENTITY_LEXICON,
    EXPANSIONS_REQUIRING_SOURCE_TERM,
    GENERIC_INTENT_EXPANSIONS,
    REWRITE_ENTITY_GROUPS,
    REWRITE_ENTITY_SURFACES,
    REWRITE_ENTITY_SYNONYMS,
)
from rag.preprocess.hybrid_keyword_extractor import (
    extract_kiwi_candidates,
    extract_kiwi_token_terms,
)
from rag.preprocess.query_analysis import QueryAnalysisResult
from rag.preprocess.tokenizer import (
    QUERY_FILLERS,
    normalize_token,
    ordered_unique,
    regex_tokens,
    is_weak_token,
)


@dataclass(frozen=True)
class RewrittenQuery:
    original: str
    semantic_query: str
    keyword_query: str
    entity_query: str
    intent: str | None
    entities: list[str]
    rewrite_entities: list[str] = field(default_factory=list)
    filters: dict[str, str | list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_FILLERS = QUERY_FILLERS

_INTENT_TRIGGERS: dict[str, tuple[str, ...]] = {
    "기간": ("언제", "언제야", "기간", "일정", "마감", "마감일", "기한", "까지"),
    "방법": ("방법", "어떻게", "어떻게해", "절차", "어디서"),
    "확인": ("확인", "조회", "열람", "봐", "보다", "결과", "고지서"),
    "신청": ("신청", "접수", "지원"),
    "자격": ("자격", "대상", "요건", "조건"),
    "서류": ("서류", "제출서류", "필요서류", "신청서", "양식"),
}
_INTENT_PRIORITY = ("기간", "방법", "확인", "신청", "자격", "서류")

@dataclass(frozen=True)
class _ExpansionRule:
    intents: tuple[str, ...]
    entities: tuple[str, ...] = ()
    entity_groups: tuple[str, ...] = ()
    expansions: tuple[str, ...] = ()


_CONDITIONAL_EXPANSION_RULES = tuple(
    _ExpansionRule(
        intents=rule["intents"],
        entities=rule["entities"],
        entity_groups=rule["entity_groups"],
        expansions=rule["expansions"],
    )
    for rule in CONDITIONAL_EXPANSION_RULES
)
_EXPANSIONS_REQUIRING_SOURCE_TERM = EXPANSIONS_REQUIRING_SOURCE_TERM
_CATEGORY_BY_ENTITY = CATEGORY_BY_REWRITE_ENTITY
_ENTITY_SURFACES = REWRITE_ENTITY_SURFACES
_ENTITY_SYNONYMS = REWRITE_ENTITY_SYNONYMS
_ENTITY_GROUPS = REWRITE_ENTITY_GROUPS
_GENERIC_INTENT_EXPANSIONS = GENERIC_INTENT_EXPANSIONS


def rewrite_query(
    query: str,
    keywords: list[str],
    entities: dict[str, list[str]] | None = None,
    analysis: QueryAnalysisResult | None = None,
) -> RewrittenQuery:
    original = query.strip()
    if not original:
        return RewrittenQuery(
            original="",
            semantic_query="",
            keyword_query="",
            entity_query="",
            intent=None,
            entities=[],
            filters={},
        )

    token_info = _TokenInfo.from_analysis(analysis) if analysis else _TokenInfo.from_text(original)
    detected_entities = (
        analysis.rewrite_entities
        if analysis and analysis.rewrite_entities
        else _detect_entities(original, keywords, token_info)
    )
    intent = analysis.intent if analysis and analysis.intent else _detect_intent(token_info)
    filters = _build_filters(detected_entities, entities or (analysis.extracted_entities if analysis else {}))
    keyword_terms = _keyword_terms(
        original,
        keywords,
        token_info,
        detected_entities,
        intent,
        noun_terms=analysis.noun_terms if analysis else None,
    )
    entity_terms = _entity_terms(detected_entities)

    semantic_query = _build_semantic_query(original, detected_entities, intent)
    keyword_query = " ".join(keyword_terms) or " ".join(token_info.content_tokens) or original
    entity_query = " ".join(entity_terms) or " ".join(detected_entities)

    return RewrittenQuery(
        original=original,
        semantic_query=semantic_query,
        keyword_query=keyword_query,
        entity_query=entity_query,
        intent=intent,
        entities=detected_entities,
        rewrite_entities=detected_entities,
        filters=filters,
    )


def rewrite_queries(
    query: str,
    keywords: list[str],
    entities: dict[str, list[str]] | None = None,
    analysis: QueryAnalysisResult | None = None,
) -> list[str]:
    bundle = rewrite_query(query=query, keywords=keywords, entities=entities, analysis=analysis)
    return rewrite_queries_from_bundle(bundle, query=query, analysis=analysis)


def rewrite_queries_from_bundle(
    bundle: RewrittenQuery,
    *,
    query: str | None = None,
    analysis: QueryAnalysisResult | None = None,
) -> list[str]:
    noun_only = _noun_only_query(query or bundle.original, analysis=analysis)
    return _ordered_unique(
        [
            bundle.keyword_query,
            bundle.entity_query,
            bundle.semantic_query,
            noun_only,
            bundle.original,
        ]
    )


@dataclass(frozen=True)
class _TokenInfo:
    raw_tokens: tuple[str, ...]
    normalized_tokens: tuple[str, ...]
    content_tokens: tuple[str, ...]

    @classmethod
    def from_text(cls, text: str) -> "_TokenInfo":
        raw_tokens = tuple(regex_tokens(text))
        regex_normalized = tuple(_normalize_token(token) for token in raw_tokens)
        kiwi_terms, _ = extract_kiwi_token_terms(text)
        normalized = tuple(_ordered_unique((*regex_normalized, *kiwi_terms)))
        content_source = kiwi_terms or normalized
        content = tuple(
            _ordered_unique(
                token
                for token in content_source
                if token and token not in _FILLERS and not _is_weak_token(token)
            )
        )
        return cls(
            raw_tokens=raw_tokens,
            normalized_tokens=tuple(token for token in normalized if token),
            content_tokens=content,
        )

    @classmethod
    def from_analysis(cls, analysis: QueryAnalysisResult) -> "_TokenInfo":
        raw_tokens = tuple(analysis.tokens)
        regex_normalized = tuple(_normalize_token(token) for token in raw_tokens)
        normalized = tuple(_ordered_unique((*regex_normalized, *analysis.morph_terms)))
        content_source = analysis.morph_terms or normalized
        content = tuple(
            _ordered_unique(
                token
                for token in content_source
                if token and token not in _FILLERS and not _is_weak_token(token)
            )
        )
        return cls(
            raw_tokens=raw_tokens,
            normalized_tokens=tuple(token for token in normalized if token),
            content_tokens=content,
        )

    @property
    def token_set(self) -> set[str]:
        return {*self.raw_tokens, *self.normalized_tokens}


def _normalize_token(token: str) -> str:
    return normalize_token(token)


def _detect_intent(token_info: _TokenInfo) -> str | None:
    token_set = token_info.token_set
    for intent in _INTENT_PRIORITY:
        if any(_trigger_matches(trigger, token_set) for trigger in _INTENT_TRIGGERS[intent]):
            return intent
    return None


def detect_intent(*, analysis: QueryAnalysisResult | None = None, text: str | None = None) -> str | None:
    if analysis is None:
        if text is None:
            return None
        analysis = QueryAnalysisResult(
            raw_text=text,
            normalized_text=text,
            lexical_text=text,
            tokens=regex_tokens(text),
            morph_terms=[],
            noun_terms=[],
            aho_matches=[],
            keywords=[],
            extracted_entities={},
        )
    return _detect_intent(_TokenInfo.from_analysis(analysis))


def _trigger_matches(trigger: str, token_set: set[str]) -> bool:
    normalized = _normalize_token(trigger)
    return trigger in token_set or normalized in token_set


def _detect_entities(
    query: str,
    keywords: list[str],
    token_info: _TokenInfo,
) -> list[str]:
    token_set = token_info.token_set
    keyword_set = {_normalize_token(keyword) for keyword in keywords}
    detected: list[str] = []

    for entity, surfaces in _ENTITY_SURFACES.items():
        terms = (entity, *surfaces, *ENTITY_LEXICON.get(_CATEGORY_BY_ENTITY.get(entity, entity), []))
        if any(_term_matches(term, token_set) for term in terms):
            detected.append(entity)
            continue
        if any(_keyword_is_safe_entity_hint(keyword, entity, token_set) for keyword in keyword_set):
            detected.append(entity)

    # "등록금 고지서 확인"처럼 고지서는 별도 recall entity로 유지한다.
    if "등록금" in detected and _term_matches("고지서", token_set) and "고지서" not in detected:
        detected.append("고지서")

    return _drop_subsumed_terms(_ordered_unique(detected))


def detect_rewrite_entities(
    query: str,
    keywords: list[str],
    *,
    analysis: QueryAnalysisResult | None = None,
) -> list[str]:
    token_info = _TokenInfo.from_analysis(analysis) if analysis else _TokenInfo.from_text(query)
    return _detect_entities(query, keywords, token_info)


def _term_matches(term: str, token_set: set[str]) -> bool:
    normalized = _normalize_token(term)
    return term.lower() in token_set or normalized in token_set


def _keyword_is_safe_entity_hint(keyword: str, entity: str, token_set: set[str]) -> bool:
    if not keyword or keyword not in token_set:
        return False
    return keyword == _normalize_token(entity) or keyword in {
        _normalize_token(surface) for surface in _ENTITY_SURFACES.get(entity, ())
    }


def _build_filters(
    detected_entities: list[str],
    extracted_entities: dict[str, list[str]],
) -> dict[str, str | list[str]]:
    categories = [
        _CATEGORY_BY_ENTITY[entity]
        for entity in detected_entities
        if entity in _CATEGORY_BY_ENTITY
    ]
    filters: dict[str, str | list[str]] = {}
    if categories:
        filters["category"] = _ordered_unique(categories)

    for field in ("target", "department", "time"):
        values = extracted_entities.get(field, [])
        if values:
            filters[field] = _ordered_unique(values)
    return filters


def _keyword_terms(
    query: str,
    keywords: list[str],
    token_info: _TokenInfo,
    entities: list[str],
    intent: str | None,
    noun_terms: list[str] | None = None,
) -> list[str]:
    terms: list[str] = []
    terms.extend(entities)
    terms.extend(_safe_keywords(keywords, token_info))
    if intent:
        terms.append(intent)
        terms.extend(_GENERIC_INTENT_EXPANSIONS.get(intent, ()))
        terms.extend(_conditional_expansions(query, intent, entities, token_info=token_info))
    terms.extend(_noun_only_terms(query, noun_terms=noun_terms))
    return _ordered_unique(_drop_subsumed_terms(terms))


def _safe_keywords(keywords: list[str], token_info: _TokenInfo) -> list[str]:
    token_set = token_info.token_set
    safe: list[str] = []
    for keyword in keywords:
        normalized = _normalize_token(keyword)
        if not normalized or normalized in _FILLERS or _is_weak_token(normalized):
            continue
        if normalized in token_set:
            safe.append(normalized)
    return safe


def _conditional_expansions(
    query: str,
    intent: str,
    entities: list[str],
    *,
    token_info: _TokenInfo | None = None,
) -> list[str]:
    expansions: list[str] = []
    entity_set = set(entities)
    for rule in _CONDITIONAL_EXPANSION_RULES:
        if intent not in rule.intents:
            continue
        if not _expansion_rule_matches_entities(rule, entity_set):
            continue
        expansions.extend(rule.expansions)

    # Negative constraint: 원문에 근거 토큰이 없으면 해당 확장을 만들지 않는다.
    token_set = (token_info or _TokenInfo.from_text(query)).token_set
    expansions = [
        term
        for term in expansions
        if _has_required_source_term(term, token_set)
    ]

    return _ordered_unique(expansions)


def _has_required_source_term(expansion: str, token_set: set[str]) -> bool:
    required = _EXPANSIONS_REQUIRING_SOURCE_TERM.get(expansion)
    return required is None or required in token_set


def _expansion_rule_matches_entities(rule: _ExpansionRule, entities: set[str]) -> bool:
    if entities.intersection(rule.entities):
        return True
    return any(entities.intersection(_ENTITY_GROUPS.get(group, ())) for group in rule.entity_groups)


def _entity_terms(entities: list[str]) -> list[str]:
    terms: list[str] = []
    for entity in entities:
        terms.append(entity)
        terms.extend(_ENTITY_SYNONYMS.get(entity, ()))
    return _ordered_unique(terms)


def _build_semantic_query(original: str, entities: list[str], intent: str | None) -> str:
    suffix_terms: list[str] = []
    if entities and not any(entity in original for entity in entities):
        suffix_terms.extend(entities)
    if intent and intent not in original:
        suffix_terms.append(intent)
    if not suffix_terms:
        return original
    return f"{original} {' '.join(_ordered_unique(suffix_terms))}"


def _noun_only_query(query: str, *, analysis: QueryAnalysisResult | None = None) -> str:
    if analysis is not None:
        return " ".join(
            _noun_only_terms(
                query,
                noun_terms=analysis.noun_terms,
                fallback_terms=list(_TokenInfo.from_analysis(analysis).content_tokens),
            )
        )
    return " ".join(_noun_only_terms(query))


def _noun_only_terms(
    query: str,
    *,
    noun_terms: list[str] | None = None,
    fallback_terms: list[str] | None = None,
) -> list[str]:
    if noun_terms is not None:
        terms = [term for term in noun_terms if term not in _FILLERS]
        return terms or list(fallback_terms or [])
    kiwi_terms, _ = extract_kiwi_candidates(query)
    if kiwi_terms:
        return [term for term in kiwi_terms if term not in _FILLERS]
    token_info = _TokenInfo.from_text(query)
    return list(token_info.content_tokens)


def _drop_subsumed_terms(terms: list[str]) -> list[str]:
    ordered = _ordered_unique(terms)
    by_length = sorted(ordered, key=len, reverse=True)
    kept: list[str] = []
    for term in by_length:
        if any(term != other and term in other for other in kept):
            continue
        kept.append(term)
    return sorted(kept, key=ordered.index)


def _is_weak_token(token: str) -> bool:
    return is_weak_token(token)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return ordered_unique(values)
