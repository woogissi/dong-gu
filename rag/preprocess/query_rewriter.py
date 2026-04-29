"""질문 리라이팅 모듈
- 사용자 질문에서 핵심 키워드와 엔티티를 추출하여 확장
- 의도 확장 규칙과 엔티티 기반 확장 규칙 적용
- 중복 제거 및 정렬된 확장된 질문 리스트 반환"""

# 단순 확장 규칙 기반으로 구현되어 있어 오탐과 과확장이 발생할 수 있음
# - 쿼리 타임 분리로 변경 고려
# - 원문: 휴학 어떻게 해?
# keyword_query: 휴학 신청 방법 절차
# entity_focused_query: 휴학 학적변동 신청기간
# expanded_query: 휴학 신청 절차 기간 필요서류

# TODO: 질문형 제거/정규화 추가
# - 어떻게 해? → 방법
# - 언제야? → 일정
# - 어디서 확인해? → 조회 방법
# expansion 규칙 더 조건부로
# ex) 
# 방법 계열 + 신청 엔티티 -> 절차, 제출처
# 확인 계열 + 장학 엔티티 -> 조회, 선발결과, 지급일

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

# substring match라서 오탐, 과확장 다수 존재
# TODO: 의도 확장 규칙과 엔티티 기반 확장 규칙을 분리하여 적용하는 방식으로 개선 필요
# 형태소 분석 기반 명사/용언 매칭
# 공백 단위 + 사전 lexeme 매칭
def _has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def _collect_entities(query: str, keywords: list[str]) -> set[str]:
    entities: set[str] = set()
    keyword_set = set(keywords)

    for entity, lexemes in ENTITY_LEXICON.items():
        # entity in keyword_set은 exact match인데 _has_any는 substring match라서 오탐, 과확장 다수 존재
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

# category, action, target을 전부 같은 비중으로 추가하여 노이즈 증가 우려
# TODO: 의도 확장 규칙과 엔티티 기반 확장 규칙을 분리하여 적용하는 방식으로 개선 필요
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
    # 현재 가장 확장된 쿼리 반환
    # TODO:추후 best scored rewrite로 변경
    return rewritten_queries[-1]
