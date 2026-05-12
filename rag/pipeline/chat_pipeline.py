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
        query_understanding = state.metadata.get("query_understanding", {})
        query_text = (
            query_understanding.get("embedding_query")
            or state.normalized_query
            or state.original_query
        )
        embedder = self._get_embedder()
        state.query_vector = embedder.embed_query(query_text)

    def _retrieve(self, state: PipelineState) -> None:
        request = build_retrieval_request(state)
        state.retrieval_strategy = request.strategy
        state.retrieval_top_k = request.top_k
        state.metadata["retrieval_request"] = request.model_dump()
        state.metadata["retrieval_strategy_log"] = request.log_fields
        state.retrieved_docs = retrieve_documents(
            request=request,
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

