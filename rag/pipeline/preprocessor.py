"""질문 전처리 모듈"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from rag.pipeline.state import PipelineState
from rag.preprocess.domain_knowledge import ENTITY_LEXICON
from rag.preprocess.normalizer import normalize_query
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.hybrid_keyword_extractor import extract_hybrid_keywords
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


@dataclass(frozen=True)
class _AhoMatch:
    pattern: str
    start: int
    end: int


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
    return list(dict.fromkeys(match.pattern for match in _aho_match_spans(text, automaton)))


def _aho_match_spans(text: str, automaton: dict[str, object]) -> list[_AhoMatch]:
    node = automaton
    matches: list[_AhoMatch] = []

    for index, char in enumerate(text):
        while node is not automaton and char not in node:
            node = node[_AHO_FAIL]  # type: ignore[index,assignment]
        node = node.get(char, automaton)  # type: ignore[assignment]
        for pattern in node.get(_AHO_OUTPUT, []):  # type: ignore[union-attr]
            start = index - len(pattern) + 1
            matches.append(_AhoMatch(pattern=pattern, start=start, end=index + 1))

    return matches


def _longest_non_overlapping_matches(text: str, automaton: dict[str, object]) -> list[str]:
    candidates = sorted(
        _aho_match_spans(text, automaton),
        key=lambda match: (-(match.end - match.start), match.start, match.pattern),
    )
    occupied: list[tuple[int, int]] = []
    selected: list[_AhoMatch] = []

    for match in candidates:
        if any(match.start < end and start < match.end for start, end in occupied):
            continue
        occupied.append((match.start, match.end))
        selected.append(match)

    selected.sort(key=lambda match: match.start)
    return list(dict.fromkeys(match.pattern for match in selected))


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
    for match in _longest_non_overlapping_matches(query, _KEYWORD_AUTOMATON):
        for keyword in _LEXICON_PATTERN_TO_KEYWORDS[match]:
            keywords[keyword] = None
    return list(keywords)


def _apply_synonym_filter(query: str) -> str:
    synonyms: dict[str, None] = {}
    for match in _longest_non_overlapping_matches(query, _KEYWORD_AUTOMATON):
        for synonym in _SYNONYMS.get(match, ()):
            if synonym not in query:
                synonyms[synonym] = None

    filtered_synonyms = _drop_subsumed_terms(list(synonyms))
    if not filtered_synonyms:
        return query
    return f"{query} {' '.join(filtered_synonyms)}"


def _drop_subsumed_terms(terms: list[str]) -> list[str]:
    ordered = sorted(dict.fromkeys(terms), key=len, reverse=True)
    kept: list[str] = []
    for term in ordered:
        if any(term != other and term in other for other in kept):
            continue
        kept.append(term)
    return sorted(kept, key=terms.index)


class QueryPreprocessor:
    def run(self, state: PipelineState) -> None:

        normalized_query = normalize_query(state.original_query)
        lexical_query = _apply_synonym_filter(normalized_query)

        aho_keywords = _extract_aho_keywords(lexical_query)
        hybrid_result = extract_hybrid_keywords(
            lexical_query,
            aho_keywords=aho_keywords,
            lexical_keywords=extract_keywords(lexical_query),
            context="query",
        )
        keywords = hybrid_result.keywords
        
        entities = extract_entities(
            query=lexical_query,
            keywords=keywords,
        )

        # TODO:Semantic enrichment 추가 구현
        # 검색 친화 형태
        # - 명사 중심, 불필요 조사 제거
        # 동의어/확장 추가
        # - ex) "장학금 신청 방법"
        # -> "장학금 신청 방법 절차", "장학금 신청 방법 필요 서류", "장학금 신청 방법 마감일"
        
        # 조사 제거 로직을 추가시 앞서 작성한 hybrid_keyword_extractor의 
        # kiwi를 활용해 명사만 추출한 버전을 state.rewritten_query 후보군
        rewritten_queries = rewrite_queries(
            query=normalized_query,
            keywords=keywords,
            entities=entities,
        )
        if lexical_query != normalized_query:
            rewritten_queries = list(dict.fromkeys([normalized_query, lexical_query, *rewritten_queries]))

        embedding_query = normalized_query
        state.normalized_query = normalized_query
        state.keywords = keywords
        state.entities = entities
        state.filters = build_filters(entities)
        state.category = primary_category(entities)
        state.rewritten_queries = rewritten_queries
        state.rewritten_query = rewritten_queries[-1] if rewritten_queries else normalized_query
        state.metadata["query_understanding"] = {
            "normalized_query": normalized_query,
            "lexical_query": lexical_query,
            "embedding_query": embedding_query,
            "keywords": keywords,
            "entities": entities,
            "filters": state.filters,
            "primary_category": state.category,
            "rewritten_queries": rewritten_queries,
            "hybrid_keyword_extraction": {
                "mode": hybrid_result.stats.hybrid_mode,
                "kiwi_enabled": hybrid_result.stats.kiwi_enabled,
                "kiwi_called": hybrid_result.stats.kiwi_called,
                "kiwi_cache_hit": hybrid_result.stats.kiwi_cache_hit,
                "aho_keyword_count": len(aho_keywords),
            },
        }
