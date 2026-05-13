"""Shared query analysis model for preprocessing stages."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class QueryAnalysisResult:
    raw_text: str
    normalized_text: str
    lexical_text: str
    tokens: list[str]
    morph_terms: list[str]
    noun_terms: list[str]
    aho_matches: list[str]
    keywords: list[str]
    extracted_entities: dict[str, list[str]]
    intent: str | None = None
    rewrite_entities: list[str] = field(default_factory=list)
    kiwi_enabled: bool = False
    kiwi_called: bool = False
    kiwi_cache_hit: bool = False

    @property
    def entities(self) -> dict[str, list[str]]:
        return self.extracted_entities
