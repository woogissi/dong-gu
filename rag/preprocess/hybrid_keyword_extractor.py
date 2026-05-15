from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from rag.preprocess.tokenizer import (
    CANDIDATE_STOPWORDS,
    normalize_candidate,
    ordered_unique,
)

try:  # pragma: no cover - exercised through fallback tests when unavailable
    from kiwipiepy import Kiwi as _KiwiClass
except ImportError:  # pragma: no cover
    _KiwiClass = None


HYBRID_MODE_ENV = "RAG_KEYWORD_HYBRID_MODE"
MIN_AHO_MATCHES_ENV = "RAG_KEYWORD_MIN_AHO_MATCHES"
KIWI_CACHE_SIZE_ENV = "RAG_KIWI_CACHE_SIZE"

_DEFAULT_HYBRID_MODE = "auto"
_DEFAULT_MIN_AHO_MATCHES = 1
_DEFAULT_CACHE_SIZE = 512
_MAX_KEYWORDS = 12
_KIWI_CLASS = _KiwiClass
_KIWI_CALL_COUNT = 0
_KIWI_ANALYSIS_CACHE: OrderedDict[str, "KiwiAnalysisResult"] = OrderedDict()
_STATE_LOCK = threading.RLock()
_NOUN_TAG_PREFIXES = ("NNG", "NNP", "SL", "SN")
_TOKEN_TERM_TAG_PREFIXES = (*_NOUN_TAG_PREFIXES, "VV", "VA")


@dataclass(frozen=True)
class HybridKeywordConfig:
    mode: str = _DEFAULT_HYBRID_MODE
    min_aho_matches: int = _DEFAULT_MIN_AHO_MATCHES
    max_keywords: int = _MAX_KEYWORDS

    @classmethod
    def from_env(cls) -> "HybridKeywordConfig":
        return cls(
            mode=os.getenv(HYBRID_MODE_ENV, _DEFAULT_HYBRID_MODE).strip().lower(),
            min_aho_matches=_int_env(MIN_AHO_MATCHES_ENV, _DEFAULT_MIN_AHO_MATCHES),
        )


@dataclass(frozen=True)
class HybridExtractionStats:
    kiwi_enabled: bool
    kiwi_called: bool
    kiwi_cache_hit: bool
    hybrid_mode: str


@dataclass(frozen=True)
class HybridExtractionResult:
    keywords: list[str]
    stats: HybridExtractionStats


@dataclass(frozen=True)
class KiwiAnalysisResult:
    keyword_candidates: list[str]
    morph_terms: list[str]
    noun_terms: list[str]
    cache_hit: bool = False


def extract_hybrid_keywords(
    text: str,
    *,
    aho_keywords: Iterable[str] = (),
    lexical_keywords: Iterable[str] = (),
    morph_terms: Iterable[str] | None = None,
    config: HybridKeywordConfig | None = None,
    text_id: str | None = None,
    context: str = "query",
) -> HybridExtractionResult:
    """Merge Aho/lexical keywords with optional Kiwi noun candidates.

    Kiwi runs only in ``on`` mode, in ``auto`` mode when Aho results are below
    the configured threshold, or for indexing contexts.  Runtime chunk scans can
    pass ``context="runtime_chunk"`` to keep Kiwi off unless explicitly enabled.
    """

    cfg = config or HybridKeywordConfig.from_env()
    aho = _ordered_unique(aho_keywords)
    lexical = _ordered_unique(lexical_keywords)
    kiwi_enabled = _kiwi_available() and cfg.mode != "off"
    should_call_kiwi = kiwi_enabled and _should_call_kiwi(
        mode=cfg.mode,
        aho_count=len(aho),
        min_aho_matches=cfg.min_aho_matches,
        context=context,
    )

    kiwi_candidates = list(morph_terms or [])
    cache_hit = False
    kiwi_called = morph_terms is None and should_call_kiwi
    if kiwi_called:
        analysis = extract_kiwi_analysis(text, text_id=text_id)
        kiwi_candidates = analysis.keyword_candidates
        cache_hit = analysis.cache_hit

    keywords = _rank_and_merge(
        aho_keywords=aho,
        lexical_keywords=lexical,
        kiwi_keywords=kiwi_candidates,
        limit=cfg.max_keywords,
    )
    return HybridExtractionResult(
        keywords=keywords,
        stats=HybridExtractionStats(
            kiwi_enabled=kiwi_enabled,
            kiwi_called=kiwi_called,
            kiwi_cache_hit=cache_hit,
            hybrid_mode=cfg.mode,
        ),
    )


def extract_kiwi_candidates(text: str, *, text_id: str | None = None) -> tuple[list[str], bool]:
    analysis = extract_kiwi_analysis(text, text_id=text_id)
    return analysis.keyword_candidates, analysis.cache_hit


def extract_kiwi_token_terms(text: str, *, text_id: str | None = None) -> tuple[list[str], bool]:
    analysis = extract_kiwi_analysis(text, text_id=text_id)
    return analysis.morph_terms, analysis.cache_hit


def extract_kiwi_analysis(text: str, *, text_id: str | None = None) -> KiwiAnalysisResult:
    if not text or not _kiwi_available():
        return KiwiAnalysisResult(keyword_candidates=[], morph_terms=[], noun_terms=[])

    cache_key = _cache_key(text, text_id)
    with _STATE_LOCK:
        cached = _KIWI_ANALYSIS_CACHE.get(cache_key)
        if cached is not None:
            _KIWI_ANALYSIS_CACHE.move_to_end(cache_key)
            return KiwiAnalysisResult(
                keyword_candidates=list(cached.keyword_candidates),
                morph_terms=list(cached.morph_terms),
                noun_terms=list(cached.noun_terms),
                cache_hit=True,
            )

    analysis = _analyze_with_kiwi(text)
    with _STATE_LOCK:
        cached = _KIWI_ANALYSIS_CACHE.get(cache_key)
        if cached is not None:
            _KIWI_ANALYSIS_CACHE.move_to_end(cache_key)
            return KiwiAnalysisResult(
                keyword_candidates=list(cached.keyword_candidates),
                morph_terms=list(cached.morph_terms),
                noun_terms=list(cached.noun_terms),
                cache_hit=True,
            )
        _KIWI_ANALYSIS_CACHE[cache_key] = analysis
        _trim_cache()
    return analysis


def clear_kiwi_cache() -> None:
    with _STATE_LOCK:
        _KIWI_ANALYSIS_CACHE.clear()
    _get_kiwi.cache_clear()
    _get_max_cache_size.cache_clear()
    reset_kiwi_call_count()


def get_kiwi_cache_info() -> dict[str, int]:
    with _STATE_LOCK:
        return {
            "size": len(_KIWI_ANALYSIS_CACHE),
            "analysis_size": len(_KIWI_ANALYSIS_CACHE),
            "kiwi_calls": _KIWI_CALL_COUNT,
        }


def reset_kiwi_call_count() -> None:
    global _KIWI_CALL_COUNT
    with _STATE_LOCK:
        _KIWI_CALL_COUNT = 0


def _analyze_with_kiwi(text: str) -> KiwiAnalysisResult:
    global _KIWI_CALL_COUNT
    kiwi = _get_kiwi()
    if kiwi is None:
        return KiwiAnalysisResult(keyword_candidates=[], morph_terms=[], noun_terms=[])

    with _STATE_LOCK:
        _KIWI_CALL_COUNT += 1
    noun_run: list[str] = []
    candidates: list[str] = []
    morph_terms: list[str] = []
    noun_terms: list[str] = []

    for token in kiwi.tokenize(text):
        form = normalize_candidate(getattr(token, "form", ""))
        tag = str(getattr(token, "tag", ""))
        if not form:
            _flush_noun_run(noun_run, candidates)
            continue
        if form in CANDIDATE_STOPWORDS:
            _flush_noun_run(noun_run, candidates)
            continue
        if tag.startswith(_TOKEN_TERM_TAG_PREFIXES):
            morph_terms.append(form)
        if tag.startswith(_NOUN_TAG_PREFIXES):
            noun_run.append(form)
            noun_terms.append(form)
            candidates.append(form)
            continue
        _flush_noun_run(noun_run, candidates)

    _flush_noun_run(noun_run, candidates)
    return KiwiAnalysisResult(
        keyword_candidates=ordered_unique(candidates),
        morph_terms=ordered_unique(morph_terms),
        noun_terms=ordered_unique(noun_terms),
    )


def _flush_noun_run(noun_run: list[str], candidates: list[str]) -> None:
    if len(noun_run) >= 2:
        max_window = min(4, len(noun_run))
        for size in range(max_window, 1, -1):
            for start in range(0, len(noun_run) - size + 1):
                candidates.append("".join(noun_run[start:start + size]))
    noun_run.clear()


def _rank_and_merge(
    *,
    aho_keywords: list[str],
    lexical_keywords: list[str],
    kiwi_keywords: list[str],
    limit: int,
) -> list[str]:
    scored: dict[str, tuple[int, int, int]] = {}
    insertion = 0
    for source_score, terms in ((300, aho_keywords), (200, lexical_keywords), (100, kiwi_keywords)):
        for term in terms:
            normalized = normalize_candidate(term)
            if not normalized:
                continue
            score = (source_score, len(normalized), -insertion)
            if normalized not in scored or score > scored[normalized]:
                scored[normalized] = score
            insertion += 1

    ranked = sorted(scored, key=lambda term: scored[term], reverse=True)
    return ranked[:limit]


def _should_call_kiwi(*, mode: str, aho_count: int, min_aho_matches: int, context: str) -> bool:
    if mode == "on":
        return True
    if context == "indexing":
        return True
    if context == "runtime_chunk":
        return False
    return aho_count < min_aho_matches


def _ordered_unique(values: Iterable[str]) -> list[str]:
    return ordered_unique(value for value in values if value)


def _kiwi_available() -> bool:
    return _KIWI_CLASS is not None


def is_kiwi_available() -> bool:
    return _kiwi_available()


@lru_cache(maxsize=1)
def _get_kiwi() -> Any:
    if _KIWI_CLASS is None:
        return None
    try:
        return _KIWI_CLASS()
    except Exception:  # pragma: no cover - defensive fallback for broken installs
        return None


def _cache_key(text: str, text_id: str | None) -> str:
    if text_id:
        return f"id:{text_id}"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return f"sha1:{digest}"


def _trim_cache() -> None:
    max_size = _get_max_cache_size()
    while len(_KIWI_ANALYSIS_CACHE) > max_size:
        _KIWI_ANALYSIS_CACHE.popitem(last=False)


@lru_cache(maxsize=1)
def _get_max_cache_size() -> int:
    return _int_env(KIWI_CACHE_SIZE_ENV, _DEFAULT_CACHE_SIZE)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
