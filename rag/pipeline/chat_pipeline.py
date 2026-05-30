"""RAG pipeline orchestration."""

import json
import os
import re
import time

from rag.pipeline.state import PipelineState
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.preprocess.primary_intent import PrimaryIntentClassifier
from rag.schemas.query import Query
from rag.schemas.answer import Answer

from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request
from rag.retrieval.source_policy import forbidden_source_types_for_family
from rag.retrieval.temporal import validate_temporal_evidence
from rag.retrieval.quality import retrieval_quality_result, set_retrieval_quality_status
from rag.selection.topk_selector import select_topk_with_diagnostics
from rag.selection.context_builder import build_context
from rag.selection.reranker import rerank_documents

from rag.prompt.prompt_builder import build_prompt, build_system_prompt, build_user_message
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
        has_retrieval_constraints = bool(request.filters) or bool(request.ranking_hints)
        allow_filter_relaxation = has_retrieval_constraints and quality.get("reason") in {
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
                "ranking_hints": request.ranking_hints,
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
        return mode in self._csv_env(_DISABLE_FALLBACK_FOR_MODES_ENV_VAR, default=[])

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
                        "ranking_hints": {},
                        "category": None,
                    }
                ),
                "hybrid",
            ),
            "relaxed_filters": (
                "relaxed_filters",
                request.model_copy(update={"filters": {}, "ranking_hints": {}, "category": None}),
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
        if (request.filters or request.ranking_hints) and reason in {"empty_result", "low_top1_score", "low_avg_score", "short_context"}:
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
        return ["original_query_no_rewrite", "vector_only_retry", "relaxed_filters", "increase_top_k", "lexical_only_retry"]

    def _faculty_fallback_order(self) -> list[str]:
        return ["original_query_no_rewrite", "relaxed_filters", "lexical_only_retry", "vector_only_retry"]

    def _max_fallback_attempts(self) -> int:
        try:
            value = int(os.getenv(_MAX_FALLBACK_ATTEMPTS_ENV_VAR, "2"))
        except ValueError:
            return 2
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
        strategy_log = state.metadata.get("retrieval_strategy_log", {})
        hard_filters = strategy_log.get("filters", {}) if isinstance(strategy_log, dict) else {}
        ranking_hints = strategy_log.get("ranking_hints", {}) if isinstance(strategy_log, dict) else {}
        state.reranked_docs = rerank_documents(
            state.retrieved_docs,
            query=state.rewritten_query or state.normalized_query or state.original_query,
            keywords=state.keywords,
            category=state.category,
            filters=hard_filters if isinstance(hard_filters, dict) else {},
            ranking_hints=ranking_hints if isinstance(ranking_hints, dict) else {},
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
        temporal_validation = self._validate_selected_temporal_evidence(state)
        selection_quality["temporal_validation"] = temporal_validation
        state.metadata["selection_quality"] = selection_quality
        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality["selection_quality"] = selection_quality
        state.metadata["citation_trace"] = self._build_citation_trace(state.selected_docs)
        state.context = build_context(state.selected_docs)

    def _validate_selected_temporal_evidence(self, state: PipelineState) -> dict:
        temporal_signals = self._temporal_signals_from_state(state)
        validation = validate_temporal_evidence(state.selected_docs, temporal_signals)
        state.metadata["temporal_signals"] = temporal_signals
        state.metadata["temporal_validation"] = validation
        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality["temporal_signals"] = temporal_signals
            retrieval_quality["temporal_validation"] = validation
            if validation.get("reason") == "missing_temporal_evidence":
                self._set_retrieval_quality_status(retrieval_quality, "missing_temporal_evidence")
        return validation

    def _temporal_signals_from_state(self, state: PipelineState) -> dict:
        strategy_log = state.metadata.get("retrieval_strategy_log", {})
        if not isinstance(strategy_log, dict):
            return {}
        temporal_signals = strategy_log.get("temporal_signals")
        if temporal_signals is None:
            ranking_hints = strategy_log.get("ranking_hints", {})
            if isinstance(ranking_hints, dict):
                temporal_signals = ranking_hints.get("temporal_signals")
        return temporal_signals if isinstance(temporal_signals, dict) else {}

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
        source_type = str((doc.metadata or {}).get("source_type") or "").lower()
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
            if source_type == "cafeteria":
                score += 1.5
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
        if source_type == "cafeteria" and query_type in {"cafeteria_location", "cafeteria_hours"}:
            return False
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

    def _extract_cafeteria_hours(self, content: str) -> str:
        import re
        match = re.search(r"\d{1,2}\s*[시:]\s*[~\-]\s*\d{1,2}\s*[시:]|\d{1,2}~\d{1,2}시", content)
        return match.group(0) if match else ""

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
            "single_selected_heading_mismatch": len(docs) == 1 and not doc_signals[0]["heading_query_match"],
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
        temporal_validation = state.metadata.get("temporal_validation")
        effective_context = state.context
        if (
            isinstance(temporal_validation, dict)
            and temporal_validation.get("needs_validation")
            and not temporal_validation.get("valid")
        ):
            signals = temporal_validation.get("temporal_signals") or {}
            years = signals.get("years") or []
            semesters = signals.get("semesters") or []
            missing = temporal_validation.get("missing") or []
            parts = []
            if years:
                parts.append(f"요청 연도: {', '.join(str(y) for y in years)}")
            if semesters:
                parts.append(f"요청 학기: {', '.join(str(s) for s in semesters)}")
            if missing:
                parts.append(f"문서에서 확인되지 않은 항목: {', '.join(missing)}")
            temporal_mismatch_hint = (
                "temporal_mismatch: " + "; ".join(parts)
                if parts else "temporal_mismatch: 연도/학기 정보 불일치"
            )
            state.metadata["temporal_answer_blocked"] = False
            state.metadata["temporal_mismatch_hint_injected"] = True
            effective_context = (
                f"{temporal_mismatch_hint}\n\n{effective_context}"
                if effective_context
                else temporal_mismatch_hint
            )

        state.prompt = build_prompt(
            query=state.original_query,
            context=effective_context,
        )
        system_prompt = build_system_prompt()
        user_message = build_user_message(
            query=state.original_query,
            context=effective_context,
        )
        state.metadata["answer_generation_input"] = {
            "selected_doc_count": len(state.selected_docs or []),
            "context_chars": len(state.context or ""),
            "prompt_chars": len(state.prompt or ""),
        }
        generated_answer = generate_answer(user_message, system_prompt=system_prompt)
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

    def _query_features(self, state: PipelineState) -> dict:
        query_understanding = state.metadata.get("query_understanding", {})
        if not isinstance(query_understanding, dict):
            return {}
        query_features = query_understanding.get("query_features", {})
        return query_features if isinstance(query_features, dict) else {}

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

