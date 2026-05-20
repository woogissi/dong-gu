"""RAG pipeline orchestration."""

import os

from rag.pipeline.state import PipelineState
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.preprocess.primary_intent import PrimaryIntentClassifier
from rag.schemas.query import Query
from rag.schemas.answer import Answer

from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request
from rag.selection.topk_selector import select_topk_with_diagnostics
from rag.selection.context_builder import build_context
from rag.selection.reranker import rerank_documents

from rag.prompt.prompt_builder import build_prompt
from rag.llm.answer_generator import generate_answer

from rag.fallback.fallback_handler import handle_fallback

from rag.embedding.koe5_embedder import KoE5Embedder

from pprint import pprint
from threading import Lock


_RETRIEVAL_MODE_ENV_VAR = "RETRIEVAL_MODE"
_MIN_TOP1_SCORE_ENV_VAR = "RETRIEVAL_MIN_TOP1_SCORE"
_MIN_AVG_TOPK_SCORE_ENV_VAR = "RETRIEVAL_MIN_AVG_TOPK_SCORE"
_MIN_CONTEXT_CHARS_ENV_VAR = "RETRIEVAL_MIN_CONTEXT_CHARS"
_MAX_DUPLICATE_DOC_RATIO_ENV_VAR = "RETRIEVAL_MAX_DUPLICATE_DOC_RATIO"
_MAX_TOP_NOISE_SCORE_ENV_VAR = "RETRIEVAL_MAX_TOP_NOISE_SCORE"
_MIN_TOP_STRONG_MATCH_ENV_VAR = "RETRIEVAL_MIN_TOP_STRONG_MATCH"
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
        state = PipelineState.from_query(query.text)
        self.last_state = state

        try:
            self._classify_primary_intent(state)
            if state.primary_intent != "INFO":
                state.success = True
                state.error = ""
                return self._build_direct_answer(state)

            self.preprocessor.run(state)
            self._embed_query(state)
            self._retrieve(state)
            self._select_and_build_context(state)
            self._generate(state)
            self._postprocess(state)
            state.success = True
            state.error = ""
            return self._build_success_answer(state)
        except Exception as e:
            state.success = False
            state.error = str(e)
            state.fallback_used = True
            return self._build_fallback_answer(state)

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
        effective_strategy = self._effective_retrieval_strategy(request.strategy)
        state.retrieval_strategy = effective_strategy
        state.retrieval_top_k = request.top_k
        retrieval_request_log = request.model_dump(exclude={"query_vector"})
        retrieval_request_log["query_vector_size"] = len(request.query_vector or [])
        retrieval_request_log["effective_strategy"] = effective_strategy
        state.metadata["retrieval_request"] = retrieval_request_log
        state.metadata["retrieval_strategy_log"] = {**request.log_fields, "effective_strategy": effective_strategy}
        branch_log = self._collect_branch_candidates(request)
        if branch_log:
            state.metadata["retrieval_branch_candidates"] = branch_log
        state.retrieved_docs = retrieve_documents(
            request=request,
        )
        quality = self._evaluate_retrieval_quality(state.retrieved_docs, request.top_k)
        state.metadata["retrieval_quality"] = quality
        if not quality["ok"]:
            fallback_docs, fallback_log = self._fallback_retrieve(request, quality["reason"])
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
            raise NoRetrievalResultsError("관련 문서를 찾지 못했습니다.")

    def _effective_retrieval_strategy(self, request_strategy: str) -> str:
        configured_mode = os.getenv(_RETRIEVAL_MODE_ENV_VAR, "").strip().lower()
        if configured_mode in {"lexical", "vector", "hybrid"}:
            return configured_mode
        if request_strategy == "dense":
            return "vector"
        return "hybrid" if request_strategy == "lexical" else request_strategy

    def _evaluate_retrieval_quality(self, docs: list, top_k: int) -> dict:
        if not docs:
            return {"ok": False, "reason": "empty_result"}
        top_docs = docs[: max(top_k or 1, 1)]
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
        elif exact_or_title_match_count == 0 and top_strong_match < self._float_env(_MIN_TOP_STRONG_MATCH_ENV_VAR, 0.05):
            reason = "no_exact_or_strong_keyword_match"
        else:
            reason = ""

        return {
            "ok": not reason,
            "reason": reason,
            "top1_score": top1_score,
            "avg_topk_score": avg_topk_score,
            "context_chars": context_chars,
            "duplicate_doc_ratio": duplicate_ratio,
            "top_noise_score": max(top_noise, top_doc_noise),
            "top_strong_term_match": top_strong_match,
            "exact_or_title_match_count": exact_or_title_match_count,
        }

    def _fallback_retrieve(self, request, reason: str) -> tuple[list, dict]:
        original_query = ""
        variants = list(request.query_variants or [])
        if variants:
            original_query = variants[-1]
        attempts = [
            (
                "original_query_no_rewrite",
                request.model_copy(
                    update={
                        "query": original_query or request.query,
                        "query_variants": [original_query or request.query],
                        "filters": {},
                        "category": None,
                    }
                ),
            ),
            ("relaxed_filters", request.model_copy(update={"filters": {}, "category": None})),
            ("increase_top_k", request.model_copy(update={"top_k": max((request.top_k or 10) * 2, 20)})),
            ("lexical_only_retry", request),
            ("vector_only_retry", request),
        ]
        tried = []
        for name, fallback_request in attempts:
            mode = "lexical" if name == "lexical_only_retry" else "vector" if name == "vector_only_retry" else "hybrid"
            docs = self._retrieve_with_mode(fallback_request, mode)
            quality = self._evaluate_retrieval_quality(docs, fallback_request.top_k)
            tried.append({"strategy": name, "mode": mode, "count": len(docs), "quality": quality})
            if docs and quality["ok"]:
                return docs, {"used": True, "fallback_reason": reason, "selected_strategy": name, "attempts": tried}
        return [], {"used": False, "fallback_reason": reason, "attempts": tried}

    def _collect_branch_candidates(self, request) -> dict:
        if os.getenv("RAG_LOG_BRANCH_CANDIDATES", "1").strip().lower() in {"0", "false", "off"}:
            return {}
        branches = {}
        for name, mode in (("lexical", "lexical"), ("vector", "vector")):
            docs = self._retrieve_with_mode(request, mode)[:5]
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
            "source_type": metadata.get("source_type"),
            "section_type": metadata.get("section_type"),
        }

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

    def _retrieve_with_mode(self, request, mode: str) -> list:
        previous_mode = os.getenv(_RETRIEVAL_MODE_ENV_VAR)
        os.environ[_RETRIEVAL_MODE_ENV_VAR] = mode
        try:
            return retrieve_documents(request=request)
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
        selection_result = select_topk_with_diagnostics(state.reranked_docs or state.retrieved_docs)
        state.selected_docs = selection_result["selected"]
        state.metadata["selection_diagnostics"] = selection_result
        state.metadata["rerank_comparison"] = self._build_rerank_comparison(state.retrieved_docs, state.reranked_docs, state.selected_docs)
        selection_quality = self._evaluate_selection_quality(state.selected_docs)
        state.metadata["selection_quality"] = selection_quality
        retrieval_quality = state.metadata.get("retrieval_quality")
        if isinstance(retrieval_quality, dict):
            retrieval_quality["selection_quality"] = selection_quality
        state.metadata["citation_trace"] = self._build_citation_trace(state.selected_docs)
        state.context = build_context(state.selected_docs)

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
        state.prompt = build_prompt(
            query=state.original_query,
            context=state.context,
        )
        state.answer_text = generate_answer(state.prompt)

    def _postprocess(self, state: PipelineState) -> None:
        # : response validation / polishing
        pass

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

