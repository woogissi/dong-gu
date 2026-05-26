import json
import os
import shutil
import unittest
import uuid
from pathlib import Path
from pprint import pprint
from unittest.mock import Mock, patch

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.retrieval import retriever
from rag.schemas.retrieved_doc import RetrievedDoc


class PipelineStageOutputTest(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = Path.cwd() / ".test_tmp"
        temp_root.mkdir(exist_ok=True)
        self.chunk_dir = temp_root / f"chunks_{uuid.uuid4().hex}"
        self.chunk_dir.mkdir()
        os.environ["RAG_CHUNK_DATA_DIR"] = str(self.chunk_dir)
        os.environ["RAG_USE_DB"] = "0"
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()

        self._write_chunk_file(
            "academic_notice/sample.json",
            [
                {
                    "chunk_id": "notice_1_chunk_1",
                    "doc_id": "notice_1",
                    "title": "수강정정 안내",
                    "content": "수강정정 기간과 신청 방법을 안내합니다.",
                    "source_type": "academic_notice",
                    "source_url": "https://example.com/notice_1",
                    "published_at": "2026-04-10",
                    "department": "학사관리팀",
                },
                {
                    "chunk_id": "notice_2_chunk_1",
                    "doc_id": "notice_2",
                    "title": "기숙사 입사 안내",
                    "content": "기숙사 입사 일정과 준비물을 공지합니다.",
                    "source_type": "dormitory",
                    "source_url": "https://example.com/notice_2",
                    "published_at": "2026-04-11",
                    "department": "생활관",
                },
            ],
        )

    def tearDown(self) -> None:
        retriever._load_chunk_records.cache_clear()
        retriever._load_bm25_index.cache_clear()
        os.environ.pop("RAG_CHUNK_DATA_DIR", None)
        os.environ.pop("RAG_USE_DB", None)
        shutil.rmtree(self.chunk_dir, ignore_errors=True)

    def test_pipeline_stage_outputs(self) -> None:
        fake_embedder = Mock()
        fake_embedder.embed_query.return_value = [0.11, 0.22, 0.33]
        pipeline = ChatPipeline()
        pipeline.embedder = fake_embedder
        state = PipelineState.from_query("수강정정 기간 알려줘")

        pipeline.preprocessor.run(state)
        self._debug_print("after_preprocessor", self._snapshot_after_preprocess(state))

        self.assertEqual(state.original_query, "수강정정 기간 알려줘")
        self.assertTrue(state.normalized_query)
        self.assertTrue(state.keywords)
        self.assertIsInstance(state.entities, dict)
        self.assertIsInstance(state.filters, dict)
        self.assertTrue(state.rewritten_query)
        self.assertIn("query_understanding", state.metadata)

        pipeline._embed_query(state)
        self._debug_print("after_embed_query", self._snapshot_after_embedding(state))

        self.assertEqual(state.query_vector, [0.11, 0.22, 0.33])
        pipeline.embedder.embed_query.assert_called_once_with(
            state.metadata["query_understanding"]["embedding_query"]
        )

        pipeline._retrieve(state)
        self._debug_print("after_retrieve", self._snapshot_after_retrieve(state))

        self.assertEqual(state.retrieval_strategy, "vector")
        self.assertEqual(state.retrieval_top_k, 20)
        self.assertIn("retrieval_request", state.metadata)
        self.assertIn("retrieval_strategy_log", state.metadata)
        self.assertGreaterEqual(len(state.retrieved_docs), 1)
        self.assertEqual(state.retrieved_docs[0].doc_id, "notice_1")
        self.assertEqual(state.retrieved_docs[0].metadata["strategy"], "vector")
        self.assertTrue(state.retrieved_docs[0].metadata["matched_tokens"])

        pipeline._select_and_build_context(state)
        self._debug_print("after_select_and_context", self._snapshot_after_select(state))

        self.assertGreaterEqual(len(state.reranked_docs), 1)
        self.assertGreaterEqual(len(state.selected_docs), 1)
        self.assertIn("rerank_score", state.reranked_docs[0].metadata)
        self.assertIn("rerank_signals", state.reranked_docs[0].metadata)
        self.assertIn("retrieved_candidate_trace", state.metadata)
        self.assertIn("reranked_candidate_trace", state.metadata)
        self.assertIn("selected_candidate_trace", state.metadata)
        self.assertIn("rejected_candidate_trace", state.metadata)
        self.assertIn("source_type", state.metadata["selected_candidate_trace"][0])
        self.assertTrue(state.context)

    def test_generate_records_person_title_rule_as_evidence_before_llm(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("9\ub300 \ucd1d\uc7a5")
        state.metadata["query_understanding"] = {"query_features": {"family": "person_title"}}
        state.selected_docs = [
            RetrievedDoc(
                doc_id="presidents",
                chunk_id="presidents_1",
                title="\uc5ed\ub300\ucd1d\uc7a5 | \ucd1d\uc7a5 | DEU",
                content=(
                    "\uc81c8\ub300 \ucd1d\uc7a5 \uae40\ud314\ub300\n"
                    "\uc7ac\uc784\uae30\uac04: 2010. 3. ~ 2014. 2.\n"
                    "\uc81c9\ub300 \ucd1d\uc7a5 \ud64d\uae38\ub3d9\n"
                    "\uc7ac\uc784\uae30\uac04: 2014. 3. ~ 2018. 2."
                ),
                score=10.0,
                source="https://example.test/presidents",
                metadata={"source_type": "institution"},
            )
        ]
        state.prompt = "LLM prompt should not be used"

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            mocked_generate.return_value = "LLM generated president answer"
            pipeline._generate(state)

        mocked_generate.assert_called_once()
        self.assertEqual(state.answer_text, "LLM generated president answer")
        self.assertIn("[\uad6c\uc870\ud654 \uadfc\uac70]", state.prompt)
        self.assertIn("\ud64d\uae38\ub3d9", state.prompt)
        self.assertEqual(
            state.metadata["person_title_answer_rule"]["answer_type"],
            "president_ordinal",
        )
        self.assertFalse(state.metadata["person_title_answer_rule"]["applied"])
        candidates = state.metadata["rule_answer_candidates"]
        self.assertEqual(candidates[0]["rule"], "person_title_answer")
        self.assertEqual(candidates[0]["decision"], "evidence")
        self.assertEqual(candidates[0]["source_doc_id"], "presidents")
        self.assertEqual(candidates[0]["source_chunk_id"], "presidents_1")
        self.assertEqual(candidates[0]["missing_terms"], [])
        self.assertTrue(candidates[0]["evidence"])

    def test_generate_records_cafeteria_partial_rule_as_evidence_before_llm(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("\uc815\ubcf4\uacf5\ud559\uad00 \uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04")
        state.metadata["query_understanding"] = {"query_features": {"family": "cafeteria"}}
        state.selected_docs = [
            RetrievedDoc(
                doc_id="welfare",
                chunk_id="welfare_1",
                title="\ubcf5\uc9c0\ubb38\ud654\uc2dc\uc124 | \ud3b8\uc758\u00b7\ubcf5\uc9c0 | \ub300\ud559\uc0dd\ud65c",
                content="\uc815\ubcf4\uacf5\ud559\uad00 2\uce35 \ud559\uc0dd\uc2dd\ub2f9, \ud3b8\uc758\uc810, \ud734\uac8c\uc2e4",
                score=10.0,
                source="https://www.deu.ac.kr/www/deu-culture.do",
                metadata={"source_type": "institution"},
            )
        ]
        state.reranked_docs = list(state.selected_docs)
        state.retrieved_docs = list(state.selected_docs)

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            mocked_generate.return_value = "LLM generated cafeteria answer"
            pipeline._generate(state)

        mocked_generate.assert_called_once()
        self.assertEqual(state.answer_text, "LLM generated cafeteria answer")
        self.assertIn("[\uad6c\uc870\ud654 \uadfc\uac70]", state.prompt)
        self.assertIn("missing_terms=operating_hours", state.prompt)
        self.assertNotIn("\uc6b4\uc601\uc2dc\uac04\uc740 \ud655\uc778\ub418\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4", state.answer_text)
        self.assertNotIn("\uc6b4\uc601\uc2dc\uac04\uc740 \ud655\uc778\ub418\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4", state.prompt)
        candidates = state.metadata["rule_answer_candidates"]
        self.assertEqual(candidates[0]["rule"], "cafeteria_answer")
        self.assertEqual(candidates[0]["decision"], "evidence")
        self.assertEqual(candidates[0]["source_doc_id"], "welfare")
        self.assertEqual(candidates[0]["source_chunk_id"], "welfare_1")
        self.assertEqual(candidates[0]["missing_terms"], ["operating_hours"])
        self.assertLess(candidates[0]["confidence"], 0.7)

    def test_generate_records_navigation_rule_as_evidence_before_llm(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("\ub3d9\uc758\ub300 \uc870\uc9c1\ub3c4")
        state.selected_docs = [
            RetrievedDoc(
                doc_id="org",
                chunk_id="org_1",
                title="\uc870\uc9c1\ub3c4",
                content="\uc870\uc9c1\ub3c4 \uc774\ubbf8\uc9c0 \ubc0f \uacc4\uce35 \uc548\ub0b4",
                score=10.0,
                source="https://www.deu.ac.kr/www/deu-organization.do",
                metadata={"source_type": "institution"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            mocked_generate.return_value = "LLM generated organization answer"
            pipeline._generate(state)

        mocked_generate.assert_called_once()
        self.assertEqual(state.answer_text, "LLM generated organization answer")
        self.assertIn("[\uad6c\uc870\ud654 \uadfc\uac70]", state.prompt)
        candidates = state.metadata["rule_answer_candidates"]
        self.assertEqual(candidates[0]["rule"], "navigation_fallback_answer")
        self.assertEqual(candidates[0]["decision"], "evidence")
        self.assertEqual(candidates[0]["source_doc_id"], "org")

        lost_state = PipelineState.from_query("\ubd84\uc2e4\ubb3c \uc13c\ud130 \uc5b4\ub514\uc57c")
        lost_state.selected_docs = [
            RetrievedDoc(
                doc_id="lost",
                chunk_id="lost_1",
                title="\ubd84\uc2e4\ubb3c\uc13c\ud130 \uac8c\uc2dc\ud310\ubaa9\ub85d",
                content="\ubd84\uc2e4\ubb3c \uac8c\uc2dc\ud310",
                score=10.0,
                source="https://www.deu.ac.kr/www/deu-lostfound.do?mode=list",
                metadata={"source_type": "lostfound"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            mocked_generate.return_value = "LLM generated lostfound answer"
            pipeline._generate(lost_state)

        mocked_generate.assert_called_once()
        self.assertEqual(lost_state.answer_text, "LLM generated lostfound answer")
        self.assertIn("[\uad6c\uc870\ud654 \uadfc\uac70]", lost_state.prompt)
        lost_candidates = lost_state.metadata["rule_answer_candidates"]
        self.assertEqual(lost_candidates[0]["rule"], "navigation_fallback_answer")
        self.assertEqual(lost_candidates[0]["decision"], "evidence")
        self.assertEqual(lost_candidates[0]["source_doc_id"], "lost")

    def test_generate_keeps_faculty_rule_final_when_gate_passes(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("\uc624\uc6d0\ud0dc \uad50\uc218 \uc815\ubcf4")
        state.keywords = ["\uad50\uc218", "\uc624\uc6d0\ud0dc", "\uc815\ubcf4"]
        state.selected_docs = [
            RetrievedDoc(
                doc_id="energy",
                chunk_id="energy_1",
                title="\uad50\uc218\uc18c\uac1c \uac8c\uc2dc\ud310\ubaa9\ub85d | \ucca8\ub2e8\uc5d0\ub108\uc9c0\uacf5\ud559\uacfc",
                content=(
                    "\uc624\uc6d0\ud0dc \uad50\uc218\ub2d8\n"
                    "\uae30\ub2a5\uc131 \uace0\ubd84\uc790\ubcf5\ud569\uc7ac\ub8cc\n"
                    "\uc5f0\uad6c\uc2e4\n\uacf5\ud559\uad00 711\ud638\n"
                    "\uc5f0\ub77d\ucc98\n051-890-1234\n"
                    "E-MAIL\nowt@deu.ac.kr"
                ),
                score=10.0,
                source="https://energy.deu.ac.kr/energy/sub02.do",
                metadata={"source_type": "department"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            pipeline._generate(state)

        mocked_generate.assert_not_called()
        self.assertIn("\uc624\uc6d0\ud0dc \uad50\uc218\ub2d8 \uc815\ubcf4\uc785\ub2c8\ub2e4", state.answer_text)
        candidate = state.metadata["rule_answer_candidates"][0]
        self.assertEqual(candidate["rule"], "faculty_answer")
        self.assertEqual(candidate["decision"], "final")
        self.assertEqual(candidate["missing_terms"], [])

    def test_generate_keeps_department_faculty_list_final_when_gate_passes(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("\ucef4\ud4e8\ud130\uacf5\ud559\uacfc \uad50\uc218 \ubaa9\ub85d")
        state.selected_docs = [
            RetrievedDoc(
                doc_id="computer",
                chunk_id="computer_1",
                title="\uad50\uc218\uc18c\uac1c \uac8c\uc2dc\ud310\ubaa9\ub85d | \ucef4\ud4e8\ud130\uacf5\ud559\uacfc",
                content=(
                    "\ubcc0\uc2b9\uaddc \uad50\uc218\ub2d8\nAIoT\n\uc5f0\uad6c\uc2e4\n\uc815\ubcf4\uacf5\ud559\uad00 801\ud638\nE-MAIL\nsg0919@deu.ac.kr\n"
                    "\ucd5c\ubcd1\uc724 \uad50\uc218\ub2d8\n\uc815\ubcf4\ubcf4\ud638\n\uc5f0\uad6c\uc2e4\n\uc815\ubcf4\uacf5\ud559\uad00 802\ud638\nE-MAIL\nbychoi@deu.ac.kr"
                ),
                score=10.0,
                source="https://swcc.deu.ac.kr/computer/sub02.do",
                metadata={"source_type": "department"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            pipeline._generate(state)

        mocked_generate.assert_not_called()
        self.assertIn("\ucef4\ud4e8\ud130\uacf5\ud559\uacfc \uad50\uc218 \ubaa9\ub85d\uc785\ub2c8\ub2e4", state.answer_text)
        candidate = state.metadata["rule_answer_candidates"][0]
        self.assertEqual(candidate["rule"], "department_faculty_list_answer")
        self.assertEqual(candidate["decision"], "final")
        self.assertEqual(candidate["missing_terms"], [])

    def test_generate_keeps_curriculum_and_schedule_final_when_gates_pass(self) -> None:
        pipeline = ChatPipeline()
        curriculum_state = PipelineState.from_query("\uac8c\uc784\uacf5\ud559\uacfc 3\ud559\ub144 \uc774\uc218\ud45c")
        curriculum_state.metadata["query_understanding"] = {"query_features": {"family": "department_curriculum"}}
        curriculum_state.keywords = ["\uac8c\uc784\uacf5\ud559\uacfc", "3\ud559\ub144", "\uc774\uc218\ud45c"]
        curriculum_state.selected_docs = [
            RetrievedDoc(
                doc_id="game",
                chunk_id="game_003",
                title="\uc774\uc218\ud45c | \uad50\uc721\uacfc\uc815 | \uac8c\uc784\uacf5\ud559\uacfc",
                content="3 \uac8c\uc784\uacf5\ud559\uacfc 222222 \uac8c\uc784\uadf8\ub798\ud53d\uc2a4 3 2.00/1.00 333333 \uac8c\uc784\uc778\uacf5\uc9c0\ub2a5 3 3.00/0.00",
                score=10.0,
                source="https://game.deu.ac.kr/game/curriculum.do",
                metadata={"source_type": "department"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            pipeline._generate(curriculum_state)

        mocked_generate.assert_not_called()
        self.assertIn("\uac8c\uc784\uadf8\ub798\ud53d\uc2a4", curriculum_state.answer_text)
        self.assertEqual(curriculum_state.metadata["rule_answer_candidates"][0]["decision"], "final")

        schedule_state = PipelineState.from_query("26\ub144 1\ud559\uae30 \ubcf4\uac15\uc77c\uc815")
        schedule_state.metadata["query_understanding"] = {"query_features": {"family": "academic_schedule"}}
        schedule_state.selected_docs = [
            RetrievedDoc(
                doc_id="schedule",
                chunk_id="schedule_1",
                title="\ud559\uc0ac\uc77c\uc815 | \ud559\uc0ac\uc815\ubcf4",
                content="2026\ub144 1\ud559\uae30\n5\uc6d4 1\uc77c | \uc9c0\uc815\ubcf4\uac15\uc77c \uc218\uc5c5 \uc9c4\ud589\n6\uc6d4 8\uc77c | \uc9c0\uc815\ubcf4\uac15\uc77c \uc218\uc5c5 \uc9c4\ud589",
                score=10.0,
                source="https://www.deu.ac.kr/www/schedule.do",
                metadata={"source_type": "institution"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            pipeline._generate(schedule_state)

        mocked_generate.assert_not_called()
        self.assertIn("\uc9c0\uc815\ubcf4\uac15\uc77c", schedule_state.answer_text)
        self.assertEqual(schedule_state.metadata["rule_answer_candidates"][0]["decision"], "final")

    def test_generate_downgrades_curriculum_rule_without_year_to_evidence(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("\uac8c\uc784\uacf5\ud559\uacfc \uc774\uc218\ud45c")
        state.metadata["query_understanding"] = {"query_features": {"family": "department_curriculum"}}
        state.keywords = ["\uac8c\uc784\uacf5\ud559\uacfc", "\uc774\uc218\ud45c"]
        state.selected_docs = [
            RetrievedDoc(
                doc_id="game",
                chunk_id="game_001",
                title="\uc774\uc218\ud45c | \uad50\uc721\uacfc\uc815 | \uac8c\uc784\uacf5\ud559\uacfc",
                content="\uac8c\uc784\uacf5\ud559\uacfc \uc774\uc218\ud45c \uc548\ub0b4",
                score=10.0,
                source="https://game.deu.ac.kr/game/curriculum.do",
                metadata={"source_type": "department"},
            )
        ]

        with patch("rag.pipeline.chat_pipeline.generate_answer") as mocked_generate:
            mocked_generate.return_value = "LLM generated curriculum answer"
            pipeline._generate(state)

        mocked_generate.assert_called_once()
        self.assertEqual(state.answer_text, "LLM generated curriculum answer")
        self.assertIn("[\uad6c\uc870\ud654 \uadfc\uac70]", state.prompt)
        candidate = state.metadata["rule_answer_candidates"][0]
        self.assertEqual(candidate["rule"], "department_curriculum_answer")
        self.assertEqual(candidate["decision"], "evidence")
        self.assertIn("curriculum_year", candidate["missing_terms"])
        self.assertIn("curriculum_courses", candidate["missing_terms"])

    def _write_chunk_file(self, relative_path: str, payload: list[dict]) -> None:
        file_path = self.chunk_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _snapshot_after_preprocess(self, state: PipelineState) -> dict[str, object]:
        return {
            "original_query": state.original_query,
            "normalized_query": state.normalized_query,
            "keywords": state.keywords,
            "entities": state.entities,
            "filters": state.filters,
            "category": state.category,
            "rewritten_queries": state.rewritten_queries,
            "rewritten_query": state.rewritten_query,
            "metadata": state.metadata.get("query_understanding"),
        }

    def _snapshot_after_embedding(self, state: PipelineState) -> dict[str, object]:
        return {
            "query_for_embedding": state.rewritten_query or state.normalized_query or state.original_query,
            "embedding_query": state.metadata.get("query_understanding", {}).get("embedding_query"),
            "query_vector": state.query_vector,
            "vector_size": len(state.query_vector),
        }

    def _snapshot_after_retrieve(self, state: PipelineState) -> dict[str, object]:
        return {
            "retrieval_strategy": state.retrieval_strategy,
            "retrieval_top_k": state.retrieval_top_k,
            "retrieval_request": state.metadata.get("retrieval_request"),
            "retrieval_strategy_log": state.metadata.get("retrieval_strategy_log"),
            "retrieved_docs": [
                {
                    "doc_id": doc.doc_id,
                    "chunk_id": doc.chunk_id,
                    "title": doc.title,
                    "score": doc.score,
                    "category": doc.category,
                    "metadata": doc.metadata,
                }
                for doc in state.retrieved_docs
            ],
        }

    def _snapshot_after_select(self, state: PipelineState) -> dict[str, object]:
        return {
            "reranked_docs": [
                {
                    "doc_id": doc.doc_id,
                    "chunk_id": doc.chunk_id,
                    "score": doc.score,
                    "rerank_signals": doc.metadata.get("rerank_signals"),
                }
                for doc in state.reranked_docs
            ],
            "selected_docs": [doc.doc_id for doc in state.selected_docs],
            "context": state.context,
        }

    def _debug_print(self, label: str, payload: object) -> None:
        print(f"\n[{self.__class__.__name__}] {label}")
        pprint(payload, sort_dicts=False)


if __name__ == "__main__":
    unittest.main()
