"""Regex fallback lexical term extraction."""

from __future__ import annotations

from rag.preprocess.tokenizer import regex_lexical_terms


def extract_keywords(query: str) -> list[str]:
    """Return regex fallback terms only.

    Dictionary/entity matching is centralized in the Aho-Corasick path, so this
    module no longer keeps a separate domain lexicon or stopword policy.
    """
    if not query:
        return []
    return regex_lexical_terms(query)[:12]
