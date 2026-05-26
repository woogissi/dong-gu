"""질문 전처리 모듈"""

from __future__ import annotations

from dataclasses import replace
import re

from rag.pipeline.state import PipelineState
from rag.preprocess.normalizer import normalize_query
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.hybrid_keyword_extractor import (
    HybridKeywordConfig,
    extract_hybrid_keywords,
    extract_kiwi_analysis,
    is_kiwi_available,
)
from rag.preprocess.entity_extractor import build_filters, extract_entities, primary_category
from rag.preprocess.lexicon_matcher import (
    apply_synonym_filter,
    extract_aho_keywords,
)
from rag.preprocess.query_analysis import QueryAnalysisResult
from rag.preprocess.query_features import extract_query_features, sanitize_filters
from rag.preprocess.query_rewriter import (
    detect_intent,
    detect_rewrite_entities,
    rewrite_queries_from_bundle,
    rewrite_query,
)
from rag.preprocess.tokenizer import regex_tokens


_PROTECTED_QUERY_TOKEN_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9]+(?:[-ㆍ·][가-힣A-Za-z0-9]+)*"
)
_PROTECTED_SUFFIXES = (
    "관",
    "호관",
    "학과",
    "학부",
    "대학원",
    "장학금",
    "버스",
    "식당",
    "라운지",
    "센터",
    "팀",
    "실",
)
_PROTECTED_KEYWORDS = {
    "정보관",
    "정보공학관",
    "지천관",
    "콜라보라운지",
    "셔틀버스",
    "통학버스",
    "학생식당",
    "학식",
    "기말시험",
    "보강일정",
}
def _protected_query_terms(query: str, keywords: list[str]) -> list[str]:
    protected: dict[str, None] = {}
    for value in [*keywords, *(_PROTECTED_QUERY_TOKEN_PATTERN.findall(query or ""))]:
        term = value.strip()
        if not term:
            continue
        if term in _PROTECTED_KEYWORDS:
            protected[term] = None
            continue
        if re.search(r"\d", term):
            protected[term] = None
            continue
        if any(term.endswith(suffix) and len(term) >= max(3, len(suffix) + 1) for suffix in _PROTECTED_SUFFIXES):
            protected[term] = None
    return list(protected)


def _missing_protected_terms(text: str, protected_terms: list[str]) -> list[str]:
    normalized = text or ""
    return [term for term in protected_terms if term and term not in normalized]


def _append_missing_terms(text: str, missing_terms: list[str]) -> str:
    if not missing_terms:
        return text
    return " ".join([text, *missing_terms]).strip()


class QueryPreprocessor:
    def analyze_query_once(self, raw_query: str) -> QueryAnalysisResult:
        normalized_query = normalize_query(raw_query)
        lexical_query = apply_synonym_filter(normalized_query)

        aho_matches = extract_aho_keywords(lexical_query)
        lexical_terms = extract_keywords(lexical_query)
        cfg = HybridKeywordConfig.from_env()
        should_analyze_kiwi = cfg.mode != "off" and is_kiwi_available()
        kiwi_analysis = extract_kiwi_analysis(lexical_query) if should_analyze_kiwi else None
        morph_terms = kiwi_analysis.keyword_candidates if kiwi_analysis else []
        noun_terms = kiwi_analysis.noun_terms if kiwi_analysis else []
        hybrid_result = extract_hybrid_keywords(
            lexical_query,
            aho_keywords=aho_matches,
            lexical_keywords=lexical_terms,
            morph_terms=morph_terms,
            config=cfg,
            context="query",
        )
        keywords = hybrid_result.keywords
        extracted_entities = extract_entities(
            query=lexical_query,
            keywords=keywords,
        )
        partial_analysis = QueryAnalysisResult(
            raw_text=raw_query,
            normalized_text=normalized_query,
            lexical_text=lexical_query,
            tokens=regex_tokens(normalized_query),
            morph_terms=kiwi_analysis.morph_terms if kiwi_analysis else [],
            noun_terms=noun_terms,
            aho_matches=aho_matches,
            keywords=keywords,
            extracted_entities=extracted_entities,
            kiwi_enabled=should_analyze_kiwi,
            kiwi_called=kiwi_analysis is not None and not kiwi_analysis.cache_hit,
            kiwi_cache_hit=bool(kiwi_analysis and kiwi_analysis.cache_hit),
        )
        rewrite_entities = detect_rewrite_entities(
            normalized_query,
            keywords,
            analysis=partial_analysis,
        )
        intent = detect_intent(analysis=partial_analysis)
        return QueryAnalysisResult(
            raw_text=partial_analysis.raw_text,
            normalized_text=partial_analysis.normalized_text,
            lexical_text=partial_analysis.lexical_text,
            tokens=partial_analysis.tokens,
            morph_terms=partial_analysis.morph_terms,
            noun_terms=partial_analysis.noun_terms,
            aho_matches=partial_analysis.aho_matches,
            keywords=partial_analysis.keywords,
            extracted_entities=partial_analysis.extracted_entities,
            intent=intent,
            rewrite_entities=rewrite_entities,
            kiwi_enabled=partial_analysis.kiwi_enabled,
            kiwi_called=partial_analysis.kiwi_called,
            kiwi_cache_hit=partial_analysis.kiwi_cache_hit,
        )

    def run(self, state: PipelineState) -> None:

        analysis = self.analyze_query_once(state.original_query)
        normalized_query = analysis.normalized_text
        lexical_query = analysis.lexical_text
        query_features = extract_query_features(normalized_query, analysis.keywords)
        keywords = list(dict.fromkeys([*analysis.keywords, *query_features.strong_terms]))
        extracted_entities = analysis.extracted_entities

        # TODO:Semantic enrichment 추가 구현
        # 검색 친화 형태
        # - 명사 중심, 불필요 조사 제거
        # 동의어/확장 추가
        # - ex) "장학금 신청 방법"
        # -> "장학금 신청 방법 절차", "장학금 신청 방법 필요 서류", "장학금 신청 방법 마감일"
        
        # 조사 제거 로직을 추가시 앞서 작성한 hybrid_keyword_extractor의 
        # kiwi를 활용해 명사만 추출한 버전을 state.rewritten_query 후보군
        query_bundle = rewrite_query(
            query=normalized_query,
            keywords=keywords,
            entities=extracted_entities,
            analysis=analysis,
        )
        rewritten_queries = rewrite_queries_from_bundle(
            query_bundle,
            query=normalized_query,
            analysis=analysis,
        )
        protected_terms = list(
            dict.fromkeys([*_protected_query_terms(normalized_query, keywords), *query_features.protected_terms])
        )
        missing_in_rewrite = _missing_protected_terms(query_bundle.keyword_query or "", protected_terms)
        rewrite_quality = {
            "protected_terms": protected_terms,
            "missing_protected_terms": missing_in_rewrite,
            "original_len": len(normalized_query),
            "rewrite_len": len(query_bundle.keyword_query or ""),
            "rewrite_preserved": not missing_in_rewrite,
        }
        if missing_in_rewrite:
            protected_rewrite = _append_missing_terms(query_bundle.keyword_query or normalized_query, missing_in_rewrite)
            rewritten_queries = [normalized_query, protected_rewrite, *rewritten_queries]
            query_bundle = replace(query_bundle, keyword_query=normalized_query)
        if lexical_query != normalized_query:
            rewritten_queries = list(dict.fromkeys([query_bundle.keyword_query, lexical_query, *rewritten_queries]))
        rewritten_queries = list(dict.fromkeys([*rewritten_queries, normalized_query, state.original_query]))

        embedding_query = normalized_query
        state.normalized_query = normalized_query
        state.keywords = keywords
        state.entities = extracted_entities
        state.query_bundle = query_bundle.to_dict()
        state.filters = build_filters(extracted_entities)
        bundle_filters = query_bundle.filters
        for field, values in bundle_filters.items():
            if field not in state.filters and isinstance(values, list):
                state.filters[field] = values
        state.filters, dropped_filters = sanitize_filters(state.filters)
        state.category = query_features.category or primary_category(extracted_entities) or (
            query_bundle.filters.get("category", [None])[0]
            if isinstance(query_bundle.filters.get("category"), list)
            else None
        )
        state.rewritten_queries = rewritten_queries
        state.rewritten_query = query_bundle.keyword_query or normalized_query
        state.metadata["query_understanding"] = {
            "normalized_query": normalized_query,
            "original_query": state.original_query,
            "lexical_query": lexical_query,
            "expanded_query": " ".join(dict.fromkeys([normalized_query, *keywords])),
            "embedding_query": embedding_query,
            "query_bundle": state.query_bundle,
            "keywords": keywords,
            "extracted_entities": extracted_entities,
            "rewrite_entities": query_bundle.entities,
            "rewrite_quality": rewrite_quality,
            "query_features": query_features.to_log_dict(),
            "entities": extracted_entities,
            "filters": state.filters,
            "dropped_filters": dropped_filters,
            "primary_category": state.category,
            "detected_domain": query_features.domain,
            "detected_category": query_features.category or state.category,
            "rule_hit_names": query_features.rule_hit_names,
            "applied_boosts": query_features.source_boosts,
            "rewritten_queries": rewritten_queries,
            "hybrid_keyword_extraction": {
                "mode": HybridKeywordConfig.from_env().mode,
                "kiwi_enabled": analysis.kiwi_enabled,
                "kiwi_called": analysis.kiwi_called,
                "kiwi_cache_hit": analysis.kiwi_cache_hit,
                "aho_keyword_count": len(analysis.aho_matches),
            },
        }
