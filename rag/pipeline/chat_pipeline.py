"""RAG chat pipeline orchestration."""

from rag.pipeline.state import PipelineState
from rag.pipeline.preprocessor import QueryPreprocessor
from rag.schemas.query import Query
from rag.schemas.answer import Answer

from rag.retrieval.retriever import retrieve_documents
from rag.selection.topk_selector import select_topk
from rag.selection.context_builder import build_context

from rag.prompt.prompt_builder import build_prompt
from rag.llm.answer_generator import generate_answer

from rag.fallback.fallback.fallback_handler import handle_fallback

from pprint import pprint


class ChatPipeline:
    def __init__(self) -> None:
        self.preprocessor = QueryPreprocessor()

    def run(self, query: Query) -> Answer:
        state = PipelineState.from_query(query.text)

        try:
            # self._preprocess(state)
            self.preprocessor.run(state)
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
        finally:
            pprint(state.to_log_dict())

    # 전처리 단계
    # - 질문 정규화
    # - 키워드 추출
    # - 엔티티 추출 및 카테고리 분류
    # - 질문 재작성
    # def _preprocess(self, state: PipelineState) -> None:
    #     self.preprocessor.run(state)

    def _retrieve(self, state: PipelineState) -> None:
        state.retrieved_docs = retrieve_documents(
            query=state.rewritten_query,
            keywords=state.keywords,
        )

    def _select_and_build_context(self, state: PipelineState) -> None:
        state.selected_docs = select_topk(state.retrieved_docs)
        state.context = build_context(state.selected_docs)

    def _generate(self, state: PipelineState) -> None:
        state.prompt = build_prompt(
            query=state.original_query,
            context=state.context,
        )
        state.answer_text = generate_answer(state.prompt)

    def _postprocess(self, state: PipelineState) -> None:
        # TODO: response validation / polishing
        pass

    def _build_success_answer(self, state: PipelineState) -> Answer:
        return Answer(
            question=state.original_query,
            answer=state.answer_text,
            sources=state.selected_docs,
            success=True,
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
        )

