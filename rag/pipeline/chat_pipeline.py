"""RAG pipeline orchestration."""

from rag.pipeline.state import PipelineState
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.schemas.query import Query
from rag.schemas.answer import Answer

from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request
from rag.selection.topk_selector import select_topk
from rag.selection.context_builder import build_context
from rag.selection.reranker import rerank_documents

from rag.prompt.prompt_builder import build_prompt
from rag.llm.answer_generator import generate_answer

from rag.fallback.fallback_handler import handle_fallback

from rag.embedding.koe5_embedder import KoE5Embedder

from pprint import pprint
from threading import Lock, Thread
from rag.utils.demo_logger import demo_log, preview_text, summarize_docs


class NoRetrievalResultsError(Exception):
    pass


class ChatPipeline:
    def __init__(self) -> None:
        self.preprocessor = QueryPreprocessor()
        self.embedder: KoE5Embedder | None = None
        self.embedder_lock = Lock()
        self.last_state: PipelineState | None = None
        # retriever: Retriever = None,
        # generator: AnswerGenerator = None 확장

    def run(self, query: Query) -> Answer:
        state = PipelineState.from_query(query.text)
        self.last_state = state

        try:
            self.preprocessor.run(state)
            self._log_preprocess(state)
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
            demo_log(
                "Pipeline fallback triggered",
                {
                    "error": state.error,
                    "retrieved_doc_count": len(state.retrieved_docs),
                },
            )
            return self._build_fallback_answer(state)


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
        """서버 시작 시 임베딩 모델 로드를 백그라운드로 시작합니다."""
        print("[ChatPipeline] Starting embedder initialization in background...")
        Thread(target=self._get_embedder, daemon=True).start()


    def _embed_query(self, state: PipelineState) -> None:
        # 쿼리 텍스트를 임베딩하여 벡터 생성
        query_text = state.rewritten_query or state.normalized_query or state.original_query
        embedder = self._get_embedder()
        state.query_vector = embedder.embed_query(query_text)
        demo_log(
            "2-1. Query embedding created",
            {
                "vector_size": len(state.query_vector),
            },
        )

    def _retrieve(self, state: PipelineState) -> None:
        request = build_retrieval_request(state)
        state.retrieval_strategy = request.strategy
        state.retrieval_top_k = request.top_k
        state.metadata["retrieval_request"] = request.model_dump()
        state.metadata["retrieval_strategy_log"] = request.log_fields
        demo_log(
            "3. Retrieval strategy selected",
            {
                "strategy": request.strategy,
                "top_k": request.top_k,
                "query": preview_text(request.query, max_length=180),
                "keyword_count": len(request.keywords),
                "category": request.category,
                "filter_fields": list(request.filters.keys()),
            },
        )
        state.retrieved_docs = retrieve_documents(
            request=request,
        )
        demo_log(
            "3-1. Retrieved documents",
            {
                "retrieved_doc_count": len(state.retrieved_docs),
                "top_documents": summarize_docs(state.retrieved_docs, limit=3),
            },
        )
        if not state.retrieved_docs:
            state.fallback_used = True
            state.metadata["no_retrieval_results"] = {
                "query": request.query,
                "keywords": request.keywords,
                "filters": request.filters,
                "fallback_triggers": [*request.fallback_triggers, "no_retrieval_results"],
            }
            raise NoRetrievalResultsError("관련 문서를 찾지 못했습니다.")

    def _select_and_build_context(self, state: PipelineState) -> None:
        state.reranked_docs = rerank_documents(
            state.retrieved_docs,
            query=state.rewritten_query or state.normalized_query or state.original_query,
            keywords=state.keywords,
            category=state.category,
            filters=state.filters,
        )
        state.selected_docs = select_topk(state.reranked_docs or state.retrieved_docs)
        state.context = build_context(state.selected_docs)
        demo_log(
            "3-2. Reranked and selected documents",
            {
                "reranked_doc_count": len(state.reranked_docs),
                "selected_doc_count": len(state.selected_docs),
                "selected_top_documents": summarize_docs(state.selected_docs, limit=3),
            },
        )

    def _generate(self, state: PipelineState) -> None:
        state.prompt = build_prompt(
            query=state.original_query,
            context=state.context,
        )
        demo_log(
            "4. Prompt generated",
            {
                "prompt_length": len(state.prompt),
                "selected_doc_count": len(state.selected_docs),
                "prompt_preview": preview_text(state.prompt, max_length=350),
            },
        )
        state.answer_text = generate_answer(state.prompt)
        demo_log(
            "5. LLM answer generated",
            {
                "answer_length": len(state.answer_text),
                "answer_preview": preview_text(state.answer_text, max_length=500),
            },
        )

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

    def _build_fallback_answer(self, state: PipelineState) -> Answer:
        fallback_text = handle_fallback(
            query=state.original_query,
            error=state.error,
        )
        demo_log(
            "5. Fallback answer generated",
            {
                "error": state.error,
                "answer_preview": preview_text(fallback_text, max_length=500),
            },
        )

        return Answer(
            question=state.original_query,
            answer=fallback_text,
            sources=[],
            success=False,
            retrieval_log=state.to_log_dict(),
        )

    def _log_preprocess(self, state: PipelineState) -> None:
        demo_log(
            "2. Query preprocessing completed",
            {
                "original_query": preview_text(state.original_query, max_length=180),
                "normalized_query": preview_text(state.normalized_query, max_length=180),
                "keywords": state.keywords[:5],
                "keyword_count": len(state.keywords),
                "category": state.category,
                "rewritten_query": preview_text(state.rewritten_query, max_length=160),
            },
        )

