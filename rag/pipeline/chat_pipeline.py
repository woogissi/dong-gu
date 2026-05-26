"""RAG pipeline orchestration."""

import html
import json
import os
import re
import time
from pathlib import Path

from rag.pipeline.state import PipelineState
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.preprocess.primary_intent import PrimaryIntentClassifier
from rag.schemas.query import Query
from rag.schemas.answer import Answer

from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request
from rag.retrieval.source_policy import forbidden_source_types_for_family
from rag.retrieval.quality import retrieval_quality_result, set_retrieval_quality_status
from rag.selection.topk_selector import select_topk_with_diagnostics
from rag.selection.context_builder import build_context
from rag.selection.reranker import rerank_documents

from rag.prompt.prompt_builder import build_prompt
from rag.llm.answer_generator import generate_answer
from rag.generation.answer_postprocessor import (
    repair_negative_answer_with_context,
    strip_markdown_formatting,
)

from rag.fallback.fallback_handler import handle_fallback
from rag.fallback.policy import NO_RETRIEVAL_RESULTS_MESSAGE, has_not_found_answer

from rag.embedding.koe5_embedder import KoE5Embedder

from threading import Lock


_RETRIEVAL_MODE_ENV_VAR = "RETRIEVAL_MODE"
_MIN_TOP1_SCORE_ENV_VAR = "RETRIEVAL_MIN_TOP1_SCORE"
_MIN_AVG_TOPK_SCORE_ENV_VAR = "RETRIEVAL_MIN_AVG_TOPK_SCORE"
_MIN_CONTEXT_CHARS_ENV_VAR = "RETRIEVAL_MIN_CONTEXT_CHARS"
_MAX_DUPLICATE_DOC_RATIO_ENV_VAR = "RETRIEVAL_MAX_DUPLICATE_DOC_RATIO"
_MAX_TOP_NOISE_SCORE_ENV_VAR = "RETRIEVAL_MAX_TOP_NOISE_SCORE"
_MIN_TOP_STRONG_MATCH_ENV_VAR = "RETRIEVAL_MIN_TOP_STRONG_MATCH"
_LOG_BRANCH_CANDIDATES_ENV_VAR = "RAG_LOG_BRANCH_CANDIDATES"
_MAX_FALLBACK_ATTEMPTS_ENV_VAR = "RAG_MAX_FALLBACK_ATTEMPTS"
_FALLBACK_ORDER_ENV_VAR = "RAG_FALLBACK_ORDER"
_VECTOR_ONLY_FAMILIES_ENV_VAR = "RAG_VECTOR_ONLY_FAMILIES"
_DISABLE_FALLBACK_FOR_MODES_ENV_VAR = "RAG_DISABLE_FALLBACK_FOR_MODES"
_STARTUP_WARMUP_QUERY = "동의대학교 정보 안내"


class NoRetrievalResultsError(Exception):
    pass


class ChatPipeline:
    def __init__(self) -> None:
        self.preprocessor = QueryPreprocessor()
        self.intent_classifier = PrimaryIntentClassifier()
        self.embedder: KoE5Embedder | None = None
        self.embedder_startup_error: str | None = None
        self.embedder_lock = Lock()
        self.last_state: PipelineState | None = None
        # retriever: Retriever = None,
        # generator: AnswerGenerator = None 확장

    def run(self, query: Query) -> Answer:
        run_started = time.perf_counter()
        state = PipelineState.from_query(query.text)
        self.last_state = state

        try:
            self._timed_stage(state, "classify_primary_intent", lambda: self._classify_primary_intent(state))
            if state.primary_intent != "INFO":
                state.success = True
                state.error = ""
                return self._build_direct_answer(state)

            self._timed_stage(state, "preprocess", lambda: self.preprocessor.run(state))
            self._timed_stage(state, "embed_query", lambda: self._embed_query(state))
            self._timed_stage(state, "retrieve", lambda: self._retrieve(state))
            self._timed_stage(state, "select_and_build_context", lambda: self._select_and_build_context(state))
            self._timed_stage(state, "generate_answer", lambda: self._generate(state))
            self._timed_stage(state, "postprocess", lambda: self._postprocess(state))
            state.success = True
            state.error = ""
            return self._build_success_answer(state)
        except Exception as e:
            state.success = False
            state.error = str(e)
            state.fallback_used = True
            return self._build_fallback_answer(state)
        finally:
            state.metadata["total_run_ms"] = self._elapsed_ms(run_started)
            self._log_timing_summary(state)

    def _timed_stage(self, state: PipelineState, name: str, callback):
        started = time.perf_counter()
        try:
            return callback()
        finally:
            state.metadata.setdefault("timings_ms", []).append(
                {"stage": name, "elapsed_ms": self._elapsed_ms(started)}
            )

    def _elapsed_ms(self, started: float) -> int:
        return int(round((time.perf_counter() - started) * 1000))

    def _record_retrieval_timing(
        self,
        state: PipelineState | None,
        *,
        label: str,
        mode: str,
        count: int,
        started: float,
    ) -> None:
        if state is None:
            return
        state.metadata.setdefault("retrieval_timings_ms", []).append(
            {
                "label": label,
                "mode": mode,
                "count": count,
                "elapsed_ms": self._elapsed_ms(started),
            }
        )

    def _log_timing_summary(self, state: PipelineState) -> None:
        print(
            "[rag timing] "
            f"query={state.original_query!r} "
            f"success={state.success} "
            f"fallback_used={state.fallback_used} "
            f"total_ms={state.metadata.get('total_run_ms')} "
            f"stages={state.metadata.get('timings_ms', [])} "
            f"retrieval_calls={state.metadata.get('retrieval_timings_ms', [])}",
            flush=True,
        )

    def _classify_primary_intent(self, state: PipelineState) -> None:
        state.primary_intent = self.intent_classifier.classify(state.original_query)
        state.metadata["primary_intent"] = state.primary_intent


    def _get_embedder(self) -> KoE5Embedder:
        with self.embedder_lock:
            if self.embedder is None:
                print("[ChatPipeline] Loading embedder...")
                self.embedder = KoE5Embedder()
                print("[ChatPipeline] Embedder loaded successfully.")
            else:
                print("[ChatPipeline] Embedder already initialized.")
        return self.embedder

    def initialize(self) -> None:
        """서버 시작 시 KoE5 임베딩 모델을 동기 로드하고 warm-up 합니다."""
        try:
            print("[ChatPipeline] Starting embedder initialization at startup...")
            embedder = self._get_embedder()
            warmup_vector = embedder.embed_query(_STARTUP_WARMUP_QUERY)
            self.embedder_startup_error = None
            print(
                "[ChatPipeline] Embedder startup warm-up completed. "
                f"vector_size={len(warmup_vector or [])}"
            )
        except Exception as exc:
            self.embedder_startup_error = str(exc)
            print(f"[ChatPipeline] Embedder startup warm-up failed: {exc}")
            raise


    def _embed_query(self, state: PipelineState) -> None:
        # 쿼리 텍스트를 임베딩하여 벡터 생성
        query_understanding = state.metadata.get("query_understanding", {})
        query_text = (
            query_understanding.get("embedding_query")
            or state.normalized_query
            or state.original_query
        )
        if self.embedder is None:
            message = (
                "KoE5 embedder is not initialized. "
                "Startup warm-up must complete before handling INFO requests."
            )
            if self.embedder_startup_error:
                message += f" startup_error={self.embedder_startup_error}"
            raise RuntimeError(message)
        embedder = self.embedder
        state.query_vector = embedder.embed_query(query_text)

    def _retrieve(self, state: PipelineState) -> None:
        request = build_retrieval_request(state)
        effective_strategy = self._effective_retrieval_strategy(request)
        if effective_strategy != request.strategy:
            request = request.model_copy(update={"strategy": effective_strategy})
        state.retrieval_strategy = effective_strategy
        state.retrieval_top_k = request.top_k
        retrieval_request_log = request.model_dump(exclude={"query_vector"})
        retrieval_request_log["query_vector_size"] = len(request.query_vector or [])
        retrieval_request_log["effective_strategy"] = effective_strategy
        state.metadata["retrieval_request"] = retrieval_request_log
        state.metadata["retrieval_strategy_log"] = {**request.log_fields, "effective_strategy": effective_strategy}
        branch_log = self._collect_branch_candidates(request, state)
        if branch_log:
            state.metadata["retrieval_branch_candidates"] = branch_log
        retrieve_started = time.perf_counter()
        state.retrieved_docs = retrieve_documents(request=request)
        self._record_retrieval_timing(
            state,
            label="main",
            mode=effective_strategy,
            count=len(state.retrieved_docs or []),
            started=retrieve_started,
        )
        quality = self._evaluate_retrieval_quality(
            state.retrieved_docs,
            request.top_k,
            query=request.query,
            keywords=request.keywords,
        )
        state.metadata["retrieval_quality"] = quality
        allow_filter_relaxation = bool(request.filters) and quality.get("reason") in {
            "empty_result",
            "low_top1_score",
            "low_avg_score",
            "short_context",
        }
        if not quality["ok"] and (allow_filter_relaxation or not self._fallback_disabled_for_mode(effective_strategy)):
            fallback_docs, fallback_log = self._fallback_retrieve(request, quality["reason"], state)
            state.metadata["retrieval_fallback"] = fallback_log
            if fallback_docs:
                state.fallback_used = True
                state.retrieved_docs = fallback_docs
        if not state.retrieved_docs:
            state.fallback_used = True
            state.metadata["no_retrieval_results"] = {
                "query": request.query,
                "keywords": request.keywords,
                "filters": request.filters,
                "fallback_triggers": [*request.fallback_triggers, "no_retrieval_results"],
            }
            raise NoRetrievalResultsError(NO_RETRIEVAL_RESULTS_MESSAGE)

    def _effective_retrieval_strategy(self, request) -> str:
        configured_mode = os.getenv(_RETRIEVAL_MODE_ENV_VAR, "").strip().lower()
        if configured_mode in {"lexical", "vector", "hybrid"}:
            return configured_mode
        query_family = ""
        if isinstance(request.log_fields, dict):
            query_family = str(request.log_fields.get("query_family") or "")
        vector_only_families = set(self._csv_env(
            _VECTOR_ONLY_FAMILIES_ENV_VAR,
            default=[
                "department_curriculum",
                "building_location",
                "welfare_facility",
                "campus_address",
                "person_title",
                "course_registration",
                "academic_schedule",
                "seasonal_course_registration",
                "specific_scholarship",
                "graduation",
                "certificate",
            ],
        ))
        if query_family in vector_only_families:
            return "vector"
        if request.strategy == "dense":
            return "vector"
        return "hybrid" if request.strategy == "lexical" else request.strategy

    def _fallback_disabled_for_mode(self, mode: str) -> bool:
        return mode in self._csv_env(_DISABLE_FALLBACK_FOR_MODES_ENV_VAR, default=["vector"])

    def _csv_env(self, name: str, *, default: list[str]) -> list[str]:
        raw_value = os.getenv(name, "")
        if not raw_value.strip():
            return default
        return [value.strip() for value in raw_value.split(",") if value.strip()]

    def _evaluate_retrieval_quality(
        self,
        docs: list,
        top_k: int,
        *,
        query: str = "",
        keywords: list[str] | None = None,
    ) -> dict:
        if not docs:
            return self._retrieval_quality_result("empty_result")
        top_docs = docs[: max(top_k or 1, 1)]
        required_entity = self._extract_faculty_entity(query, keywords or [])
        entity_match_count = sum(1 for doc in top_docs[:3] if self._doc_contains_entity(doc, required_entity))
        top1_entity_match = self._doc_contains_entity(top_docs[0], required_entity) if required_entity else False
        scores = [float(doc.score or 0.0) for doc in top_docs]
        top1_score = scores[0] if scores else 0.0
        avg_topk_score = sum(scores) / len(scores) if scores else 0.0
        context_chars = sum(len(doc.content or "") for doc in top_docs)
        duplicate_ratio = 1.0 - (len({doc.doc_id for doc in top_docs}) / len(top_docs))
        top_signals = top_docs[0].metadata.get("rerank_signals") if top_docs else {}
        if not isinstance(top_signals, dict):
            top_signals = {}
        top_noise = self._metadata_float(top_signals, "noise_score")
        top_strong_match = self._metadata_float(top_signals, "strong_term_match")
        top_doc_noise = self._doc_noise_score(top_docs[0]) if top_docs else 0.0
        exact_or_title_match_count = sum(1 for doc in top_docs[:5] if self._has_retrieval_evidence(doc))

        if top1_score < self._float_env(_MIN_TOP1_SCORE_ENV_VAR, 0.05):
            reason = "low_top1_score"
        elif avg_topk_score < self._float_env(_MIN_AVG_TOPK_SCORE_ENV_VAR, 0.03):
            reason = "low_avg_score"
        elif context_chars < self._int_env(_MIN_CONTEXT_CHARS_ENV_VAR, 120):
            reason = "short_context"
        elif duplicate_ratio > self._float_env(_MAX_DUPLICATE_DOC_RATIO_ENV_VAR, 0.8):
            reason = "excessive_duplicate_doc_ids"
        elif top_doc_noise >= self._float_env(_MAX_TOP_NOISE_SCORE_ENV_VAR, 1.2):
            reason = "top_candidate_noise"
        elif required_entity and entity_match_count == 0:
            reason = "no_required_entity_match"
        elif exact_or_title_match_count == 0 and top_strong_match < self._float_env(_MIN_TOP_STRONG_MATCH_ENV_VAR, 0.05):
            reason = "no_exact_or_strong_keyword_match"
        else:
            reason = ""

        return self._retrieval_quality_result(
            reason,
            top1_score=top1_score,
            avg_topk_score=avg_topk_score,
            context_chars=context_chars,
            duplicate_doc_ratio=duplicate_ratio,
            top_noise_score=max(top_noise, top_doc_noise),
            top_strong_term_match=top_strong_match,
            exact_or_title_match_count=exact_or_title_match_count,
            required_entity=required_entity,
            required_entity_match_count=entity_match_count,
            top1_required_entity_match=top1_entity_match,
        )

    def _retrieval_quality_result(self, diagnostic_reason: str, **fields) -> dict:
        return retrieval_quality_result(diagnostic_reason, **fields)

    def _blocking_retrieval_quality_reasons(self) -> set[str]:
        from rag.retrieval.quality import BLOCKING_RETRIEVAL_QUALITY_REASONS

        return set(BLOCKING_RETRIEVAL_QUALITY_REASONS)

    def _set_retrieval_quality_status(self, retrieval_quality: dict, diagnostic_reason: str) -> None:
        set_retrieval_quality_status(retrieval_quality, diagnostic_reason)

    def _fallback_retrieve(self, request, reason: str, state: PipelineState | None = None) -> tuple[list, dict]:
        original_query = ""
        variants = list(request.query_variants or [])
        if variants:
            original_query = variants[-1]
        attempt_map = {
            "vector_only_retry": ("vector_only_retry", request, "vector"),
            "original_query_no_rewrite": (
                "original_query_no_rewrite",
                request.model_copy(
                    update={
                        "query": original_query or request.query,
                        "query_variants": [original_query or request.query],
                        "filters": {},
                        "category": None,
                    }
                ),
                "hybrid",
            ),
            "relaxed_filters": (
                "relaxed_filters",
                request.model_copy(update={"filters": {}, "category": None}),
                "hybrid",
            ),
            "increase_top_k": (
                "increase_top_k",
                request.model_copy(update={"top_k": max((request.top_k or 10) * 2, 20)}),
                "hybrid",
            ),
            "lexical_only_retry": ("lexical_only_retry", request, "lexical"),
        }
        fallback_order = (
            self._faculty_fallback_order()
            if self._extract_faculty_entity(request.query, request.keywords)
            else self._fallback_order()
        )
        if request.filters and reason in {"empty_result", "low_top1_score", "low_avg_score", "short_context"}:
            fallback_order = ["relaxed_filters", *[name for name in fallback_order if name != "relaxed_filters"]]
        attempts = [
            attempt_map[name]
            for name in fallback_order
            if name in attempt_map
        ][: self._max_fallback_attempts()]
        tried = []
        for name, fallback_request, mode in attempts:
            docs = self._retrieve_with_mode(
                fallback_request,
                mode,
                label=f"fallback_{name}",
                state=state,
            )
            quality = self._evaluate_retrieval_quality(
                docs,
                fallback_request.top_k,
                query=fallback_request.query,
                keywords=fallback_request.keywords,
            )
            tried.append({"strategy": name, "mode": mode, "count": len(docs), "quality": quality})
            if docs and quality["ok"]:
                return docs, {"used": True, "fallback_reason": reason, "selected_strategy": name, "attempts": tried}
        return [], {"used": False, "fallback_reason": reason, "attempts": tried}

    def _fallback_order(self) -> list[str]:
        configured_order = [
            value.strip()
            for value in os.getenv(_FALLBACK_ORDER_ENV_VAR, "").split(",")
            if value.strip()
        ]
        if configured_order:
            return configured_order
        return ["vector_only_retry", "original_query_no_rewrite", "relaxed_filters", "increase_top_k", "lexical_only_retry"]

    def _faculty_fallback_order(self) -> list[str]:
        return ["original_query_no_rewrite", "relaxed_filters", "lexical_only_retry", "vector_only_retry"]

    def _max_fallback_attempts(self) -> int:
        try:
            value = int(os.getenv(_MAX_FALLBACK_ATTEMPTS_ENV_VAR, "1"))
        except ValueError:
            return 1
        return max(0, value)

    def _collect_branch_candidates(self, request, state: PipelineState | None = None) -> dict:
        if os.getenv(_LOG_BRANCH_CANDIDATES_ENV_VAR, "0").strip().lower() in {"0", "false", "off"}:
            return {}
        branches = {}
        for name, mode in (("lexical", "lexical"), ("vector", "vector")):
            docs = self._retrieve_with_mode(
                request,
                mode,
                label=f"branch_{name}",
                state=state,
            )[:5]
            branches[name] = [self._candidate_log_item(rank, doc) for rank, doc in enumerate(docs, start=1)]
        return branches

    def _candidate_log_item(self, rank: int, doc) -> dict:
        metadata = doc.metadata or {}
        return {
            "rank": rank,
            "doc_id": doc.doc_id,
            "chunk_id": doc.chunk_id,
            "title": doc.title,
            "score": doc.score,
            "lexical_score": metadata.get("lexical_score"),
            "vector_score": metadata.get("vector_score"),
            "final_score": metadata.get("final_score"),
            "rerank_score": metadata.get("rerank_score"),
            "source_type": metadata.get("source_type"),
            "section_type": metadata.get("section_type"),
            "section_title": metadata.get("section_title"),
            "source_url": doc.source,
            "search_mode": metadata.get("search_mode") or metadata.get("strategy"),
            "reject_reason": metadata.get("reject_reason"),
        }

    def _candidate_trace(self, docs: list, *, limit: int = 10) -> list[dict]:
        return [
            self._candidate_log_item(rank, doc)
            for rank, doc in enumerate((docs or [])[:limit], start=1)
        ]

    def _doc_noise_score(self, doc) -> float:
        metadata = doc.metadata or {}
        source_type = str(metadata.get("source_type") or "").lower()
        source = (doc.source or "").lower()
        content_length = int(metadata.get("content_length") or len(doc.content or ""))
        score = float(metadata.get("noise_penalty") or 0.0)
        if source_type in {"static", "index", "menu"}:
            score += 0.8
        if any(marker in source for marker in ("index.do", "main.do", "/main", "sitemap")):
            score += 0.4
        if content_length and content_length < 120:
            score += 0.4
        return score

    def _has_retrieval_evidence(self, doc) -> bool:
        metadata = doc.metadata or {}
        return any(
            float(metadata.get(key) or 0.0) > 0.0
            for key in ("exact_phrase_score", "title_match_score", "section_match_score", "lexical_score")
        )

    def _required_faculty_entity(self, state: PipelineState) -> str:
        return self._extract_faculty_entity(
            state.original_query,
            [
                *(state.keywords or []),
                state.rewritten_query,
                state.normalized_query,
            ],
        )

    def _extract_faculty_entity(self, query: str, keywords: list[str] | None = None) -> str:
        candidates = [query, *(keywords or [])]
        joined = " ".join(str(value or "") for value in candidates).lower()
        if not any(term in joined for term in ("교수", "교수님", "교수소개", "교수진", "faculty")):
            return ""
        if self._is_department_faculty_list_query(query) and not self._has_explicit_professor_name(query):
            return ""
        for text in candidates:
            value = str(text or "").strip()
            if not value:
                continue
            for pattern in (
                r"([가-힣]{2,5})\s*교수(?:님)?",
                r"교수(?:님)?\s*([가-힣]{2,5})",
            ):
                match = re.search(pattern, value)
                if match and self._is_valid_faculty_entity(match.group(1)):
                    return match.group(1)
            if re.fullmatch(r"[가-힣]{2,5}", value) and self._is_valid_faculty_entity(value):
                return value
        return ""

    def _has_explicit_professor_name(self, query: str) -> bool:
        for match in re.finditer(r"([가-힣]{2,5})\s*교수(?:님)?", query or ""):
            if self._is_valid_faculty_entity(match.group(1)):
                return True
        for match in re.finditer(r"교수(?:님)?\s*([가-힣]{2,5})", query or ""):
            if self._is_valid_faculty_entity(match.group(1)):
                return True
        return False

    def _is_valid_faculty_entity(self, value: str) -> bool:
        candidate = str(value or "").strip()
        if not re.fullmatch(r"[가-힣]{2,5}", candidate):
            return False
        if candidate in {"교수", "교수님", "정보", "목록", "소개", "교수진", "전임교수"}:
            return False
        return not any(marker in candidate for marker in ("학과", "전공", "학부", "대학원", "목록", "소개"))

    def _faculty_query_type(self, state: PipelineState) -> str:
        if self._required_faculty_entity(state):
            return "single_professor"
        if self._is_department_faculty_list_query(state.original_query):
            return "department_faculty_list"
        return "none"

    def _is_department_faculty_list_query(self, query: str) -> bool:
        text = re.sub(r"\s+", "", query or "").lower()
        if not any(term in text for term in ("교수목록", "교수소개", "교수진", "전임교수")):
            return False
        return any(marker in text for marker in ("학과", "전공", "학부", "대학원"))

    def _extract_department_faculty_name(self, query: str) -> str:
        compact = re.sub(r"\s+", "", query or "")
        match = re.search(r"([A-Za-z0-9가-힣&·ㆍ\-\+]+?(?:학과|전공|학부|대학원))", compact)
        return match.group(1) if match else ""

    def _doc_contains_entity(self, doc, entity: str) -> bool:
        if not entity:
            return False
        text = "\n".join(
            [
                str(doc.title or ""),
                str(doc.metadata.get("section_title") or ""),
                str(doc.content or ""),
            ]
        )
        return entity.lower() in text.lower()

    def _is_lifelong_faculty_noise(self, doc) -> bool:
        source_type = str(doc.metadata.get("source_type") or "").lower()
        source = str(doc.source or "").lower()
        title = str(doc.title or "").lower()
        return (
            source_type == "lifelong"
            or "lifelong.deu.ac.kr" in source
            or "creditbank" in source
            or "평생교육원" in title
            or "음악학사" in title
        )

    def _retrieve_with_mode(
        self,
        request,
        mode: str,
        *,
        label: str | None = None,
        state: PipelineState | None = None,
    ) -> list:
        previous_mode = os.getenv(_RETRIEVAL_MODE_ENV_VAR)
        os.environ[_RETRIEVAL_MODE_ENV_VAR] = mode
        started = time.perf_counter()
        try:
            docs = retrieve_documents(request=request)
            self._record_retrieval_timing(
                state,
                label=label or mode,
                mode=mode,
                count=len(docs or []),
                started=started,
            )
            return docs
        finally:
            if previous_mode is None:
                os.environ.pop(_RETRIEVAL_MODE_ENV_VAR, None)
            else:
                os.environ[_RETRIEVAL_MODE_ENV_VAR] = previous_mode

    def _float_env(self, name: str, default: float) -> float:
        try:
            return float(os.getenv(name, ""))
        except ValueError:
            return default

    def _int_env(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, ""))
        except ValueError:
            return default

    def _select_and_build_context(self, state: PipelineState) -> None:
        state.reranked_docs = rerank_documents(
            state.retrieved_docs,
            query=state.rewritten_query or state.normalized_query or state.original_query,
            keywords=state.keywords,
            category=state.category,
            filters=state.filters,
        )
        query_features = self._query_features(state)
        query_family = query_features.get("family") if isinstance(query_features, dict) else None
        candidate_docs = state.reranked_docs or state.retrieved_docs
        candidate_docs = self._filter_forbidden_source_docs(query_family, candidate_docs)
        if query_family == "department_curriculum":
            candidate_docs = self._filter_department_curriculum_docs(state, candidate_docs)
        if query_family in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
            candidate_docs = self._filter_canonical_notice_docs(state, candidate_docs)
        selection_k = 3
        max_chunks_per_doc = 4 if query_family == "department_curriculum" else 1
        if query_family in {"academic_schedule", "course_registration", "seasonal_course_registration"}:
            max_chunks_per_doc = 3
        selection_result = select_topk_with_diagnostics(
            candidate_docs,
            k=selection_k,
            max_chunks_per_doc=max_chunks_per_doc,
        )
        state.selected_docs = selection_result["selected"]
        state.metadata["retrieved_candidate_trace"] = self._candidate_trace(state.retrieved_docs, limit=10)
        state.metadata["reranked_candidate_trace"] = self._candidate_trace(state.reranked_docs, limit=10)
        state.metadata["selected_candidate_trace"] = self._candidate_trace(state.selected_docs, limit=3)
        state.metadata["rejected_candidate_trace"] = selection_result.get("rejected_chunks", [])[:20]
        self._correct_department_faculty_list_selection(state, candidate_docs)
        self._correct_faculty_selection(state, candidate_docs)
        self._correct_facility_selection(state, candidate_docs)
        state.metadata["selected_candidate_trace"] = self._candidate_trace(state.selected_docs, limit=3)
        state.metadata["selection_diagnostics"] = selection_result
        state.metadata["rerank_comparison"] = self._build_rerank_comparison(state.retrieved_docs, state.reranked_docs, state.selected_docs)
        selection_quality = self._evaluate_selection_quality(state.selected_docs)
        state.metadata["selection_quality"] = selection_quality
        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality["selection_quality"] = selection_quality
        state.metadata["citation_trace"] = self._build_citation_trace(state.selected_docs)
        state.context = build_context(state.selected_docs)

    def _filter_forbidden_source_docs(self, query_family: str | None, docs: list) -> list:
        forbidden = forbidden_source_types_for_family(query_family)
        if not forbidden:
            return docs
        filtered = [
            doc
            for doc in docs
            if str(doc.metadata.get("source_type") or "").strip().lower() not in forbidden
        ]
        return filtered or docs

    def _correct_faculty_selection(self, state: PipelineState, candidate_docs: list) -> None:
        required_entity = self._required_faculty_entity(state)
        if not required_entity:
            state.metadata.setdefault("faculty_query_type", self._faculty_query_type(state))
            return

        before_docs = list(state.selected_docs)
        before_trace = self._compact_doc_trace(before_docs)
        selected_matches = [doc for doc in before_docs if self._doc_contains_entity(doc, required_entity)]
        replacement_used = False
        if not selected_matches:
            selected_matches = [doc for doc in candidate_docs if self._doc_contains_entity(doc, required_entity)]
            if selected_matches:
                replacement_used = True
                selected_ids = {doc.chunk_id for doc in selected_matches[:3]}
                filler_docs = [
                    doc
                    for doc in before_docs
                    if doc.chunk_id not in selected_ids and not self._is_lifelong_faculty_noise(doc)
                ]
                state.selected_docs = [*selected_matches[:3], *filler_docs][:3]

        if selected_matches:
            original_order = {doc.chunk_id: index for index, doc in enumerate(state.selected_docs)}
            state.selected_docs = sorted(
                state.selected_docs,
                key=lambda doc: (
                    not self._doc_contains_entity(doc, required_entity),
                    self._is_lifelong_faculty_noise(doc),
                    original_order.get(doc.chunk_id, 999),
                ),
            )

        after_trace = self._compact_doc_trace(state.selected_docs)
        match_count = sum(1 for doc in state.selected_docs[:3] if self._doc_contains_entity(doc, required_entity))
        top1_match = self._doc_contains_entity(state.selected_docs[0], required_entity) if state.selected_docs else False
        source_correction_applied = before_trace != after_trace
        state.metadata["required_entity"] = required_entity
        state.metadata["faculty_query_type"] = "single_professor"
        state.metadata["required_entity_match_count"] = match_count
        state.metadata["top1_required_entity_match"] = top1_match
        state.metadata["source_correction_applied"] = source_correction_applied
        state.metadata["selected_before_correction"] = before_trace
        state.metadata["selected_after_correction"] = after_trace
        state.metadata["faculty_selection_correction"] = {
            "required_entity": required_entity,
            "replacement_used": replacement_used,
            "source_correction_applied": source_correction_applied,
            "match_count": match_count,
            "top1_match": top1_match,
        }
        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality.update(
                {
                    "required_entity": required_entity,
                    "required_entity_match_count": match_count,
                    "top1_required_entity_match": top1_match,
                    "source_correction_applied": source_correction_applied,
                }
            )
            if match_count == 0:
                self._set_retrieval_quality_status(retrieval_quality, "no_required_entity_match")
            elif retrieval_quality.get("diagnostic_reason") == "no_required_entity_match":
                self._set_retrieval_quality_status(retrieval_quality, "")

    def _correct_department_faculty_list_selection(self, state: PipelineState, candidate_docs: list) -> None:
        if self._faculty_query_type(state) != "department_faculty_list":
            state.metadata.setdefault("department_faculty_list_correction_applied", False)
            return

        before_docs = list(state.selected_docs)
        before_trace = self._compact_doc_trace(before_docs)
        preferred_pool = [
            *candidate_docs,
            *(state.reranked_docs or []),
            *(state.retrieved_docs or []),
        ]
        preferred_docs = []
        seen_preferred: set[str] = set()
        for doc in preferred_pool:
            if doc.chunk_id in seen_preferred or not self._is_faculty_list_doc(doc):
                continue
            seen_preferred.add(doc.chunk_id)
            preferred_docs.append(doc)
        if preferred_docs:
            preferred_ids = {doc.chunk_id for doc in preferred_docs[:3]}
            filler_docs = [
                doc
                for doc in before_docs
                if doc.chunk_id not in preferred_ids
            ]
            state.selected_docs = [*preferred_docs[:3], *filler_docs][:3]
        else:
            original_order = {doc.chunk_id: index for index, doc in enumerate(state.selected_docs)}
            state.selected_docs = sorted(
                state.selected_docs,
                key=lambda doc: (
                    not self._is_faculty_list_doc(doc),
                    self._is_department_faculty_noise_doc(doc),
                    original_order.get(doc.chunk_id, 999),
                ),
            )

        after_trace = self._compact_doc_trace(state.selected_docs)
        correction_applied = before_trace != after_trace
        state.metadata["faculty_query_type"] = "department_faculty_list"
        state.metadata["required_entity"] = ""
        state.metadata["required_entity_match_count"] = 0
        state.metadata["top1_required_entity_match"] = False
        state.metadata["department_faculty_list_correction_applied"] = correction_applied
        state.metadata["selected_before_correction"] = before_trace
        state.metadata["selected_after_correction"] = after_trace
        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality.update(
                {
                    "required_entity": "",
                    "required_entity_match_count": 0,
                    "top1_required_entity_match": False,
                    "department_faculty_list_correction_applied": correction_applied,
                }
            )
            if retrieval_quality.get("diagnostic_reason") == "no_required_entity_match":
                self._set_retrieval_quality_status(retrieval_quality, "")

    def _correct_facility_selection(self, state: PipelineState, candidate_docs: list) -> None:
        query_type = self._facility_query_type(state)
        state.metadata["facility_query_type"] = query_type
        if query_type == "none":
            state.metadata.setdefault("facility_alias_applied", False)
            state.metadata.setdefault("facility_evidence_found", False)
            return

        before_docs = list(state.selected_docs)
        before_trace = self._compact_doc_trace(before_docs)
        preferred_pool = [
            *before_docs,
            *(candidate_docs or []),
            *(state.reranked_docs or []),
            *(state.retrieved_docs or []),
        ]
        preferred_docs = []
        seen: set[str] = set()
        for doc in sorted(preferred_pool, key=lambda item: self._facility_doc_score(item, query_type), reverse=True):
            if doc.chunk_id in seen:
                continue
            seen.add(doc.chunk_id)
            if self._facility_doc_score(doc, query_type) <= 0:
                continue
            preferred_docs.append(doc)

        if preferred_docs:
            preferred_ids = {doc.chunk_id for doc in preferred_docs[:3]}
            filler_docs = [
                doc
                for doc in before_docs
                if doc.chunk_id not in preferred_ids and not self._is_facility_noise_doc(doc, query_type)
            ]
            state.selected_docs = [*preferred_docs[:3], *filler_docs][:3]
        else:
            original_order = {doc.chunk_id: index for index, doc in enumerate(state.selected_docs)}
            state.selected_docs = sorted(
                state.selected_docs,
                key=lambda doc: (
                    self._is_facility_noise_doc(doc, query_type),
                    -self._facility_doc_score(doc, query_type),
                    original_order.get(doc.chunk_id, 999),
                ),
            )

        after_trace = self._compact_doc_trace(state.selected_docs)
        evidence_found = any(self._facility_doc_score(doc, query_type) > 0 for doc in state.selected_docs)
        correction_applied = before_trace != after_trace
        alias_applied = self._facility_alias_applied(state.original_query)
        state.metadata["facility_alias_applied"] = alias_applied
        state.metadata["facility_evidence_found"] = evidence_found
        state.metadata["selected_before_facility_correction"] = before_trace
        state.metadata["selected_after_facility_correction"] = after_trace
        state.metadata["facility_selection_correction_applied"] = correction_applied

        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality.update(
                {
                    "facility_query_type": query_type,
                    "facility_alias_applied": alias_applied,
                    "facility_evidence_found": evidence_found,
                    "facility_selection_correction_applied": correction_applied,
                }
            )
            quality_reason = retrieval_quality.get("diagnostic_reason") or retrieval_quality.get("reason")
            if evidence_found and quality_reason == "no_exact_or_strong_keyword_match":
                self._set_retrieval_quality_status(retrieval_quality, "")
            if query_type == "cafeteria_hours" and evidence_found:
                retrieval_quality["partial_evidence"] = True

    def _facility_query_type(self, state: PipelineState) -> str:
        query = self._facility_normalized_query(state.original_query)
        features = self._query_features(state)
        family = features.get("family") if isinstance(features, dict) else ""
        has_info_engineering = self._mentions_info_engineering(query)
        has_cafeteria = any(term in query for term in ("학생식당", "식당", "학식"))
        has_hours = any(term in query for term in ("운영시간", "운영", "시간", "몇시", "몇 시"))
        has_location = any(term in query for term in ("위치", "어디", "몇번", "몇 번", "건물"))
        if has_info_engineering and has_cafeteria and has_hours:
            return "cafeteria_hours"
        if has_info_engineering and has_cafeteria:
            return "cafeteria_location"
        if has_info_engineering and (has_location or family in {"building_location", "facility"}):
            return "building_location"
        return "none"

    def _facility_normalized_query(self, query: str) -> str:
        text = re.sub(r"\s+", "", query or "")
        if "정보관" in text and "정보공학관" not in text:
            text += " 정보공학관"
        if re.search(r"23번?건물|23호관", text) and "정보공학관" not in text:
            text += " 정보공학관"
        return text

    def _mentions_info_engineering(self, text: str) -> bool:
        return any(term in text for term in ("정보관", "정보공학관", "23번건물", "23번 건물", "23호관"))

    def _facility_alias_applied(self, query: str) -> bool:
        text = re.sub(r"\s+", "", query or "")
        return ("정보관" in text and "정보공학관" not in text) or bool(re.search(r"23번?건물|23호관", text))

    def _facility_doc_score(self, doc, query_type: str) -> float:
        title = str(doc.title or "")
        source = str(doc.source or "")
        content = str(doc.content or "")
        text = f"{title}\n{source}\n{content}"
        compact = re.sub(r"\s+", "", text)
        score = 0.0
        if "정보공학관" in compact:
            score += 2.0
        if re.search(r"23\s*정보공학관|정보공학관.*23\s*번|23\s*번.*정보공학관", text):
            score += 2.2
        if any(term in title for term in ("캠퍼스맵", "복지문화시설", "편의·복지")):
            score += 1.2
        if any(term in source for term in ("deu-campus-map", "deu-culture")):
            score += 1.0
        if query_type == "building_location":
            if "정보공학관" in compact and any(term in compact for term in ("23", "2F", "2층", "학생식당")):
                score += 1.8
        if query_type in {"cafeteria_location", "cafeteria_hours"}:
            if "정보공학관" in compact and "학생식당" in compact:
                score += 2.4
            if any(term in compact for term in ("2층학생식당", "2F학생식당")):
                score += 1.6
            if self._extract_cafeteria_hours(content):
                score += 1.0
        if self._is_facility_noise_doc(doc, query_type):
            score -= 4.0
        return score

    def _is_facility_noise_doc(self, doc, query_type: str = "none") -> bool:
        title = str(doc.title or "")
        source = str(doc.source or "")
        content = str(doc.content or "")
        text = f"{title}\n{source}\n{content}"
        source_type = str(doc.metadata.get("source_type") or "").lower()
        if source_type in {"job", "scholarship", "external_notice", "bids"}:
            return True
        noise_terms = (
            "채용",
            "채용공고",
            "장학식비",
            "장학",
            "장애인",
            "외국인 입학",
            "기숙사",
            "효민생활관",
            "행복기숙사",
        )
        if any(term in text for term in noise_terms):
            if "정보공학관" not in text or query_type in {"cafeteria_location", "cafeteria_hours"}:
                return True
        if query_type in {"cafeteria_location", "cafeteria_hours"} and "식당" in text and "정보공학관" not in text:
            return True
        return False

    def _is_faculty_list_doc(self, doc) -> bool:
        title = str(doc.title or "").lower()
        return any(term in title for term in ("교수소개", "전임교수", "교수진"))

    def _is_department_faculty_noise_doc(self, doc) -> bool:
        title = str(doc.title or "").lower()
        return any(
            term in title
            for term in ("학과사무실", "학교생활", "학사일정", "진로", "입학상담", "이수표", "교육과정")
        )

    def _compact_doc_trace(self, docs: list) -> list[dict]:
        return [
            {
                "rank": rank,
                "doc_id": doc.doc_id,
                "chunk_id": doc.chunk_id,
                "title": doc.title,
                "source_url": doc.source,
                "source_type": doc.metadata.get("source_type"),
            }
            for rank, doc in enumerate(docs, start=1)
        ]

    def _evaluate_selection_quality(self, docs: list) -> dict:
        if not docs:
            return {
                "selected_context_contamination": False,
                "attachment_ratio": 0.0,
                "noise_ratio": 0.0,
                "top_heading_query_match": False,
                "doc_signals": [],
            }

        doc_signals = []
        contaminated_count = 0
        attachment_count = 0
        for rank, doc in enumerate(docs, start=1):
            signals = doc.metadata.get("rerank_signals") or {}
            if not isinstance(signals, dict):
                signals = {}
            section_type = str(doc.metadata.get("section_type") or "").lower()
            is_attachment = section_type == "attachment"
            noise_score = self._metadata_float(signals, "noise_score")
            heading_match = (
                self._metadata_float(signals, "title_match")
                + self._metadata_float(signals, "section_title_match")
            )
            is_contamination_candidate = noise_score >= 1.5 and heading_match <= 0.0
            attachment_count += 1 if is_attachment else 0
            contaminated_count += 1 if is_contamination_candidate else 0
            doc_signals.append(
                {
                    "rank": rank,
                    "doc_id": doc.doc_id,
                    "chunk_id": doc.chunk_id,
                    "title": doc.title,
                    "section_title": doc.metadata.get("section_title"),
                    "source_type": doc.metadata.get("source_type"),
                    "is_attachment": is_attachment,
                    "noise_score": noise_score,
                    "heading_query_match": heading_match > 0.0,
                    "rerank_score": doc.metadata.get("rerank_score", doc.score),
                    "rerank_signals": signals,
                }
            )

        return {
            "selected_context_contamination": contaminated_count > 0,
            "attachment_ratio": attachment_count / len(docs),
            "noise_ratio": contaminated_count / len(docs),
            "top_heading_query_match": doc_signals[0]["heading_query_match"],
            "doc_signals": doc_signals,
        }

    def _build_rerank_comparison(self, before_docs: list, after_docs: list, selected_docs: list) -> list[dict]:
        before_rank = {doc.chunk_id: rank for rank, doc in enumerate(before_docs, start=1)}
        selected_ids = {doc.chunk_id for doc in selected_docs}
        rows = []
        for rank_after, doc in enumerate(after_docs[:20], start=1):
            rank_before = before_rank.get(doc.chunk_id)
            rows.append(
                {
                    "chunk_id": doc.chunk_id,
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "rank_before": rank_before,
                    "rank_after": rank_after,
                    "rank_delta": None if rank_before is None else rank_before - rank_after,
                    "rerank_score": doc.metadata.get("rerank_score", doc.score),
                    "selected": doc.chunk_id in selected_ids,
                }
            )
        return rows

    def _build_citation_trace(self, selected_docs: list) -> list[dict]:
        trace = []
        for rank, doc in enumerate(selected_docs, start=1):
            trace.append(
                {
                    "rank": rank,
                    "doc_id": doc.doc_id,
                    "chunk_id": doc.chunk_id,
                    "title": doc.title,
                    "source_url": doc.source,
                    "source_type": doc.metadata.get("source_type"),
                    "content_type": doc.metadata.get("content_type") or doc.metadata.get("section_type"),
                    "score": doc.score,
                    "lexical_score": doc.metadata.get("lexical_score"),
                    "vector_score": doc.metadata.get("vector_score"),
                    "rerank_score": doc.metadata.get("rerank_score"),
                    "final_score": doc.metadata.get("final_score"),
                }
            )
        return trace

    def _metadata_float(self, values: dict, key: str) -> float:
        try:
            return float(values.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _generate(self, state: PipelineState) -> None:
        person_title_answer = self._build_person_title_answer(state)
        if person_title_answer:
            state.metadata["person_title_answer_rule"] = {
                "applied": False,
                "rule": "person_title_answer",
                "answer_type": "president_ordinal",
                "decision": "evidence",
            }
            self._record_rule_answer_candidate(
                state,
                "person_title_answer",
                person_title_answer,
                decision="evidence",
                reason="high_risk_rule_evidence_only",
            )
        department_faculty_answer = self._build_department_faculty_list_answer(state)
        if department_faculty_answer:
            if self._handle_structured_rule_answer(state, "department_faculty_list_answer", department_faculty_answer):
                return
        faculty_answer = self._build_faculty_answer(state)
        if faculty_answer:
            if self._handle_structured_rule_answer(state, "faculty_answer", faculty_answer):
                return
        facility_location_answer = self._build_facility_location_answer(state)
        if facility_location_answer:
            self._record_rule_answer_candidate(
                state,
                "facility_location_answer",
                facility_location_answer,
                decision="evidence",
                reason="high_risk_rule_evidence_only",
            )
        cafeteria_answer = self._build_cafeteria_answer(state)
        if cafeteria_answer:
            self._record_rule_answer_candidate(
                state,
                "cafeteria_answer",
                cafeteria_answer,
                decision="evidence",
                reason="high_risk_rule_evidence_only",
            )
        curriculum_answer = self._build_department_curriculum_answer(state)
        if curriculum_answer:
            if self._handle_structured_rule_answer(state, "department_curriculum_answer", curriculum_answer):
                return
        academic_schedule_answer = self._build_academic_schedule_answer(state)
        if academic_schedule_answer:
            if self._handle_structured_rule_answer(state, "academic_schedule_answer", academic_schedule_answer):
                return
        navigation_answer = self._build_navigation_fallback_answer(state)
        if navigation_answer:
            self._record_rule_answer_candidate(
                state,
                "navigation_fallback_answer",
                navigation_answer,
                decision="evidence",
                reason="high_risk_rule_evidence_only",
            )
        state.prompt = build_prompt(
            query=state.original_query,
            context=state.context,
            structured_evidence=self._structured_evidence_text(state),
        )
        state.metadata["answer_generation_input"] = {
            "selected_doc_count": len(state.selected_docs or []),
            "context_chars": len(state.context or ""),
            "prompt_chars": len(state.prompt or ""),
            "has_structured_evidence": bool(self._structured_evidence_text(state)),
        }
        generated_answer = generate_answer(state.prompt)
        state.metadata["answer_generation_output"] = {
            "raw_answer_chars": len(generated_answer or ""),
            "raw_answer_has_not_found": has_not_found_answer(generated_answer),
        }
        state.answer_text = repair_negative_answer_with_context(
            generated_answer,
            state.metadata,
            context=state.context,
            selected_docs=state.selected_docs,
            query=state.original_query,
        )
        state.metadata["answer_generation_output"].update(
            {
                "final_answer_chars": len(state.answer_text or ""),
                "final_answer_has_not_found": has_not_found_answer(state.answer_text),
                "negative_answer_repair": state.metadata.get("negative_answer_repair"),
            }
        )

    def _handle_structured_rule_answer(self, state: PipelineState, rule: str, answer: str) -> bool:
        passed, decision, missing_terms, reason = self._structured_rule_gate(state, rule)
        self._record_rule_answer_candidate(
            state,
            rule,
            answer,
            decision=decision,
            reason=reason,
            missing_terms=missing_terms,
        )
        if not passed:
            return False
        state.answer_text = answer
        return True

    def _record_rule_answer_candidate(
        self,
        state: PipelineState,
        rule: str,
        answer: str,
        *,
        decision: str = "final",
        reason: str = "rule_returned_before_llm",
        missing_terms: list[str] | None = None,
    ) -> None:
        doc = self._rule_answer_source_doc(state, rule)
        candidate = {
            "rule": rule,
            "decision": decision,
            "confidence": self._rule_answer_confidence(rule, state),
            "source_doc_id": getattr(doc, "doc_id", None),
            "source_chunk_id": getattr(doc, "chunk_id", None),
            "evidence": self._rule_answer_evidence(rule, answer, doc, state),
            "missing_terms": missing_terms if missing_terms is not None else self._rule_answer_missing_terms(rule, state),
            "reason": reason,
        }
        state.metadata.setdefault("rule_answer_candidates", []).append(candidate)

    def _structured_rule_gate(self, state: PipelineState, rule: str) -> tuple[bool, str, list[str], str]:
        missing: list[str] = []
        if rule == "faculty_answer":
            metadata = state.metadata.get("faculty_answer", {})
            required_entity = str(metadata.get("required_entity") or "").strip() if isinstance(metadata, dict) else ""
            fields = metadata.get("extracted_fields") if isinstance(metadata, dict) else None
            doc = self._rule_answer_source_doc(state, rule)
            if not required_entity:
                missing.append("required_entity")
            if required_entity and (not doc or not self._doc_contains_entity(doc, required_entity)):
                missing.append("matching_faculty_document")
            if not isinstance(fields, list) or not fields:
                missing.append("faculty_fields")
            if not (isinstance(metadata, dict) and metadata.get("source_doc_id") and metadata.get("source_chunk_id")):
                missing.append("source_document")
            return self._structured_gate_result(missing, "faculty_answer_gate")

        if rule == "department_faculty_list_answer":
            metadata = state.metadata.get("department_faculty_list_answer", {})
            doc = self._rule_answer_source_doc(state, rule)
            entry_count = int(metadata.get("entry_count") or 0) if isinstance(metadata, dict) else 0
            department_name = str(metadata.get("department_name") or "").strip() if isinstance(metadata, dict) else ""
            if entry_count < 2:
                missing.append("faculty_entries")
            if not doc or not self._is_faculty_list_doc(doc):
                missing.append("faculty_list_document")
            if not department_name and not self._department_name_from_title(getattr(doc, "title", "") or ""):
                missing.append("department_or_faculty_title")
            return self._structured_gate_result(missing, "department_faculty_list_answer_gate")

        if rule == "department_curriculum_answer":
            metadata = state.metadata.get("department_curriculum_answer", {})
            course_count = int(metadata.get("course_count") or 0) if isinstance(metadata, dict) else 0
            if not (isinstance(metadata, dict) and metadata.get("department_name")):
                missing.append("department_name")
            if not (isinstance(metadata, dict) and metadata.get("source_doc_id")):
                missing.append("source_document")
            if not (isinstance(metadata, dict) and metadata.get("year")):
                missing.append("curriculum_year")
            if course_count < 1:
                missing.append("curriculum_courses")
            return self._structured_gate_result(missing, "department_curriculum_answer_gate")

        if rule == "academic_schedule_answer":
            metadata = state.metadata.get("academic_schedule_answer", {})
            row_count = int(metadata.get("row_count") or 0) if isinstance(metadata, dict) else 0
            if not (isinstance(metadata, dict) and metadata.get("semester")):
                missing.append("semester")
            if not (isinstance(metadata, dict) and metadata.get("source_doc_id")):
                missing.append("source_document")
            if row_count < 1:
                missing.append("schedule_rows")
            return self._structured_gate_result(missing, "academic_schedule_answer_gate")

        return True, "final", [], "no_gate_required"

    def _structured_gate_result(self, missing: list[str], reason: str) -> tuple[bool, str, list[str], str]:
        if not missing:
            return True, "final", [], reason
        decision = "evidence" if "source_document" not in missing else "rejected"
        return False, decision, missing, reason

    def _structured_evidence_text(self, state: PipelineState) -> str:
        evidence_lines = self._format_structured_evidence(state)
        if not evidence_lines:
            return ""
        return "\n".join(evidence_lines).strip()

    def _format_structured_evidence(self, state: PipelineState) -> list[str]:
        candidates = state.metadata.get("rule_answer_candidates") or []
        lines: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict) or candidate.get("decision") != "evidence":
                continue
            parts = [
                f"rule={candidate.get('rule')}",
                f"confidence={candidate.get('confidence')}",
            ]
            if candidate.get("source_doc_id"):
                parts.append(f"source_doc_id={candidate.get('source_doc_id')}")
            if candidate.get("source_chunk_id"):
                parts.append(f"source_chunk_id={candidate.get('source_chunk_id')}")
            missing_terms = candidate.get("missing_terms") or []
            if missing_terms:
                parts.append("missing_terms=" + ",".join(str(term) for term in missing_terms))
            lines.append("- " + "; ".join(parts))
            for evidence in candidate.get("evidence") or []:
                lines.append(f"  evidence: {evidence}")
        return lines

    def _rule_answer_source_doc(self, state: PipelineState, rule: str):
        metadata_key_by_rule = {
            "department_faculty_list_answer": "department_faculty_list_answer",
            "faculty_answer": "faculty_answer",
            "facility_location_answer": "facility_answer",
            "cafeteria_answer": "facility_answer",
            "department_curriculum_answer": "department_curriculum_answer",
            "academic_schedule_answer": "academic_schedule_answer",
        }
        metadata = state.metadata.get(metadata_key_by_rule.get(rule, ""), {})
        source_chunk_id = metadata.get("source_chunk_id") if isinstance(metadata, dict) else None
        source_doc_id = metadata.get("source_doc_id") if isinstance(metadata, dict) else None
        docs = [*(state.selected_docs or []), *(state.reranked_docs or []), *(state.retrieved_docs or [])]
        if source_chunk_id:
            for doc in docs:
                if getattr(doc, "chunk_id", None) == source_chunk_id:
                    return doc
        if source_doc_id:
            for doc in docs:
                if getattr(doc, "doc_id", None) == source_doc_id:
                    return doc
        return docs[0] if docs else None

    def _rule_answer_confidence(self, rule: str, state: PipelineState) -> float:
        if rule in {"faculty_answer", "department_faculty_list_answer", "department_curriculum_answer", "academic_schedule_answer"}:
            return 0.95
        if rule == "person_title_answer":
            return 0.8
        if rule == "facility_location_answer":
            return 0.75
        if rule == "cafeteria_answer":
            metadata = state.metadata.get("facility_answer", {})
            if isinstance(metadata, dict) and metadata.get("type") == "cafeteria_hours" and not metadata.get("hours_found"):
                return 0.55
            return 0.7
        if rule == "navigation_fallback_answer":
            return 0.65
        return 0.5

    def _rule_answer_evidence(self, rule: str, answer: str, doc, state: PipelineState) -> list[str]:
        if rule == "cafeteria_answer" and self._rule_answer_missing_terms(rule, state):
            evidence = []
            title = (getattr(doc, "title", "") or "").strip()
            content = re.sub(r"\s+", " ", getattr(doc, "content", "") or "").strip()
            source = (getattr(doc, "source", "") or "").strip()
            if title:
                evidence.append(f"title: {title}")
            if content:
                evidence.append(f"content: {content[:240]}")
            if source:
                evidence.append(f"source: {source}")
            return evidence
        lines = [line.strip() for line in (answer or "").splitlines() if line.strip()]
        return lines[:3]

    def _rule_answer_missing_terms(self, rule: str, state: PipelineState) -> list[str]:
        if rule == "cafeteria_answer":
            metadata = state.metadata.get("facility_answer", {})
            if isinstance(metadata, dict) and metadata.get("type") == "cafeteria_hours" and not metadata.get("hours_found"):
                return ["operating_hours"]
        return []

    def _repair_negative_answer_with_context(self, answer: str, state: PipelineState) -> str:
        return repair_negative_answer_with_context(answer, state.metadata)

    def _build_facility_location_answer(self, state: PipelineState) -> str | None:
        if self._facility_query_type(state) != "building_location":
            return None
        doc = self._best_facility_doc(state, "building_location")
        if not doc:
            return None
        source = doc.source or "출처 없음"
        state.metadata["facility_answer_used"] = True
        state.metadata["facility_partial_answer"] = False
        state.metadata["facility_answer"] = {
            "type": "building_location",
            "source_doc_id": doc.doc_id,
            "source_chunk_id": doc.chunk_id,
        }
        prefix = "정보관은 정보공학관을 의미하며, " if self._facility_alias_applied(state.original_query) else ""
        detail = "교내 23번 건물입니다."
        if "학생식당" in (doc.content or ""):
            detail += " 캠퍼스맵 기준 정보공학관 2층에는 학생식당, 교직원식당, 편의점 등이 있습니다."
        return f"{prefix}정보공학관은 {detail}\n출처: {source}"

    def _build_cafeteria_answer(self, state: PipelineState) -> str | None:
        query_type = self._facility_query_type(state)
        if query_type not in {"cafeteria_location", "cafeteria_hours"}:
            return None
        doc = self._best_facility_doc(state, query_type)
        if not doc:
            return None
        source = doc.source or "출처 없음"
        hours = self._extract_cafeteria_hours(doc.content or "")
        state.metadata["facility_answer_used"] = True
        state.metadata["facility_partial_answer"] = query_type == "cafeteria_hours" and not hours
        state.metadata["facility_answer"] = {
            "type": query_type,
            "source_doc_id": doc.doc_id,
            "source_chunk_id": doc.chunk_id,
            "hours_found": bool(hours),
        }
        if query_type == "cafeteria_hours":
            if hours:
                return f"정보공학관 학생식당 운영시간은 {hours}입니다. 학생식당은 정보공학관 2층에 있습니다.\n출처: {source}"
            return (
                "현재 문서에서는 정보공학관 학생식당의 운영시간은 확인되지 않습니다. "
                "다만 복지문화시설/캠퍼스맵 기준 학생식당은 정보공학관 2층에 있습니다.\n"
                f"출처: {source}"
            )
        return f"정보공학관 학생식당은 정보공학관 2층에 있습니다.\n출처: {source}"

    def _best_facility_doc(self, state: PipelineState, query_type: str):
        candidates = self._facility_candidate_docs(state)
        scored = [
            (self._facility_doc_score(doc, query_type), doc)
            for doc in candidates
            if not self._is_facility_noise_doc(doc, query_type)
        ]
        scored = [(score, doc) for score, doc in scored if score > 0]
        if not scored:
            return None
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][1]

    def _facility_candidate_docs(self, state: PipelineState) -> list:
        docs = []
        seen: set[str] = set()
        for doc in [*(state.selected_docs or []), *(state.reranked_docs or []), *(state.retrieved_docs or [])]:
            if doc.chunk_id in seen:
                continue
            seen.add(doc.chunk_id)
            docs.append(doc)
        return docs

    def _extract_cafeteria_hours(self, text: str) -> str:
        if "정보공학관" not in (text or ""):
            return ""
        compact = re.sub(r"\s+", " ", text or "")
        for match in re.finditer(r"(?:운영시간|이용시간|식당 이용시간)\s*[:：]?\s*([0-2]?\d:[0-5]\d\s*[~\-]\s*[0-2]?\d:[0-5]\d(?:\s*,?\s*[0-2]?\d:[0-5]\d\s*[~\-]\s*[0-2]?\d:[0-5]\d)*)", compact):
            value = match.group(1).strip()
            window = compact[max(0, match.start() - 80) : match.end() + 80]
            if "기숙사" in window or "효민생활관" in window or "외국인" in window:
                continue
            return value
        return ""

    def _build_faculty_answer(self, state: PipelineState) -> str | None:
        if self._faculty_query_type(state) != "single_professor":
            return None
        faculty_name = self._required_faculty_entity(state)
        if not faculty_name:
            return None
        matching_docs = [
            doc
            for doc in state.selected_docs
            if self._doc_contains_entity(doc, faculty_name) and not self._is_lifelong_faculty_noise(doc)
        ]
        if not matching_docs:
            matching_docs = [
                doc
                for doc in state.selected_docs
                if self._doc_contains_entity(doc, faculty_name)
            ]
        if not matching_docs:
            return None

        extracted = self._extract_faculty_fields(matching_docs[0].content or "", faculty_name)
        if not extracted:
            return None

        source = matching_docs[0].source or "출처 없음"
        lines = [f"{faculty_name} 교수님 정보입니다."]
        for label, value in extracted:
            lines.append(f"- {label}: {value}")
        lines.append(f"출처: {source}")
        state.metadata["faculty_answer"] = {
            "required_entity": faculty_name,
            "source_doc_id": matching_docs[0].doc_id,
            "source_chunk_id": matching_docs[0].chunk_id,
            "extracted_fields": [{"label": label, "value": value} for label, value in extracted],
        }
        return "\n".join(lines)

    def _build_department_faculty_list_answer(self, state: PipelineState) -> str | None:
        if self._faculty_query_type(state) != "department_faculty_list":
            return None
        docs = [
            doc
            for doc in [*(state.selected_docs or []), *(state.reranked_docs or []), *(state.retrieved_docs or [])]
            if self._is_faculty_list_doc(doc)
        ]
        if not docs:
            return None
        seen_chunks: set[str] = set()
        unique_docs = []
        for doc in docs:
            if doc.chunk_id in seen_chunks:
                continue
            seen_chunks.add(doc.chunk_id)
            unique_docs.append(doc)

        department_name = self._extract_department_faculty_name(state.original_query)
        for doc in unique_docs[:5]:
            entries = self._extract_department_faculty_entries(doc.content or "")
            if len(entries) < 2:
                continue
            source = doc.source or "출처 없음"
            title_name = department_name or self._department_name_from_title(doc.title)
            heading = f"{title_name} 교수 목록입니다." if title_name else "교수 목록입니다."
            lines = [heading]
            for entry in entries[:12]:
                details = []
                if entry.get("field"):
                    details.append(entry["field"])
                if entry.get("office"):
                    details.append(f"연구실 {entry['office']}")
                if entry.get("phone"):
                    details.append(f"연락처 {entry['phone']}")
                if entry.get("email"):
                    details.append(f"E-MAIL {entry['email']}")
                suffix = " / ".join(details)
                lines.append(f"- {entry['name']}: {suffix}" if suffix else f"- {entry['name']}")
            lines.append(f"출처: {source}")
            state.metadata["department_faculty_list_answer"] = {
                "source_doc_id": doc.doc_id,
                "source_chunk_id": doc.chunk_id,
                "entry_count": len(entries),
                "department_name": title_name,
            }
            return "\n".join(lines)
        return None

    def _department_name_from_title(self, title: str) -> str:
        match = re.search(r"([A-Za-z0-9가-힣&·ㆍ\-\+]+?(?:학과|전공|학부|대학원))", title or "")
        return match.group(1) if match else ""

    def _extract_department_faculty_entries(self, content: str) -> list[dict[str, str]]:
        normalized_content = (content or "").replace("\\n", "\n")
        lines = [line.strip() for line in normalized_content.splitlines()]
        lines = [line for line in lines if line and not self._is_faculty_noise_text(line)]
        entries: list[dict[str, str]] = []
        seen_names: set[str] = set()
        name_indexes = []
        for index, line in enumerate(lines):
            match = re.match(r"^([가-힣]{2,5})\s*(?:교수님?)?$", line)
            if not match:
                continue
            name = match.group(1)
            if not self._is_valid_faculty_entity(name) or self._is_faculty_name_noise(name):
                continue
            previous_lines = [
                previous
                for previous in lines[max(0, index - 2) : index]
                if not self._is_faculty_noise_text(previous) and not self._is_faculty_name_noise(previous)
            ]
            if any(re.fullmatch(r"[가-힣]{2,5}\s*교수(?:님)?", previous) for previous in previous_lines):
                continue
            if any(self._is_valid_faculty_entity(previous) for previous in previous_lines):
                continue
            lookahead = "\n".join(lines[index + 1 : min(len(lines), index + 10)])
            if not any(term in lookahead.lower() for term in ("연구실", "연락처", "e-mail", "email", "이메일")):
                continue
            name_indexes.append((index, name))
        for index, name in name_indexes:
            if name in seen_names:
                continue
            seen_names.add(name)
            window = lines[index + 1 : min(len(lines), index + 14)]
            entry = {"name": name, "field": "", "office": "", "phone": "", "email": ""}
            for offset, line in enumerate(window):
                lowered = line.lower()
                if not entry["email"]:
                    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line)
                    if email_match:
                        entry["email"] = email_match.group(0)
                if not entry["phone"]:
                    phone_match = re.search(r"\b0\d{1,2}-\d{3,4}-\d{4}\b", line)
                    if phone_match:
                        entry["phone"] = phone_match.group(0)
                if any(term in lowered for term in ("연구실", "office")) and not entry["office"]:
                    entry["office"] = self._next_meaningful_line(window, offset)
                elif any(term in lowered for term in ("연락처", "전화")) and not entry["phone"]:
                    entry["phone"] = self._next_meaningful_line(window, offset)
                elif any(term in lowered for term in ("e-mail", "email", "이메일")) and not entry["email"]:
                    entry["email"] = self._next_meaningful_line(window, offset)
                elif (
                    not entry["field"]
                    and not any(term in lowered for term in ("연구실", "연락처", "e-mail", "email", "이메일", "홈페이지", "학력", "경력"))
                    and not self._is_valid_faculty_entity(line)
                ):
                    entry["field"] = line
            entries.append(entry)
        return entries

    def _is_faculty_name_noise(self, value: str) -> bool:
        return value in {
            "내용",
            "검색",
            "검색어",
            "검색분류선택",
            "게시글검색",
            "연구실",
            "연락처",
            "이메일",
            "홈페이지",
            "직위",
            "학력",
            "경력",
            "강의분야",
            "연구분야",
            "전공명",
            "공통교양",
            "전공필수",
            "전공선택",
            "교수소개",
        }

    def _next_meaningful_line(self, lines: list[str], index: int) -> str:
        for line in lines[index + 1 : index + 4]:
            if line and not self._is_faculty_noise_text(line):
                return line
        return ""

    def _extract_faculty_fields(self, content: str, faculty_name: str) -> list[tuple[str, str]]:
        normalized_content = (content or "").replace("\\n", "\n")
        lines = [line.strip() for line in normalized_content.splitlines()]
        lines = [line for line in lines if line and not self._is_faculty_noise_text(line)]
        name_indexes = [index for index, line in enumerate(lines) if faculty_name in line]
        if not name_indexes:
            return []

        fields: list[tuple[str, str]] = []
        seen: set[str] = set()
        labels = {
            "연구실": "연구실",
            "연락처": "연락처",
            "e-mail": "E-MAIL",
            "email": "E-MAIL",
            "이메일": "E-MAIL",
            "연구 분야": "연구 분야",
            "연구분야": "연구 분야",
            "강의분야": "강의 분야",
            "직위": "직위",
        }

        def add(label: str, value: str) -> None:
            clean_value = re.sub(r"\s+", " ", value).strip(" :-|")
            if not clean_value or clean_value == label or label in seen or self._is_faculty_noise_text(clean_value):
                return
            seen.add(label)
            fields.append((label, clean_value))

        for name_index in name_indexes[:2]:
            window = lines[name_index : min(len(lines), name_index + 40)]
            if len(window) > 1:
                first_detail = window[1]
                if (
                    not self._is_faculty_noise_text(first_detail)
                    and not any(marker in first_detail.lower() for marker in labels)
                    and "교수" not in first_detail
                ):
                    add("연구 분야", first_detail)
            for offset, line in enumerate(window):
                lowered = line.lower()
                for marker, label in labels.items():
                    if marker not in lowered:
                        continue
                    inline = re.split(r"[:：|]", line, maxsplit=1)
                    if len(inline) == 2 and inline[1].strip():
                        add(label, inline[1])
                        continue
                    for next_line in window[offset + 1 : offset + 4]:
                        if next_line and not any(other in next_line.lower() for other in labels):
                            add(label, next_line)
                            break
            if fields:
                break

        if not any(label == "E-MAIL" for label, _ in fields):
            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "\n".join(lines))
            if match:
                add("E-MAIL", match.group(0))
        if not any(label == "연락처" for label, _ in fields):
            match = re.search(r"\b0\d{1,2}-\d{3,4}-\d{4}\b", "\n".join(lines))
            if match:
                add("연락처", match.group(0))
        return fields[:6]

    def _is_faculty_noise_text(self, value: str) -> bool:
        text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
        if not text:
            return True
        noise_values = {
            "[title]",
            "[body]",
            "[attachment]",
            "content",
            "body",
            "게시글 검색",
            "검색분류선택",
            "검색어",
            "검색",
            "홈페이지",
            "닫기",
            "교수소개",
            "외래교수소개",
            "겸임교수소개",
            "전임교수소개",
        }
        return text in noise_values

    def _build_navigation_fallback_answer(self, state: PipelineState) -> str | None:
        query = state.original_query or ""
        if not state.selected_docs:
            return None
        if any(term in query for term in ("조직도", "조직", "부서")):
            doc = self._first_selected_doc_matching(
                state,
                title_terms=("조직도",),
                source_terms=("deu-organization",),
                source_types=("institution",),
            )
            if doc:
                source = doc.source or "출처 없음"
                return (
                    "동의대학교 조직도는 공식 조직도 페이지에서 확인할 수 있습니다. "
                    "부서별 조직 관계와 담당 조직을 보려면 아래 출처의 조직도 문서를 참고해 주세요.\n"
                    f"출처: {source}"
                )
        if any(term in query for term in ("분실물", "분실", "lost")):
            doc = self._first_selected_doc_matching(
                state,
                title_terms=("분실물", "분실물센터", "분실물신고"),
                source_terms=("deu-lostfound", "lostproperty"),
                source_types=("lostfound", "library"),
            )
            if doc:
                source = doc.source or "출처 없음"
                if "lib.deu.ac.kr" in source:
                    return (
                        "도서관 분실물은 중앙도서관 분실물신고 게시판에서 확인할 수 있습니다. "
                        "습득물 목록이나 신고 글은 아래 출처의 게시판을 확인해 주세요.\n"
                        f"출처: {source}"
                    )
                return (
                    "동의대학교 분실물은 공식 분실물센터 게시판에서 확인할 수 있습니다. "
                    "분실물 조회나 신고는 아래 출처의 게시판을 이용해 주세요.\n"
                    f"출처: {source}"
                )
        return None

    def _first_selected_doc_matching(
        self,
        state: PipelineState,
        *,
        title_terms: tuple[str, ...] = (),
        source_terms: tuple[str, ...] = (),
        source_types: tuple[str, ...] = (),
    ):
        for doc in state.selected_docs:
            title = doc.title or ""
            source = doc.source or ""
            source_type = str(doc.metadata.get("source_type") or "")
            if title_terms and any(term in title for term in title_terms):
                return doc
            if source_terms and any(term in source for term in source_terms):
                return doc
            if source_types and source_type in source_types:
                return doc
        return None

    def _build_person_title_answer(self, state: PipelineState) -> str | None:
        query_features = self._query_features(state)
        if not isinstance(query_features, dict) or query_features.get("family") != "person_title":
            return None
        ordinal = self._extract_president_ordinal(state.original_query)
        president_docs = [
            doc
            for doc in state.selected_docs
            if "총장" in (doc.title or "") and ("역대" in (doc.title or "") or "역대" in (doc.content or ""))
        ]
        if not president_docs:
            return None
        if ordinal is None:
            return self._build_president_list_answer(state, president_docs)
        for doc in president_docs:
            parsed = self._extract_president_entry(doc.content or "", ordinal)
            if not parsed:
                parsed = self._extract_president_entry_from_raw_html(doc.doc_id, ordinal)
            if not parsed:
                parsed = self._extract_president_entry_from_reference(doc.doc_id, ordinal)
            if parsed:
                source = doc.source or "출처 없음"
                detail = self._format_president_detail(parsed.get("period") or "")
                return f"동의대학교 제{ordinal}대 총장은 {parsed['name']}입니다.{detail}\n출처: {source}"
        return None

    def _build_president_list_answer(self, state: PipelineState, president_docs: list) -> str | None:
        if not any(term in (state.original_query or "") for term in ("역대", "목록", "총장")):
            return None
        entries: list[str] = []
        seen: set[str] = set()
        for doc in president_docs:
            for ordinal_label, name in self._extract_president_list_entries(doc.content or ""):
                key = f"{ordinal_label}:{name}"
                if key in seen:
                    continue
                seen.add(key)
                entries.append(f"- {ordinal_label}: {name}")
                if len(entries) >= 8:
                    break
            if entries:
                source = doc.source or "출처 없음"
                return "\n".join(["선택된 문서에서 확인되는 역대 총장 정보입니다.", *entries, f"출처: {source}"])
        return None

    def _extract_president_list_entries(self, text: str) -> list[tuple[str, str]]:
        entries: list[tuple[str, str]] = []
        lines = [re.sub(r"\s+", " ", line).strip(" #\t") for line in (text or "").splitlines()]
        for index, line in enumerate(lines):
            if not line or "총장" not in line:
                continue
            ordinal_match = re.search(r"제\s*(\d{1,2}\s*대(?:\s*[·ㆍ&]\s*\d{1,2}\s*대)?)\s*총장", line)
            if not ordinal_match:
                continue
            ordinal_label = "제" + re.sub(r"\s+", "", ordinal_match.group(1)) + " 총장"
            for candidate in lines[index + 1 : index + 6]:
                name = self._clean_president_name_candidate(candidate)
                if name:
                    entries.append((ordinal_label, name))
                    break
        return entries

    def _clean_president_name_candidate(self, value: str) -> str:
        candidate = re.sub(r"\([^)]*\)", "", value or "")
        candidate = re.sub(r"[A-Za-z0-9.~·ㆍ\-]+", " ", candidate)
        candidate = re.sub(r"\s+", "", candidate)
        if not re.fullmatch(r"[가-힣]{2,8}", candidate):
            return ""
        if candidate in {"학력", "경력", "역대총장", "총장", "동의대학교"}:
            return ""
        return candidate

    def _extract_president_ordinal(self, query: str) -> int | None:
        match = re.search(r"(?:제\s*)?(\d{1,2})\s*대\s*총장|(\d{1,2})\s*번째\s*총장", query or "")
        if not match:
            return None
        value = match.group(1) or match.group(2)
        try:
            ordinal = int(value)
        except (TypeError, ValueError):
            return None
        return ordinal if 1 <= ordinal <= 50 else None

    def _format_president_detail(self, value: str) -> str:
        detail = re.sub(r"\s+", " ", value or "").strip()
        if not detail:
            return ""
        label = "재임기간" if re.search(r"(?:19|20)\d{2}", detail) else "추가 정보"
        return f" {label}: {detail}."

    def _extract_president_entry(self, text: str, ordinal: int) -> dict[str, str] | None:
        lines = [re.sub(r"\s+", " ", line).strip(" |") for line in (text or "").splitlines()]
        lines = [line for line in lines if line]
        marker = rf"(?:제\s*)?(?<!\d){ordinal}\s*대(?!\d)"
        for index, line in enumerate(lines):
            if not re.search(marker, line):
                continue
            window = " ".join(lines[index : index + 4])
            parsed = self._parse_president_window(window, ordinal)
            if parsed:
                return parsed
        compact_text = re.sub(r"\s+", " ", text or "")
        for match in re.finditer(marker, compact_text):
            window = compact_text[match.start() : min(len(compact_text), match.start() + 180)]
            parsed = self._parse_president_window(window, ordinal)
            if parsed:
                return parsed
        return None

    def _parse_president_window(self, text: str, ordinal: int) -> dict[str, str] | None:
        marker = rf"(?:제\s*)?(?<!\d){ordinal}\s*대(?!\d)"
        pattern = re.compile(
            marker
            + r"\s*(?:총장)?\s*"
            + r"(?P<name>[가-힣]{2,5}(?:\([^)]+\))?)"
            + r"(?:\s+(?P<period>(?:19|20)\d{2}[.\-~\s년월일]*(?:19|20)?\d{0,4}[.\-~\s년월일]*))?"
        )
        match = pattern.search(text)
        if not match:
            adjacent_pattern = re.compile(
                marker
                + r".{0,80}?"
                + r"(?P<name>[가-힣]{2,5}(?:\([^)]+\))?)"
                + r"(?:.{0,20}?(?P<period>(?:19|20)\d{2}[.\-~\s년월일]*(?:19|20)?\d{0,4}[.\-~\s년월일]*))?"
            )
            match = adjacent_pattern.search(text)
        if not match:
            return None
        name = (match.group("name") or "").strip()
        if name in {"총장", "역대총장", "동의대", "동의대학교"}:
            return None
        period = re.sub(r"\s+", " ", (match.group("period") or "").strip(" .-~"))
        return {"name": name, "period": period}

    def _extract_president_entry_from_raw_html(self, doc_id: str, ordinal: int) -> dict[str, str] | None:
        raw_html = self._load_raw_static_html(doc_id)
        if not raw_html:
            return None
        subject_pattern = rf"(?:제\s*)?(?<!\d){ordinal}\s*대(?!\d)(?:\s*[\u00b7&]\s*\d+\s*대)?\s*(?:총장|학장)"
        item_pattern = re.compile(
            r"<li\b[^>]*>.*?"
            r"<strong[^>]*class=[\"'][^\"']*subject[^\"']*[\"'][^>]*>(?P<subject>.*?)</strong>.*?"
            r"<span[^>]*class=[\"'][^\"']*nm[^\"']*[\"'][^>]*>(?P<name>.*?)</span>.*?"
            r"(?:<span[^>]*class=[\"'][^\"']*nm-info[^\"']*[\"'][^>]*>(?P<info>.*?)</span>)?",
            re.IGNORECASE | re.DOTALL,
        )
        for match in item_pattern.finditer(raw_html):
            subject = self._html_to_text(match.group("subject"))
            if not re.search(subject_pattern, subject):
                continue
            name = self._html_to_text(match.group("name"))
            info = self._html_to_text(match.group("info") or "")
            if not name:
                return None
            return {"name": name, "period": info}
        return None

    def _load_raw_static_html(self, doc_id: str) -> str | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", doc_id or ""):
            return None
        base_dir = Path("crawler/crawler/data/raw/html")
        if not base_dir.exists():
            return None
        for path in base_dir.rglob(f"{doc_id}.html"):
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    def _html_to_text(self, value: str) -> str:
        text = re.sub(r"<[^>]+>", " ", value or "")
        text = html.unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_president_entry_from_reference(self, doc_id: str, ordinal: int) -> dict[str, str] | None:
        resource_path = Path(__file__).resolve().parents[1] / "resources" / "deu_presidents.json"
        try:
            records = json.loads(resource_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(records, list):
            return None
        for record in records:
            if not isinstance(record, dict):
                continue
            doc_ids = record.get("doc_ids") or []
            ordinals = record.get("ordinals") or []
            if doc_id not in doc_ids or ordinal not in ordinals:
                continue
            name = str(record.get("name") or "").strip()
            info = str(record.get("info") or "").strip()
            if name:
                return {"name": name, "period": info}
        return None

    def _build_department_curriculum_answer(self, state: PipelineState) -> str | None:
        query_features = self._query_features(state)
        if not isinstance(query_features, dict) or query_features.get("family") != "department_curriculum":
            return None
        department_name = self._extract_department_name(state.original_query, state.keywords)
        year = self._extract_curriculum_year(state.original_query)
        if not department_name:
            return None

        matching_docs = [
            doc
            for doc in state.selected_docs
            if department_name in (doc.title or "") and self._is_curriculum_title(doc.title or "")
        ]
        if not matching_docs:
            return None
        if not year:
            source = matching_docs[0].source or "출처 없음"
            state.metadata["department_curriculum_answer"] = {
                "department_name": department_name,
                "source_doc_id": matching_docs[0].doc_id,
                "source_chunk_id": matching_docs[0].chunk_id,
                "year": None,
                "course_count": 0,
            }
            return f"{department_name} 이수표는 아래 출처에서 확인할 수 있습니다.\n출처: {source}"

        combined = "\n".join(doc.content or "" for doc in matching_docs)
        block = self._extract_curriculum_year_block(combined, year, department_name)
        courses = self._extract_curriculum_courses(block)
        if not courses:
            return None

        display_courses = ", ".join(courses[:12])
        source = matching_docs[0].source or "출처 없음"
        state.metadata["department_curriculum_answer"] = {
            "department_name": department_name,
            "source_doc_id": matching_docs[0].doc_id,
            "source_chunk_id": matching_docs[0].chunk_id,
            "year": year,
            "course_count": len(courses),
        }
        return (
            f"{department_name} 이수표 기준 {year}학년 교육과정에는 다음 과목들이 확인됩니다.\n"
            f"- {display_courses}\n"
            "PDF 표 추출 특성상 학기 구분은 원본 이수표에서 함께 확인하는 것이 좋습니다.\n"
            f"출처: {source}"
        )

    def _build_academic_schedule_answer(self, state: PipelineState) -> str | None:
        query_features = self._query_features(state)
        if not isinstance(query_features, dict) or query_features.get("family") != "academic_schedule":
            return None
        if "보강" not in state.original_query:
            return None
        semester = self._extract_semester_label(state.original_query)
        if not semester:
            return None

        combined_text = "\n".join(doc.content or "" for doc in state.selected_docs)
        block = self._extract_semester_schedule_block(combined_text, semester)
        rows = self._extract_makeup_schedule_rows(block or combined_text)
        if not rows:
            return None

        source = next((doc.source for doc in state.selected_docs if doc.source), "출처 없음")
        source_doc = next((doc for doc in state.selected_docs if doc.source), state.selected_docs[0] if state.selected_docs else None)
        state.metadata["academic_schedule_answer"] = {
            "semester": semester,
            "row_count": len(rows),
            "source_doc_id": getattr(source_doc, "doc_id", None),
            "source_chunk_id": getattr(source_doc, "chunk_id", None),
        }
        lines = [f"{semester} 보강일정은 다음과 같습니다."]
        for date, detail in rows[:8]:
            lines.append(f"- {date}: {detail}")
        lines.append(f"출처: {source}")
        return "\n".join(lines)

    def _extract_semester_label(self, query: str) -> str | None:
        semester_match = re.search(r"([12])\s*학기", query or "")
        if not semester_match:
            return None
        year_match = re.search(r"(20\d{2}|\d{2})\s*년?", query or "")
        year = "2026"
        if year_match:
            year_digits = re.sub(r"\D", "", year_match.group(1))
            year = f"20{year_digits}" if len(year_digits) == 2 else year_digits[:4]
        return f"{year}년 {semester_match.group(1)}학기"

    def _extract_semester_schedule_block(self, text: str, semester: str) -> str:
        if not text or semester not in text:
            return text
        candidates: list[tuple[int, str]] = []
        for match in re.finditer(re.escape(semester), text):
            start = match.start()
            next_match = re.search(r"20\d{2}년\s+[12]학기", text[start + len(semester) :])
            end = start + len(semester) + next_match.start() if next_match else len(text)
            block = text[start:end]
            candidates.append((block.count("지정보강일"), block))
        if not candidates:
            return text
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _extract_makeup_schedule_rows(self, text: str) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        previous_date = ""
        date_pattern = re.compile(r"^\s*(\d{1,2}월\s+\d{1,2}일|\d{1,2}일)\s*(?:\||$)")
        for raw_line in (text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            table_match = re.match(r"^(\d{1,2}월\s+\d{1,2}일|\d{1,2}일)\s*\|\s*(지정보강일.+)$", line)
            if table_match:
                rows.append((table_match.group(1), table_match.group(2).strip()))
                previous_date = table_match.group(1)
                continue
            date_match = date_pattern.match(line)
            if date_match and "지정보강일" not in line:
                previous_date = date_match.group(1)
                continue
            if "지정보강일" in line:
                detail = line.split("|", 1)[-1].strip()
                rows.append((previous_date or "일자 확인 필요", detail))

        deduped: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            if row in seen:
                continue
            seen.add(row)
            deduped.append(row)
        return deduped

    def _query_features(self, state: PipelineState) -> dict:
        query_understanding = state.metadata.get("query_understanding", {})
        if not isinstance(query_understanding, dict):
            return {}
        query_features = query_understanding.get("query_features", {})
        return query_features if isinstance(query_features, dict) else {}

    def _extract_department_name(self, query: str, keywords: list[str] | None = None) -> str | None:
        candidates = [query, *(keywords or [])]
        for text in candidates:
            for match in re.finditer(r"[가-힣A-Za-z0-9·&]+학과", text or ""):
                value = match.group(0)
                if len(value) >= 3:
                    return value
        return None

    def _extract_curriculum_year(self, query: str) -> int | None:
        match = re.search(r"([1-4])\s*학년", query or "")
        return int(match.group(1)) if match else None

    def _is_curriculum_title(self, title: str) -> bool:
        return "이수표" in title and "교육과정" in title

    def _extract_department_name(self, query: str, keywords: list[str] | None = None) -> str | None:
        candidates = [query, *(keywords or [])]
        for text in candidates:
            for match in re.finditer(r"[A-Za-z0-9가-힣·ㆍ&\-\+]+?학과", text or ""):
                value = match.group(0)
                if len(value) >= 3:
                    return value
        return None

    def _extract_curriculum_year(self, query: str) -> int | None:
        match = re.search(r"([1-4])\s*학년", query or "")
        return int(match.group(1)) if match else None

    def _is_curriculum_title(self, title: str) -> bool:
        return "이수표" in title and "교육과정" in title

    def _filter_department_curriculum_docs(self, state: PipelineState, docs: list) -> list:
        department_name = self._extract_department_name(state.original_query, state.keywords)
        if not department_name:
            return docs

        exact_docs = [
            doc
            for doc in docs
            if department_name in (doc.title or "") and self._is_curriculum_title(doc.title or "")
        ]
        if exact_docs:
            state.metadata["department_curriculum_selection"] = {
                "department_name": department_name,
                "filtered_to_exact_department": True,
                "candidate_count": len(exact_docs),
            }
            return exact_docs

        state.metadata["department_curriculum_selection"] = {
            "department_name": department_name,
            "filtered_to_exact_department": False,
            "candidate_count": len(docs),
        }
        return docs

    def _filter_canonical_notice_docs(self, state: PipelineState, docs: list) -> list:
        canonical_docs = [
            doc
            for doc in docs
            if doc.metadata.get("is_canonical_notice") or doc.metadata.get("canonical_source_supplement")
        ]
        if not canonical_docs:
            state.metadata["canonical_notice_selection"] = {
                "filtered_to_canonical": False,
                "candidate_count": len(docs),
            }
            return docs
        filtered = [
            doc
            for doc in docs
            if doc in canonical_docs or str(doc.metadata.get("source_type") or "").lower() != "department"
        ]
        state.metadata["canonical_notice_selection"] = {
            "filtered_to_canonical": True,
            "canonical_count": len(canonical_docs),
            "candidate_count": len(filtered),
        }
        return filtered or canonical_docs

    def _extract_curriculum_year_block(self, text: str, year: int, department_name: str) -> str:
        text = text or ""
        mentoring_block = self._extract_mentoring_year_block(text, year)
        if mentoring_block and self._extract_curriculum_courses(mentoring_block):
            return mentoring_block

        starts: list[int] = []
        year_line_pattern = rf"(?:^|\n)\s*{year}\s+(?!학\s*기)"
        starts.extend(match.start() for match in re.finditer(year_line_pattern, text))
        starts.extend(match.start() for match in re.finditer(rf"{year}\s*학년", text))
        if not starts:
            return text

        department_stem = department_name.removesuffix("학과")
        candidates: list[tuple[int, int, str]] = []
        for start in sorted(set(starts)):
            next_years = [
                match.start()
                for next_year in range(year + 1, 5)
                for match in re.finditer(rf"(?:^|\n)\s*{next_year}\s+(?!학\s*기)", text[start + 1 :])
            ]
            end = start + 1 + min(next_years) if next_years else min(len(text), start + 2200)
            block = text[start:end]
            course_count = len(self._extract_curriculum_courses(block))
            department_bonus = 2 if department_stem and department_stem in block else 0
            candidates.append((course_count + department_bonus, -start, block))

        candidates.sort(reverse=True)
        return candidates[0][2] if candidates else text

    def _extract_mentoring_year_block(self, text: str, year: int) -> str | None:
        mentoring_starts = {
            1: "지도교수멘토링Ⅰ",
            2: "지도교수멘토링Ⅲ",
            3: "지도교수멘토링Ⅴ",
            4: "지도교수멘토링Ⅶ",
        }
        mentoring_next = {
            1: "지도교수멘토링Ⅲ",
            2: "지도교수멘토링Ⅴ",
            3: "지도교수멘토링Ⅶ",
        }
        marker = mentoring_starts.get(year)
        if not marker:
            return None
        start = text.find(marker)
        if start < 0:
            return None
        next_marker = mentoring_next.get(year)
        end = text.find(next_marker, start + len(marker)) if next_marker else -1
        if end < 0:
            end = min(len(text), start + 2200)
        return text[start:end]

    def _extract_curriculum_courses(self, text: str) -> list[str]:
        courses: list[str] = []
        seen: set[str] = set()
        pattern = re.compile(r"\b\d{6}\s+(.+?)\s+\d+(?:\.\d+)?\s+\d+\.\d+/\d+\.\d+")
        for match in pattern.finditer(text):
            name = re.sub(r"\s+", " ", match.group(1)).strip(" /")
            if not name or name in seen:
                continue
            seen.add(name)
            courses.append(name)
        for name in self._extract_curriculum_courses_without_codes(text):
            if name in seen:
                continue
            seen.add(name)
            courses.append(name)
        return courses

    def _extract_curriculum_courses_without_codes(self, text: str) -> list[str]:
        courses: list[str] = []
        seen: set[str] = set()
        stopwords = {
            "학년",
            "이수구분",
            "교과목명",
            "학점",
            "시간",
            "이론",
            "실습",
            "공통교양",
            "전공필수",
            "전공선택",
            "계열교양",
            "균형교양",
            "자율교양",
        }

        def add(name: str) -> None:
            clean = re.sub(r"\s+", " ", name).strip(" -|/")
            clean = re.sub(r"^(공통교양|전공필수|전공선택|계열교양|균형교양|자율교양)\s+", "", clean)
            if not clean or clean in stopwords or clean in seen:
                return
            if re.fullmatch(r"[\d.]+", clean):
                return
            if len(clean) < 2:
                return
            seen.add(clean)
            courses.append(clean)

        for line in (text or "").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if "|" in stripped:
                cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                for index, cell in enumerate(cells[:-1]):
                    if re.fullmatch(r"\d+(?:\.\d+)?", cells[index + 1] or ""):
                        add(cell)
                continue

            plain_pattern = re.compile(
                r"([가-힣A-Za-z0-9()·/ⅠⅡⅢⅣⅤⅥⅦⅧ-][가-힣A-Za-z0-9()·/ⅠⅡⅢⅣⅤⅥⅦⅧ\s-]{1,}?)\s+"
                r"\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?){1,2}"
            )
            for match in plain_pattern.finditer(stripped):
                add(match.group(1))
        return courses

    def _postprocess(self, state: PipelineState) -> None:
        state.answer_text = strip_markdown_formatting(state.answer_text)

    def _strip_markdown_formatting(self, text: str) -> str:
        return strip_markdown_formatting(text)

    def _build_success_answer(self, state: PipelineState) -> Answer:
        return Answer(
            question=state.original_query,
            answer=state.answer_text,
            sources=state.selected_docs,
            success=True,
            retrieval_log=state.to_log_dict(),
        )

    def _build_direct_answer(self, state: PipelineState) -> Answer:
        if state.primary_intent == "PROFANITY":
            answer_text = "\ubd80\uc801\uc808\ud55c \ud45c\ud604\uc740 \uc0ac\uc6a9\ud560 \uc218 \uc5c6\uc5b4\uc694."
        else:
            answer_text = (
                "\uc548\ub155\ud558\uc138\uc694. \ub3d9\uc758\ub300\ud559\uad50 \uc815\ubcf4 \uc548\ub0b4\ub97c "
                "\ub3c4\uc640\ub4dc\ub9ac\uace0 \uc788\uc5b4\uc694. \ud559\uc0ac, \uc7a5\ud559, "
                "\uae30\uc219\uc0ac, \ud1b5\ud559\ubc84\uc2a4 \uac19\uc740 \ud559\uad50 \uc815\ubcf4\ub97c "
                "\ubb3c\uc5b4\ubd10 \uc8fc\uc138\uc694."
            )
        state.answer_text = answer_text
        return Answer(
            question=state.original_query,
            answer=answer_text,
            sources=[],
            success=True,
            retrieval_log=state.to_log_dict(),
        )

    def _build_fallback_answer(self, state: PipelineState) -> Answer:
        fallback_text = handle_fallback(
            query=state.original_query,
            error=state.error,
        )

        return Answer(
            question=state.original_query,
            answer=fallback_text,
            sources=[],
            success=False,
            retrieval_log=state.to_log_dict(),
        )

