"""질문 리라이팅 모듈.

검색 역할별 쿼리를 분리하고, 원문에 드러난 intent/entity 조합에만
조건부 확장을 적용한다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Iterable

from rag.preprocess.domain_knowledge import ENTITY_LEXICON
from rag.preprocess.hybrid_keyword_extractor import extract_kiwi_candidates


@dataclass(frozen=True)
class RewrittenQuery:
    original: str
    semantic_query: str
    keyword_query: str
    entity_query: str
    intent: str | None
    entities: list[str]
    filters: dict[str, str | list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")
_PARTICLE_SUFFIX_RE = re.compile(
    r"(으로써|으로서|에게서|으로|에서|부터|까지|에게|께서|하고|거나|라도|"
    r"은|는|이|가|을|를|의|에|로|도|만|와|과)$"
)
_ENDING_SUFFIX_RE = re.compile(r"(인가요|나요|어요|예요|이에요|야|요)$")

_FILLERS = {
    "알려줘",
    "알려주세요",
    "궁금해",
    "궁금합니다",
    "뭐야",
    "뭐",
    "무엇",
    "어떻게해",
    "어떻게",
    "언제야",
    "언제",
    "어디서",
    "어디",
    "봐",
    "보나요",
    "좀",
    "요",
    "해",
    "주세요",
}

_INTENT_TRIGGERS: dict[str, tuple[str, ...]] = {
    "기간": ("언제", "언제야", "기간", "일정", "마감", "마감일", "기한", "까지"),
    "방법": ("방법", "어떻게", "어떻게해", "절차", "어디서"),
    "확인": ("확인", "조회", "열람", "봐", "보다", "결과", "고지서"),
    "신청": ("신청", "접수", "지원"),
    "자격": ("자격", "대상", "요건", "조건"),
    "서류": ("서류", "제출서류", "필요서류", "신청서", "양식"),
}
_INTENT_PRIORITY = ("기간", "방법", "확인", "신청", "자격", "서류")

_CATEGORY_BY_ENTITY: dict[str, str] = {
    "휴학": "휴학",
    "복학": "복학",
    "장학금": "장학",
    "장학": "장학",
    "등록금": "등록",
    "고지서": "등록",
    "수강신청": "수강",
    "수강": "수강",
    "학사공지": "학사",
    "졸업": "졸업",
    "기숙사": "기숙사",
    "생활관": "기숙사",
}

_ENTITY_SURFACES: dict[str, tuple[str, ...]] = {
    "휴학": ("휴학", "군휴학", "일반휴학"),
    "복학": ("복학", "복학신청"),
    "장학금": ("장학금", "국가장학", "근로장학"),
    "장학": ("장학",),
    "등록금": ("등록금", "수업료", "학비"),
    "고지서": ("고지서",),
    "수강신청": ("수강신청", "강의신청"),
    "수강": ("수강", "강의"),
    "학사공지": ("학사공지",),
    "졸업": ("졸업", "졸업요건", "졸업학점", "논문"),
    "기숙사": ("기숙사",),
    "생활관": ("생활관",),
}

_ENTITY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "장학금": ("국가장학", "근로장학", "학자금지원"),
    "등록금": ("수업료", "학비"),
    "수강신청": ("강의신청",),
    "기숙사": ("생활관",),
    "생활관": ("기숙사",),
}

_GENERIC_INTENT_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "기간": ("기간", "일정", "마감일"),
    "방법": ("방법", "절차"),
    "확인": ("조회",),
    "신청": ("신청", "접수"),
    "자격": ("자격", "대상"),
    "서류": ("서류", "제출서류"),
}

_CONDITIONAL_EXPANSIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("방법", "휴학"): ("신청", "절차", "제출처", "필요서류"),
    ("신청", "휴학"): ("신청", "접수", "제출처", "필요서류"),
    ("기간", "휴학"): ("신청기간", "일정", "마감일"),
    ("확인", "장학금"): ("조회", "선발결과", "지급일"),
    ("확인", "장학"): ("조회", "선발결과", "지급일"),
    ("확인", "등록금"): ("고지서", "조회", "납부금액"),
    ("확인", "고지서"): ("고지서", "조회", "납부금액"),
}


def rewrite_query(
    query: str,
    keywords: list[str],
    entities: dict[str, list[str]] | None = None,
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

    token_info = _TokenInfo.from_text(original)
    detected_entities = _detect_entities(original, keywords, token_info)
    intent = _detect_intent(token_info)
    filters = _build_filters(detected_entities, entities or {})
    keyword_terms = _keyword_terms(original, keywords, token_info, detected_entities, intent)
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
        filters=filters,
    )


def rewrite_queries(
    query: str,
    keywords: list[str],
    entities: dict[str, list[str]] | None = None,
) -> list[str]:
    bundle = rewrite_query(query=query, keywords=keywords, entities=entities)
    noun_only = _noun_only_query(query)
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
        raw_tokens = tuple(token.lower() for token in _TOKEN_RE.findall(text))
        normalized = tuple(_normalize_token(token) for token in raw_tokens)
        content = tuple(
            dict.fromkeys(
                token
                for token in normalized
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
    normalized = token.strip().lower()
    if len(normalized) > 1:
        normalized = _PARTICLE_SUFFIX_RE.sub("", normalized)
    if len(normalized) > 1:
        normalized = _ENDING_SUFFIX_RE.sub("", normalized)
    if normalized == "어떻게해":
        return "어떻게"
    if normalized == "언제":
        return "언제"
    return normalized


def _detect_intent(token_info: _TokenInfo) -> str | None:
    token_set = token_info.token_set
    for intent in _INTENT_PRIORITY:
        if any(_trigger_matches(trigger, token_set) for trigger in _INTENT_TRIGGERS[intent]):
            return intent
    return None


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
) -> list[str]:
    terms: list[str] = []
    terms.extend(entities)
    terms.extend(_safe_keywords(keywords, token_info))
    if intent:
        terms.append(intent)
        terms.extend(_GENERIC_INTENT_EXPANSIONS.get(intent, ()))
        terms.extend(_conditional_expansions(query, intent, entities))
    terms.extend(_noun_only_terms(query))
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


def _conditional_expansions(query: str, intent: str, entities: list[str]) -> list[str]:
    expansions: list[str] = []
    for entity in entities:
        expansions.extend(_CONDITIONAL_EXPANSIONS.get((intent, entity), ()))

    # Negative constraint: 원문에 납부 의도가 없으면 납부방법을 만들지 않는다.
    token_set = _TokenInfo.from_text(query).token_set
    if "납부" not in token_set:
        expansions = [term for term in expansions if term != "납부방법"]

    return expansions


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


def _noun_only_query(query: str) -> str:
    return " ".join(_noun_only_terms(query))


def _noun_only_terms(query: str) -> list[str]:
    kiwi_terms, _ = extract_kiwi_candidates(query)
    if kiwi_terms:
        return [term for term in kiwi_terms if term not in _FILLERS]
    token_info = _TokenInfo.from_text(query)
    return list(token_info.content_tokens)


def _drop_subsumed_terms(terms: list[str]) -> list[str]:
    ordered = _ordered_unique(terms)
    kept: list[str] = []
    for term in ordered:
        if any(term != other and term in other for other in ordered if len(other) > len(term)):
            continue
        kept.append(term)
    return kept


def _is_weak_token(token: str) -> bool:
    return len(token) <= 1 and not re.fullmatch(r"[a-z0-9]", token)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return deduped
