"""
입력 질문 받기
piplineState 생성
전처리 -> 검색 -> 선택 -> 프롬프트 -> 생성 -> 검증
순서 호출
각 단계 결과 state에 저장
실패시 fallback
"""
#rag 흐름 제어

from rag.pipeline.state import PipelineState
from rag.schemas.query import Query
from rag.schemas.answer import Answer
from rag.schemas.retrieved_doc import RetrievedDoc

from rag.preprocess.normalizer import normalize_query
from rag.preprocess.keyword_extractor import extract_keywords
from rag.preprocess.query_rewriter import rewrite_query

from rag.retrieval.retriever import retrieve_documents
from rag.selection.topk_selector import select_topk
from rag.selection.context_builder import build_context

from rag.prompt.prompt_builder import build_prompt
from rag.llm.answer_generator import generate_answer

from rag.fallback.fallback_handler import handle_fallback


class ChatPipeline:
    def run(self, query: Query) -> Answer:
        state = PipelineState.from_query(query.text)

        try:
            self._preprocess(state) #전처리 일반화, 추출, 재작성 수행
            self._retrieve(state)
            self._select_and_build_context(state)
            self._generate(state)
            self._postprocess(state)

            return self._build_success_answer(state)

        except Exception as e:
            state.error = str(e)
            return self._build_fallback_answer(state)

    def _preprocess(self, state: PipelineState) -> None:
        state.normalized_query = normalize_query(state.original_query)
        state.keywords = extract_keywords(state.normalized_query)
        state.rewritten_query = rewrite_query(
            query=state.normalized_query,
            keywords=state.keywords,
        )

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
        # 나중에 검증/후처리 로직 추가
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