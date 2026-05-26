"""Dictionary-backed lexicon matching for query preprocessing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from rag.preprocess.domain_knowledge import ENTITY_LEXICON, ENTITY_SYNONYMS
from rag.preprocess.tokenizer import drop_subsumed_terms


_AHO_OUTPUT = "_out"
_AHO_FAIL = "_fail"
_SYNONYMS = ENTITY_SYNONYMS
_BROAD_SYNONYM_EXPANSIONS = {"국가장학", "교내장학", "근로장학"}


@dataclass(frozen=True)
class AhoMatch:
    pattern: str
    start: int
    end: int


def build_aho_automaton(patterns: set[str]) -> dict[str, object]:
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


def aho_matches(text: str, automaton: dict[str, object]) -> list[str]:
    return list(dict.fromkeys(match.pattern for match in aho_match_spans(text, automaton)))


def aho_match_spans(text: str, automaton: dict[str, object]) -> list[AhoMatch]:
    node = automaton
    matches: list[AhoMatch] = []

    for index, char in enumerate(text):
        while node is not automaton and char not in node:
            node = node[_AHO_FAIL]  # type: ignore[index,assignment]
        node = node.get(char, automaton)  # type: ignore[assignment]
        for pattern in node.get(_AHO_OUTPUT, []):  # type: ignore[union-attr]
            start = index - len(pattern) + 1
            matches.append(AhoMatch(pattern=pattern, start=start, end=index + 1))

    return matches


def longest_non_overlapping_matches(text: str, automaton: dict[str, object]) -> list[str]:
    candidates = sorted(
        aho_match_spans(text, automaton),
        key=lambda match: (-(match.end - match.start), match.start, match.pattern),
    )
    occupied: list[tuple[int, int]] = []
    selected: list[AhoMatch] = []

    for match in candidates:
        if any(match.start < end and start < match.end for start, end in occupied):
            continue
        occupied.append((match.start, match.end))
        selected.append(match)

    selected.sort(key=lambda match: match.start)
    return list(dict.fromkeys(match.pattern for match in selected))


def extract_aho_keywords(query: str) -> list[str]:
    keywords: dict[str, None] = {}
    for match in longest_non_overlapping_matches(query, _KEYWORD_AUTOMATON):
        for keyword in _LEXICON_PATTERN_TO_KEYWORDS[match]:
            keywords[keyword] = None
    return list(keywords)


def apply_synonym_filter(query: str) -> str:
    synonyms: dict[str, None] = {}
    for match in longest_non_overlapping_matches(query, _KEYWORD_AUTOMATON):
        for synonym in _SYNONYMS.get(match, ()):
            if synonym in _BROAD_SYNONYM_EXPANSIONS:
                continue
            if synonym not in query:
                synonyms[synonym] = None

    filtered_synonyms = drop_subsumed_terms(synonyms)
    if not filtered_synonyms:
        return query
    return f"{query} {' '.join(filtered_synonyms)}"


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

_KEYWORD_AUTOMATON = build_aho_automaton(set(_LEXICON_PATTERN_TO_KEYWORDS))
