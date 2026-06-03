import unittest
from unittest.mock import patch

from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.pipeline.state import PipelineState
from rag.preprocess.query_features import extract_query_features, sanitize_filters
from rag.preprocess.normalizer import normalize_query
from rag.retrieval.retriever import merge_retrieval_candidates
from rag.retrieval.canonical_source import canonical_notice_metadata
from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.context_builder import build_context, build_llm_context
from rag.selection.reranker import rerank_documents
from rag.selection.topk_selector import select_topk_with_diagnostics


class RagQualityFixTest(unittest.TestCase):
    def test_preprocessor_preserves_building_and_curriculum_terms(self) -> None:
        state = PipelineState.from_query("컴퓨터공학과 2학년 전공필수 과목")

        QueryPreprocessor().run(state)

        features = state.metadata["query_understanding"]["query_features"]
        self.assertEqual(features["family"], "department_curriculum")
        self.assertIn("컴퓨터공학과", features["protected_terms"])
        self.assertIn("2학년", features["protected_terms"])
        self.assertIn("전공필수", state.rewritten_query)
        self.assertIn("컴퓨터공학과", " ".join(state.rewritten_queries))

    def test_query_features_classifies_building_location(self) -> None:
        features = extract_query_features("정보공학관 2층에 뭐 있어", [])

        self.assertEqual(features.family, "building_location")
        self.assertIn("정보공학관", features.protected_terms)
        self.assertIn("2층", features.protected_terms)
        self.assertIn("정보공학관", features.required_terms)

    def test_query_features_classifies_verified_failure_families(self) -> None:
        self.assertEqual(extract_query_features("26년 1학기 보강일정", []).family, "academic_schedule")
        self.assertEqual(extract_query_features("수강신청 기간 알려줘", []).domain, "course")
        self.assertEqual(extract_query_features("국가장학금 신청 기간 알려줘", []).domain, "scholarship")

    def test_normalizer_corrects_dongwi_typo(self) -> None:
        self.assertEqual(normalize_query("동위대학교 위치 알려줘"), "동의대 위치 알려줘")

    def test_sanitize_filters_drops_invalid_department_facets(self) -> None:
        sanitized, dropped = sanitize_filters({"department": ["학과사무실", "컴퓨터공학과"]})

        self.assertEqual(sanitized, {"department": ["컴퓨터공학과"]})
        self.assertEqual(dropped[0]["reason"], "invalid_department_facet")

    def test_reranker_prefers_building_evidence_over_curriculum_attachment(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="curriculum",
                chunk_id="curriculum_1",
                title="2026학년도 교육과정",
                content="교양과정 전공 과목 학점 안내",
                score=10.0,
                metadata={"section_type": "attachment", "source_type": "academic_notice"},
            ),
            RetrievedDoc(
                doc_id="computer_office",
                chunk_id="computer_office_1",
                title="학과사무실 위치 및 연락처 | 컴퓨터공학과",
                content="컴퓨터공학과는 정보공학관(교내 건물 번호 23번) 8층에 있습니다.",
                score=4.0,
                metadata={"section_type": "body", "source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="정보공학관은 몇번 건물?",
            keywords=["정보공학관", "건물번호"],
        )

        self.assertEqual(reranked[0].doc_id, "computer_office")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["required_entity_match"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_reranker_prefers_verified_expected_documents(self) -> None:
        cases = [
            (
                "26년 1학기 보강일정",
                [
                    self._doc("scholarship", "2026년 1학기 푸른등대 기부장학금 신규장학생 선발 안내", "장학금 신청 안내", 9.0, "scholarship"),
                    self._doc("schedule", "학사일정 | 학사정보 | 대학생활", "5월 학사일정과 보강일정 안내", 4.0, "institution"),
                ],
                "schedule",
            ),
            (
                "동의대학교 위치",
                [
                    self._doc("job", "동의대학교 교수학습개발센터 학습컨설턴트 모집 안내", "채용 공고", 9.0, "job"),
                    self._doc("gaya", "가야 캠퍼스 | 찾아오시는 길 | 캠퍼스안내 | DEU", "부산광역시 부산진구 엄광로 176", 4.0, "institution"),
                ],
                "gaya",
            ),
            (
                "컴퓨터공학과 이수표 정보",
                [
                    self._doc("lab", "컴퓨터 시스템 실습실 | 실습실 | 컴퓨터공학과", "실습실 위치 안내", 9.0, "department"),
                    self._doc("curriculum", "이수표 | 교육과정 | 컴퓨터공학과", "컴퓨터공학과 전공필수 교육과정 이수표", 4.0, "department"),
                ],
                "curriculum",
            ),
            (
                "국가장학금 신청 기간 알려줘",
                [
                    self._doc("other", "2026 강원랜드 멘토링 장학 대학생 멘토 모집 안내", "장학금 모집 안내", 9.0, "scholarship"),
                    self._doc("national", "[필독] 2026-2학기 국가장학금 1차 신청기간 안내(5/22~6/22)", "국가장학금 신청 기간 안내", 4.0, "scholarship"),
                ],
                "national",
            ),
            (
                "동의대 7대 총장 정보",
                [
                    self._doc("job", "동의대학교 학생상담센터 객원상담원 모집", "채용 공고", 9.0, "job"),
                    self._doc("presidents", "역대총장 | 총장 | DEU", "동의대학교 7대 총장 정보", 4.0, "institution"),
                ],
                "presidents",
            ),
        ]

        for query, docs, expected_doc_id in cases:
            with self.subTest(query=query):
                reranked = rerank_documents(docs, query=query, keywords=[])
                self.assertEqual(reranked[0].doc_id, expected_doc_id)

    def test_reranker_prefers_canonical_course_registration_source(self) -> None:
        docs = [
            self._doc(
                "department_copy",
                "2026학년도 1학기 수강신청 안내",
                "수강신청 기간 안내",
                9.0,
                "department",
                source_url="https://computer.deu.ac.kr/computer/sub06_03.do?mode=view",
            ),
            self._doc(
                "canonical",
                "2026학년도 1학기 수강신청 안내 | 학사공지",
                "수강신청 기간 안내",
                7.0,
                "academic_notice",
                source_url="https://www.deu.ac.kr/www/boardview/12",
            ),
        ]

        reranked = rerank_documents(docs, query="수강신청 기간 알려줘", keywords=[])

        self.assertEqual(reranked[0].doc_id, "canonical")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["canonical_source_priority"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["canonical_source_priority"], 0)

    def test_canonical_notice_metadata_groups_department_copy(self) -> None:
        central = canonical_notice_metadata(
            {
                "title": "2026학년도 1학기 수강신청 안내",
                "source_url": "https://www.deu.ac.kr/www/deu-notice.do?articleNo=1",
                "source_type": "academic_notice",
            }
        )
        department = canonical_notice_metadata(
            {
                "title": "[안내] 2026-1학기 수강신청 안내",
                "source_url": "https://computer.deu.ac.kr/computer/sub06_03.do?articleNo=2&mode=view",
                "source_type": "department",
            }
        )

        self.assertEqual(central["canonical_notice_family"], "course_registration")
        self.assertTrue(central["is_canonical_notice"])
        self.assertEqual(department["duplicate_kind"], "department_copy")
        self.assertEqual(central["canonical_group"], department["canonical_group"])

    def test_canonical_selected_context_excludes_department_copies(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("수강신청 기간 알려줘")
        docs = [
            self._doc(
                "dept",
                "2026학년도 1학기 수강신청 안내",
                "수강신청 안내",
                9.0,
                "department",
            ),
            self._doc(
                "central",
                "2026학년도 1학기 수강신청 안내 | 학사공지",
                "수강신청 안내",
                7.0,
                "academic_notice",
                source_url="https://www.deu.ac.kr/www/deu-notice.do?articleNo=1",
            ).model_copy(
                update={
                    "metadata": {
                        "source_type": "academic_notice",
                        "is_canonical_notice": True,
                        "canonical_notice_family": "course_registration",
                    }
                }
            ),
        ]

        filtered = pipeline._filter_canonical_notice_docs(state, docs)

        self.assertEqual([doc.doc_id for doc in filtered], ["central"])

    def test_pipeline_defaults_slow_exact_families_to_vector(self) -> None:
        pipeline = ChatPipeline()

        class Request:
            strategy = "lexical"
            log_fields = {"query_family": "course_registration"}

        self.assertEqual(pipeline._effective_retrieval_strategy(Request()), "vector")

    def test_newly_added_vector_only_families(self) -> None:
        # 평가 결과 기반으로 추가된 패밀리들이 vector 전략을 반환하는지 확인한다.
        pipeline = ChatPipeline()

        class Request:
            strategy = "lexical"

            def __init__(self, family: str) -> None:
                self.log_fields = {"query_family": family}

        new_families = ["scholarship", "grade", "graduation"]
        for family in new_families:
            with self.subTest(family=family):
                self.assertEqual(
                    pipeline._effective_retrieval_strategy(Request(family)),
                    "vector",
                    f"'{family}' 패밀리는 vector 전략을 사용해야 한다",
                )

    def test_hybrid_still_used_for_unregistered_families(self) -> None:
        # vector_only_families에 없는 패밀리는 여전히 hybrid를 사용해야 한다.
        # dormitory: r027에서 hybrid→vector 전환 시 top-3 회귀 확인 → hybrid 유지
        pipeline = ChatPipeline()

        for family in ["academic_admin", "dormitory"]:
            with self.subTest(family=family):

                class Request:
                    strategy = "lexical"
                    log_fields = {"query_family": family}

                self.assertEqual(
                    pipeline._effective_retrieval_strategy(Request()),
                    "hybrid",
                    f"'{family}' 패밀리는 hybrid를 유지해야 한다",
                )

    def test_topk_rejects_ui_noise_and_missing_required_terms(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="menu",
                chunk_id="menu_1",
                title="HOME",
                content="HOME 공유 SNS 메뉴 사이트맵 로그인 COPYRIGHT",
                score=9.0,
                metadata={
                    "required_terms": ["정보공학관"],
                    "rerank_signals": {"noise_score": 2.0, "required_entity_match": 0.0},
                },
            ),
            RetrievedDoc(
                doc_id="facility",
                chunk_id="facility_1",
                title="정보공학관 안내",
                content="정보공학관은 교내 건물 번호 23번입니다.",
                score=5.0,
                metadata={
                    "required_terms": ["정보공학관"],
                    "rerank_signals": {
                        "strong_term_match": 1.0,
                        "title_match": 0.8,
                        "required_entity_match": 1.0,
                    },
                },
            ),
        ]

        result = select_topk_with_diagnostics(docs, k=1)

        self.assertEqual(result["selected"][0].doc_id, "facility")
        self.assertIn("context_contamination", {item["reason"] for item in result["rejected_chunks"]})

    def test_context_includes_traceable_chunk_metadata(self) -> None:
        context = build_context(
            [
                RetrievedDoc(
                    doc_id="doc1",
                    chunk_id="chunk1",
                    title="정보공학관 안내",
                    source="https://example.test/doc1",
                    content="정보공학관은 23번 건물입니다.",
                    score=1.0,
                    metadata={"source_type": "department", "lexical_score": 0.8, "final_score": 0.9},
                )
            ]
        )

        self.assertIn("chunk_id: chunk1", context)
        self.assertIn("source_url: https://example.test/doc1", context)
        self.assertIn("lexical=0.8", context)

    def test_llm_context_excludes_diagnostic_noise(self) -> None:
        # LLM에 보내는 컨텍스트는 근거 본문/제목/출처만 남기고 내부 ID·점수 노이즈는 제거해야 한다.
        docs = [
            RetrievedDoc(
                doc_id="doc1",
                chunk_id="chunk1",
                title="중앙도서관 이용 안내",
                source="https://example.test/doc1",
                content="중앙도서관 평일 이용 시간은 09:00~22:00입니다.",
                score=1.0,
                metadata={"source_type": "static", "lexical_score": 0.8, "final_score": 0.9},
            )
        ]
        llm_context = build_llm_context(docs)

        # 근거 파악에 필요한 정보는 유지
        self.assertIn("중앙도서관 평일 이용 시간은 09:00~22:00입니다.", llm_context)
        self.assertIn("source_url: https://example.test/doc1", llm_context)
        self.assertIn("중앙도서관 이용 안내", llm_context)
        # 진단 노이즈는 제거
        self.assertNotIn("chunk_id", llm_context)
        self.assertNotIn("doc_id", llm_context)
        self.assertNotIn("scores:", llm_context)
        self.assertNotIn("lexical=", llm_context)

    def test_department_curriculum_selection_keeps_exact_department_chunks_only(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("컴퓨터공학과 2학년 이수표 교육과정")
        state.metadata["query_understanding"] = {
            "query_features": {"family": "department_curriculum"}
        }
        state.keywords = ["컴퓨터공학과", "2학년", "이수표", "교육과정"]
        state.retrieved_docs = [
            self._doc(
                "computer",
                "이수표 | 교육과정 | 컴퓨터공학과",
                "2 컴퓨터공학과 123456 자료구조 3 3.00/0.00",
                10.0,
                "department",
                chunk_id="computer_002",
                section_type="attachment",
            ),
            self._doc(
                "computer",
                "이수표 | 교육과정 | 컴퓨터공학과",
                "502439 알고리즘 3 3.00/0.00 502714 웹프로그래밍 3 1.00/2.00",
                9.0,
                "department",
                chunk_id="computer_003",
                section_type="attachment",
            ),
            self._doc(
                "human",
                "이수표 | 교육과정 | 인간공학과",
                "2 인간공학과 인간공학개론 3 3.00/0.00",
                8.0,
                "department",
                chunk_id="human_002",
                section_type="attachment",
            ),
        ]

        pipeline._select_and_build_context(state)

        selected_chunk_ids = {doc.chunk_id for doc in state.selected_docs}
        self.assertEqual({doc.doc_id for doc in state.selected_docs}, {"computer"})
        self.assertIn("computer_002", selected_chunk_ids)
        self.assertIn("computer_003", selected_chunk_ids)
        self.assertNotIn("인간공학과", state.context)

    def test_curriculum_year_block_ignores_semester_header(self) -> None:
        pipeline = ChatPipeline()
        text = (
            "학 년 과정구분 1 학 기 2 학 기\n"
            "2 전자공학과 111111 전자회로 3 3.00/0.00\n"
            "222222 회로이론 3 3.00/0.00\n"
            "3 전자공학과 333333 신호처리 3 3.00/0.00"
        )

        block = pipeline._extract_curriculum_year_block(text, 2, "전자공학과")

        self.assertIn("전자회로", block)
        self.assertIn("회로이론", block)
        self.assertNotIn("신호처리", block)

    def test_curriculum_year_block_uses_mentoring_markers_when_table_header_lists_years_first(self) -> None:
        pipeline = ChatPipeline()
        text = (
            "학 년 과정구분 1 학 기 2 학 기\n"
            "2 컴퓨터공\n학과\n공통교양\n3 컴퓨터공\n학과\n전공선택\n"
            "100145 지도교수멘토링Ⅲ 0.25 0.25/0.00 "
            "100146 지도교수멘토링Ⅳ 0.25 0.25/0.00 "
            "503125 자료구조 3 3.00/0.00 "
            "500111 객체지향프로그래밍 3 0.00/3.00 "
            "100147 지도교수멘토링Ⅴ 0.25 0.25/0.00 "
            "502439 알고리즘 3 3.00/0.00"
        )

        block = pipeline._extract_curriculum_year_block(text, 2, "컴퓨터공학과")

        self.assertIn("자료구조", block)
        self.assertIn("객체지향프로그래밍", block)
        self.assertNotIn("알고리즘", block)

    def test_curriculum_course_parser_handles_tables_without_course_codes(self) -> None:
        pipeline = ChatPipeline()
        text = (
            "| 2 | 공통교양 | 지도교수멘토링Ⅲ | 0.25 | 0.25 | 지도교수멘토링Ⅳ | 0.25 | 0.25 |\n"
            "| | 전공필수 | 작업설계및실습 | 3 | 2 | 1 | 산업심리학 | 3 | 3 |\n"
            "기초통계 3 3 산업안전관리 3 3"
        )

        courses = pipeline._extract_curriculum_courses(text)

        self.assertIn("작업설계및실습", courses)
        self.assertIn("산업심리학", courses)
        self.assertIn("기초통계", courses)
        self.assertIn("산업안전관리", courses)

    def test_faculty_selection_moves_exact_name_match_before_lifelong_source(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("최병윤 교수 정보")
        state.keywords = ["교수", "최병윤", "정보"]
        state.selected_docs = [
            self._doc(
                "lifelong",
                "동의대학교 평생교육원 > 음악학사 > 교수진소개",
                "김민선 교수 김준태 교수",
                9.0,
                "lifelong",
                source_url="https://lifelong.deu.ac.kr/CreditBank/MusicIntro_New.aspx",
            ),
            self._doc(
                "computer",
                "교수소개 게시판목록 | 컴퓨터공학과",
                "최병윤 교수님\n컴퓨터구조, 정보보호\n연구실\n정보공학관 802호",
                5.0,
                "department",
                source_url="https://swcc.deu.ac.kr/computer/sub02.do",
            ),
        ]

        pipeline._correct_faculty_selection(state, state.selected_docs)

        self.assertEqual(state.selected_docs[0].doc_id, "computer")
        self.assertTrue(state.metadata["source_correction_applied"])
        self.assertEqual(state.metadata["required_entity"], "최병윤")
        self.assertTrue(state.metadata["top1_required_entity_match"])

    def test_department_faculty_list_query_does_not_extract_department_as_professor(self) -> None:
        pipeline = ChatPipeline()
        for query in (
            "컴퓨터공학과 교수 목록",
            "컴퓨터공학과 교수소개",
            "k-뷰티학과 교수 목록",
            "k뷰티학과 교수소개",
            "응급구조학과 교수소개",
            "뷰티비즈니스학과 교수소개",
        ):
            with self.subTest(query=query):
                state = PipelineState.from_query(query)
                self.assertEqual(pipeline._required_faculty_entity(state), "")
                self.assertEqual(pipeline._faculty_query_type(state), "department_faculty_list")

    def test_department_faculty_list_selection_prefers_faculty_page(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("응급구조학과 교수소개")
        state.selected_docs = [
            self._doc("office", "학과사무실-공지사항 게시판목록 | 응급구조학과", "content", 9.0, "department"),
            self._doc("schedule", "학사일정 게시판목록 | 응급구조학과", "content", 8.0, "department"),
            self._doc("faculty", "교수소개 게시판목록 | 응급구조학과", "김응급 교수님\n응급구조학\n연구실\n의료보건관 501호", 5.0, "department"),
        ]

        pipeline._correct_department_faculty_list_selection(state, state.selected_docs)

        self.assertEqual(state.selected_docs[0].doc_id, "faculty")
        self.assertTrue(state.metadata["department_faculty_list_correction_applied"])
        self.assertEqual(state.metadata["faculty_query_type"], "department_faculty_list")
        self.assertEqual(state.metadata["required_entity"], "")

    def test_single_professor_with_department_still_extracts_name(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("첨단에너지공학과 김미라 교수")

        self.assertEqual(pipeline._required_faculty_entity(state), "김미라")
        self.assertEqual(pipeline._faculty_query_type(state), "single_professor")

    def test_curriculum_selection_keeps_exact_computer_engineering_department(self) -> None:
        pipeline = ChatPipeline()
        state = PipelineState.from_query("컴퓨터공학과 2학년 전공필수 과목")
        state.metadata["query_understanding"] = {
            "query_features": {"family": "department_curriculum"}
        }
        state.keywords = ["컴퓨터공학과", "2학년", "전공필수"]
        docs = [
            self._doc("software", "이수표 | 교육과정 | 컴퓨터소프트웨어학과", "2 컴퓨터소프트웨어학과 전공필수", 9.0, "department"),
            self._doc("computer", "이수표 | 교육과정 | 컴퓨터공학과", "2 컴퓨터공학과 전공필수 자료구조 3 3.00/0.00", 5.0, "department"),
        ]

        filtered = pipeline._filter_department_curriculum_docs(state, docs)

        self.assertEqual([doc.doc_id for doc in filtered], ["computer"])

    def test_query_features_classifies_graduation_family(self) -> None:
        self.assertEqual(extract_query_features("\uc878\uc5c5\ud559\uc810 \uc54c\ub824\uc918", []).family, "graduation")
        self.assertIn("\uc878\uc5c5", extract_query_features("\uc878\uc5c5 \uc694\uac74 \uc54c\ub824\uc918", []).required_terms)

    def test_reranker_prefers_graduation_rules_over_meeting_minutes(self) -> None:
        docs = [
            self._doc(
                "minutes",
                "\uc81c141\ucc28 \ub300\ud559\ud3c9\uc758\uc6d0\ud68c \ud68c\uc758\ub85d",
                "\uac01 \ub300\ud559\uc758 \uc878\uc5c5\ud559\uc810\uc740 130\ud559\uc810\uc73c\ub85c \ud55c\ub2e4.",
                9.0,
                "institution",
            ),
            self._doc(
                "guide",
                "2026 \ud559\uc0ac\uc815\ubcf4 \uc885\ud569\uc548\ub0b4",
                "\uc878\uc5c5\uc694\uac74 \ubc0f \uc878\uc5c5\ud559\uc810 \uc548\ub0b4: \uac01 \ub300\ud559\uc758 \uc878\uc5c5\ud559\uc810\uc740 130\ud559\uc810\uc785\ub2c8\ub2e4.",
                6.0,
                "academic_notice",
            ),
            self._doc(
                "rule",
                "\ud559\uce59",
                "\uc218\ub8cc \ubc0f \uc878\uc5c5: \uc878\uc5c5\ud559\uc810, \uc870\uae30\uc878\uc5c5, \uc878\uc5c5\uc694\uac74\uc744 \uc815\ud55c\ub2e4.",
                5.0,
                "institution",
            ),
        ]

        reranked = rerank_documents(docs, query="\uc878\uc5c5\ud559\uc810 \uc54c\ub824\uc918", keywords=[])

        self.assertEqual(reranked[0].doc_id, "guide")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["query_family_boost"], 0)
        self.assertLess(reranked[2].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_hybrid_prefers_dining_hall_for_info_engineering_cafeteria_hours(self) -> None:
        query_metadata = {
            "query": "\uc815\ubcf4\uacf5\ud559\uad00 \ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04",
            "query_family": "welfare_facility",
            "keywords": ["\uc815\ubcf4\uacf5\ud559\uad00", "\ud559\uc0dd\uc2dd\ub2f9", "\uc6b4\uc601\uc2dc\uac04"],
            "strong_terms": ["\uc815\ubcf4\uacf5\ud559\uad00", "\ud559\uc0dd\uc2dd\ub2f9", "\uc6b4\uc601\uc2dc\uac04"],
            "required_terms": ["\ud559\uc0dd\uc2dd\ub2f9"],
        }
        culture = self._doc(
            "culture",
            "\ubcf5\uc9c0\ubb38\ud654\uc2dc\uc124 | \ud3b8\uc758\u00b7\ubcf5\uc9c0 | \ub300\ud559\uc0dd\ud65c",
            "\uc815\ubcf4\uacf5\ud559\uad00 2\uce35 \ud559\uc0dd\uc2dd\ub2f9, \ud3b8\uc758\uc810, \ud734\uac8c\uc2e4",
            1.0,
            "institution",
            source_url="https://www.deu.ac.kr/www/deu-culture.do",
        ).model_copy(update={"metadata": {**query_metadata, "source_type": "institution", "lexical_norm_score": 1.0}})
        dining = self._doc(
            "dining",
            "\uad50\ub0b4\uc2dd\ub2f9 | \ud3b8\uc758\u00b7\ubcf5\uc9c0 | \ub300\ud559\uc0dd\ud65c",
            "\uc815\ubcf4\uacf5\ud559\uad00 \ud559\uc0dd \uc2dd\ub2f9 \uc704\uce58: \uc815\ubcf4\uacf5\ud559\uad00 2\uce35 \uc6b4\uc601\uc2dc\uac04 \uc911\uc2dd 11:00 ~ 15:00",
            0.7,
            "welfare",
            source_url="https://www.deu.ac.kr/www/deu-dining-hall.do",
        ).model_copy(update={"metadata": {**query_metadata, "source_type": "welfare", "lexical_norm_score": 0.7}})

        with patch.dict("os.environ", {"HYBRID_SCORE_MODE": "weighted"}, clear=False):
            merged = merge_retrieval_candidates(
                lexical_docs=[culture, dining],
                vector_docs=[
                    dining.model_copy(update={"score": 1.0, "metadata": {**dining.metadata, "vector_score": 1.0}}),
                    culture.model_copy(update={"score": 0.8, "metadata": {**culture.metadata, "vector_score": 0.8}}),
                ],
            )

        self.assertEqual(merged[0].doc_id, "dining")
        self.assertIn("deu-dining-hall.do", merged[0].document.source)
        self.assertGreater(merged[0].document.metadata["hybrid_adjustment"]["bonus"], 0.0)

    def _doc(
        self,
        doc_id: str,
        title: str,
        content: str,
        score: float,
        source_type: str,
        *,
        chunk_id: str | None = None,
        section_type: str = "body",
        source_url: str | None = None,
    ) -> RetrievedDoc:
        return RetrievedDoc(
            doc_id=doc_id,
            chunk_id=chunk_id or f"{doc_id}_chunk",
            title=title,
            content=content,
            score=score,
            source=source_url or f"https://example.test/{doc_id}",
            metadata={"source_type": source_type, "section_type": section_type, "content_length": len(content)},
        )


if __name__ == "__main__":
    unittest.main()
