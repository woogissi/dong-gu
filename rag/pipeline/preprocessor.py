"""질문 전처리 모듈"""

from __future__ import annotations

from collections import deque

from rag.pipeline.state import PipelineState
from rag.preprocess.domain_knowledge import ENTITY_LEXICON
from rag.preprocess.normalizer import normalize_query
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.entity_extractor import build_filters, extract_entities, primary_category
from rag.preprocess.query_rewriter import rewrite_queries


_SYNONYMS: dict[str, tuple[str, ...]] = {
    "장학금": ("학자금", "학자금 지원"),
    "국가장학": ("국가장학금", "학자금 지원"),
    "등록금": ("수업료", "학비"),
    "기숙사": ("생활관",),
    "생활관": ("기숙사",),
    "수강신청": ("강의신청",),
    "교환학생": ("국제교류",),
}
_AHO_OUTPUT = "_out"
_AHO_FAIL = "_fail"


def _build_aho_automaton(patterns: set[str]) -> dict[str, object]:
    root: dict[str, object] = {_AHO_OUTPUT: []}

    for pattern in patterns:
        if not pattern:
            continue
        node = root
        for char in pattern:
            node = node.setdefault(char, {_AHO_OUTPUT: []})  # type: ignore[assignment]
        node[_AHO_OUTPUT].append(pattern)  # type: ignore[index]

    queue: deque[dict[str, object]] = deque()
    for char, child in tuple(root.items()):
        if char == _AHO_OUTPUT:
            continue
        child[_AHO_FAIL] = root  # type: ignore[index]
        queue.append(child)  # type: ignore[arg-type]

    while queue:
        node = queue.popleft()
        fail_node = node[_AHO_FAIL]  # type: ignore[index]
        node[_AHO_OUTPUT].extend(fail_node.get(_AHO_OUTPUT, []))  # type: ignore[union-attr,index]

        for char, child in tuple(node.items()):
            if char in {_AHO_OUTPUT, _AHO_FAIL}:
                continue
            next_fail = fail_node
            while next_fail is not root and char not in next_fail:
                next_fail = next_fail[_AHO_FAIL]  # type: ignore[index]
            child[_AHO_FAIL] = next_fail.get(char, root)  # type: ignore[index,union-attr]
            queue.append(child)  # type: ignore[arg-type]

    return root


def _aho_matches(text: str, automaton: dict[str, object]) -> list[str]:
    node = automaton
    matches: dict[str, None] = {}

    for char in text:
        while node is not automaton and char not in node:
            node = node[_AHO_FAIL]  # type: ignore[index,assignment]
        node = node.get(char, automaton)  # type: ignore[assignment]
        for pattern in node.get(_AHO_OUTPUT, []):  # type: ignore[union-attr]
            matches[pattern] = None

    return list(matches)


_LEXICON_PATTERN_TO_KEYWORDS: dict[str, tuple[str, ...]] = {}
for entity, lexemes in ENTITY_LEXICON.items():
    terms = {entity, *lexemes}
    for term in tuple(terms):
        terms.update(_SYNONYMS.get(term, ()))
    for term in terms:
        _LEXICON_PATTERN_TO_KEYWORDS[term] = tuple(dict.fromkeys((
            *_LEXICON_PATTERN_TO_KEYWORDS.get(term, ()),
            entity,
            term,
            *_SYNONYMS.get(term, ()),
        )))

_KEYWORD_AUTOMATON = _build_aho_automaton(set(_LEXICON_PATTERN_TO_KEYWORDS))


def _extract_aho_keywords(query: str) -> list[str]:
    keywords: dict[str, None] = {}
    for match in _aho_matches(query, _KEYWORD_AUTOMATON):
        for keyword in _LEXICON_PATTERN_TO_KEYWORDS[match]:
            keywords[keyword] = None
    return list(keywords)


def _apply_synonym_filter(query: str) -> str:
    synonyms: dict[str, None] = {}
    for match in _aho_matches(query, _KEYWORD_AUTOMATON):
        for synonym in _SYNONYMS.get(match, ()):
            if synonym not in query:
                synonyms[synonym] = None

    if not synonyms:
        return query
    return f"{query} {' '.join(synonyms)}"


class QueryPreprocessor:
    def run(self, state: PipelineState) -> None:

        normalized_query = _apply_synonym_filter(normalize_query(state.original_query))

        # TODO: Kiwi, Mecab 한국어 형태소 분석기 적용
        keywords = list(dict.fromkeys(
            [*_extract_aho_keywords(normalized_query), *extract_keywords(normalized_query)]
        ))[:12]
        
        entities = extract_entities(
            query=normalized_query,
            keywords=keywords,
        )

        # TODO:Semantic enrichment 추가 구현
        # 검색 친화 형태
        # - 명사 중심, 불필요 조사 제거
        # 동의어/확장 추가
        # - ex) "장학금 신청 방법"
        # -> "장학금 신청 방법 절차", "장학금 신청 방법 필요 서류", "장학금 신청 방법 마감일"
        rewritten_queries = rewrite_queries(
            query=normalized_query,
            keywords=keywords,
            entities=entities,
        )

        state.normalized_query = normalized_query
        state.keywords = keywords
        state.entities = entities
        state.filters = build_filters(entities)
        state.category = primary_category(entities)
        state.rewritten_queries = rewritten_queries
        state.rewritten_query = rewritten_queries[-1] if rewritten_queries else normalized_query
        state.metadata["query_understanding"] = {
            "normalized_query": normalized_query,
            "keywords": keywords,
            "entities": entities,
            "filters": state.filters,
            "primary_category": state.category,
            "rewritten_queries": rewritten_queries,
        }
