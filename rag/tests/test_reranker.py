import unittest

from rag.schemas.retrieved_doc import RetrievedDoc
from rag.selection.reranker import rerank_documents


class RerankerTest(unittest.TestCase):
    def test_reranks_by_title_and_keyword_relevance(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="general_notice",
                chunk_id="general_notice_1",
                title="General campus notice",
                content=(
                    "Registration office hours and campus announcements. "
                    "Please visit the administration building for details. "
                    "Office is open Monday through Friday 09:00 to 18:00."
                ),
                score=10.0,
                category="notice",
                metadata={"source_type": "notice", "published_at": "2026-01-01"},
            ),
            RetrievedDoc(
                doc_id="scholarship_notice",
                chunk_id="scholarship_notice_1",
                title="Scholarship application period",
                content=(
                    "Scholarship application documents and deadline information. "
                    "Students must submit required documents before the deadline. "
                    "Application period runs from March 1st to March 31st."
                ),
                score=5.0,
                category="academic_notice",
                metadata={"source_type": "academic_notice", "published_at": "2026-04-01"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="scholarship application period",
            keywords=["scholarship", "application", "period"],
            category="academic_notice",
            filters={"document_category": ["academic_notice"]},
        )

        self.assertEqual(reranked[0].doc_id, "scholarship_notice")
        self.assertGreater(reranked[0].score, docs[1].score)
        self.assertEqual(reranked[0].metadata["original_score"], 5.0)
        self.assertIn("rerank_signals", reranked[0].metadata)

    def test_preserves_retrieval_order_when_scores_tie(self) -> None:
        docs = [
            RetrievedDoc(doc_id="a", chunk_id="a_1", content="same", score=1.0),
            RetrievedDoc(doc_id="b", chunk_id="b_1", content="same", score=1.0),
        ]

        reranked = rerank_documents(docs, query="", keywords=[])

        self.assertEqual([doc.doc_id for doc in reranked], ["a", "b"])

    def test_temporal_rerank_prefers_matching_year_and_semester(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="course_2025",
                chunk_id="course_2025_1",
                title="2025\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad \uc548\ub0b4",
                content="2025\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad \uae30\uac04",
                score=5.0,
                metadata={"published_at": "2025-01-10"},
            ),
            RetrievedDoc(
                doc_id="course_2026",
                chunk_id="course_2026_1",
                title="2026\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad \uc548\ub0b4",
                content="2026\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad \uae30\uac04",
                score=5.0,
                metadata={"published_at": "2026-01-10"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="2026\ub144 1\ud559\uae30 \uc218\uac15\uc2e0\uccad",
            keywords=["2026\ub144", "1\ud559\uae30", "\uc218\uac15\uc2e0\uccad"],
            ranking_hints={
                "temporal_signals": {
                    "years": ["2026"],
                    "semesters": ["1\ud559\uae30"],
                    "relative_dates": [],
                    "recency_intent": False,
                    "has_explicit_temporal": True,
                }
            },
        )

        self.assertEqual(reranked[0].doc_id, "course_2026")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["temporal_score"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["temporal_score"], 0)
        self.assertIn("temporal_rerank_signals", reranked[0].metadata)

    def test_recency_intent_prefers_recent_published_document(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="scholarship_old",
                chunk_id="scholarship_old_1",
                title="\uc7a5\ud559 \uacf5\uc9c0",
                content="\uc7a5\ud559 \uc2e0\uccad \uc548\ub0b4",
                score=5.0,
                metadata={"published_at": "2024-01-01"},
            ),
            RetrievedDoc(
                doc_id="scholarship_new",
                chunk_id="scholarship_new_1",
                title="\uc7a5\ud559 \uacf5\uc9c0",
                content="\uc7a5\ud559 \uc2e0\uccad \uc548\ub0b4",
                score=5.0,
                metadata={"published_at": "2026-05-20"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="\ucd5c\uc2e0 \uc7a5\ud559 \uacf5\uc9c0",
            keywords=["\ucd5c\uc2e0", "\uc7a5\ud559", "\uacf5\uc9c0"],
            ranking_hints={
                "temporal_signals": {
                    "years": [],
                    "semesters": [],
                    "relative_dates": [],
                    "recency_intent": True,
                    "has_explicit_temporal": True,
                }
            },
        )

        self.assertEqual(reranked[0].doc_id, "scholarship_new")
        self.assertGreater(
            reranked[0].metadata["rerank_signals"]["temporal_score"],
            reranked[1].metadata["rerank_signals"]["temporal_score"],
        )

    def test_department_metadata_does_not_create_category_match(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="department_noise",
                chunk_id="department_noise_1",
                title="General notice",
                content="General application information.",
                score=1.0,
                metadata={"department": "\uc7a5\ud559\uc9c0\uc6d0\ud300", "source_type": "notice"},
            )
        ]

        reranked = rerank_documents(
            docs,
            query="\uc7a5\ud559\uae08 \uc2e0\uccad",
            keywords=["\uc7a5\ud559\uae08", "\uc2e0\uccad"],
            category="scholarship",
            ranking_hints={"category_values": ["\uc7a5\ud559"]},
        )

        self.assertEqual(reranked[0].metadata["rerank_signals"]["category_match"], 0.0)

    def test_ranking_hints_still_drive_category_match_by_source_type(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="scholarship_source",
                chunk_id="scholarship_source_1",
                title="Scholarship notice",
                content="Scholarship application details.",
                score=1.0,
                metadata={"source_type": "scholarship", "department": "\ud559\uacfc\uc870\uad50"},
            )
        ]

        reranked = rerank_documents(
            docs,
            query="scholarship application",
            keywords=["scholarship", "application"],
            filters={},
            ranking_hints={"document_category": ["scholarship"]},
        )

        self.assertEqual(reranked[0].metadata["rerank_signals"]["category_match"], 0.7)

    def test_request_injected_doc_category_does_not_create_category_match(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="library_job",
                chunk_id="library_job_1",
                title="Library staff job posting",
                content="Hiring notice for library operations.",
                score=1.0,
                category="library",
                metadata={"source_type": "department"},
            )
        ]

        reranked = rerank_documents(
            docs,
            query="library hours",
            keywords=["library", "hours"],
            category="library",
            filters={},
            ranking_hints={"document_category": ["library"]},
        )

        self.assertEqual(reranked[0].metadata["rerank_signals"]["category_match"], 0.0)

    def test_library_source_type_still_creates_category_match(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="library_page",
                chunk_id="library_page_1",
                title="Library hours",
                content="Library operating hours.",
                score=1.0,
                category="library",
                metadata={"source_type": "library"},
            )
        ]

        reranked = rerank_documents(
            docs,
            query="library hours",
            keywords=["library", "hours"],
            filters={},
            ranking_hints={"document_category": ["library"]},
        )

        self.assertEqual(reranked[0].metadata["rerank_signals"]["category_match"], 0.7)

    def test_library_query_penalizes_department_job_postings(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="library_job",
                chunk_id="library_job_1",
                title="\ub3c4\uc11c\uad00 \uc6b4\uc601\uad00\ub9ac \uc0ac\ubb34\uc6d0 \ucc44\uc6a9 \uacf5\uace0",
                content="\uae30\uac04\uc81c \uc0ac\uc11c\uc9c1 \uadfc\ub85c\uc790 \ucc44\uc6a9",
                score=5.0,
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="library_page",
                chunk_id="library_page_1",
                title="\ub3c4\uc11c\uad00\uc18c\uac1c",
                content="\ub3c4\uc11c\uad00 \uc6b4\uc601\uc2dc\uac04 \uc548\ub0b4",
                score=5.0,
                metadata={"source_type": "library"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="\ub3c4\uc11c\uad00 \uc6b4\uc601\uc2dc\uac04 \uc54c\ub824\uc918",
            keywords=["\ub3c4\uc11c\uad00", "\uc6b4\uc601\uc2dc\uac04"],
            ranking_hints={"document_category": ["library"]},
        )

        self.assertEqual(reranked[0].doc_id, "library_page")
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_cafeteria_query_prefers_welfare_cafeteria_over_dormitory(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="dormitory_cafeteria",
                chunk_id="dormitory_cafeteria_1",
                title="\ub3d9\uc758\ub300\ud559\uad50 \ud6a8\ubbfc\uc0dd\ud65c\uad00",
                content="\uc0dd\ud65c\uad00 \uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04 \uc548\ub0b4",
                score=5.0,
                metadata={"source_type": "dormitory"},
            ),
            RetrievedDoc(
                doc_id="campus_cafeteria",
                chunk_id="campus_cafeteria_1",
                title="\uad50\ub0b4\uc2dd\ub2f9 | \ud3b8\uc758\u00b7\ubcf5\uc9c0 | \ub300\ud559\uc0dd\ud65c",
                content="\ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04 \uc548\ub0b4",
                score=5.0,
                metadata={"source_type": "welfare"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="\ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04 \uc54c\ub824\uc918",
            keywords=["\ud559\uc0dd\uc2dd\ub2f9", "\uc6b4\uc601\uc2dc\uac04"],
            ranking_hints={"document_category": ["institution", "static"]},
        )

        self.assertEqual(reranked[0].doc_id, "campus_cafeteria")
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_dormitory_query_penalizes_foreign_exchange_notice_when_not_requested(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="foreign_dorm",
                chunk_id="foreign_dorm_1",
                title="2026-1\ud559\uae30 \uc678\uad6d\uc778 \uc720\ud559\uc0dd \ud589\ubcf5\uae30\uc219\uc0ac \uc218\uc694\uc870\uc0ac \uc2e0\uccad \uc548\ub0b4",
                content="\uae30\uc219\uc0ac \uc2e0\uccad \uae30\uac04",
                score=5.0,
                metadata={"source_type": "exchange"},
            ),
            RetrievedDoc(
                doc_id="general_dorm",
                chunk_id="general_dorm_1",
                title="\ub3d9\uc758\ub300\ud559\uad50 \ud6a8\ubbfc\uc0dd\ud65c\uad00",
                content="\uae30\uc219\uc0ac \uc785\uc0ac \uc2e0\uccad \uae30\uac04 \uc548\ub0b4",
                score=5.0,
                metadata={"source_type": "dormitory"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="\uae30\uc219\uc0ac \uc2e0\uccad \uae30\uac04 \uc54c\ub824\uc918",
            keywords=["\uae30\uc219\uc0ac", "\uc2e0\uccad", "\uae30\uac04"],
            category="dormitory",
            ranking_hints={"document_category": ["dormitory", "notice"]},
        )

        self.assertEqual(reranked[0].doc_id, "general_dorm")
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_foreign_dormitory_query_keeps_exchange_notice_available(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="foreign_dorm",
                chunk_id="foreign_dorm_1",
                title="2026-1\ud559\uae30 \uc678\uad6d\uc778 \uc720\ud559\uc0dd \ud589\ubcf5\uae30\uc219\uc0ac \uc218\uc694\uc870\uc0ac \uc2e0\uccad \uc548\ub0b4",
                content="\uc678\uad6d\uc778 \uc720\ud559\uc0dd \uae30\uc219\uc0ac \uc2e0\uccad \uae30\uac04",
                score=5.0,
                metadata={"source_type": "exchange"},
            )
        ]

        reranked = rerank_documents(
            docs,
            query="\uc678\uad6d\uc778 \uc720\ud559\uc0dd \uae30\uc219\uc0ac \uc2e0\uccad",
            keywords=["\uc678\uad6d\uc778", "\uc720\ud559\uc0dd", "\uae30\uc219\uc0ac", "\uc2e0\uccad"],
            category="dormitory",
            ranking_hints={"document_category": ["dormitory", "notice"]},
        )

        self.assertEqual(reranked[0].metadata["rerank_signals"]["query_family_penalty"], 0.0)

    def test_general_graduation_prefers_policy_over_department_notice(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="department_graduation_notice",
                chunk_id="department_graduation_notice_1",
                title="컴퓨터공학과 졸업예정자 졸업논문 제출 안내",
                content="졸업예정자 졸업논문 제출 일정 안내",
                score=5.0,
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="graduation_policy",
                chunk_id="graduation_policy_1",
                title="졸업인증제도 | 학사정보",
                content="졸업요건 졸업기준 졸업학점 이수학점 안내",
                score=5.0,
                metadata={"source_type": "academic_support"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="졸업요건 알려줘",
            keywords=["졸업요건", "졸업", "요건"],
            category="graduation",
            ranking_hints={"document_category": ["academic_notice", "academic_support", "institution"]},
        )

        self.assertEqual(reranked[0].doc_id, "graduation_policy")
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_department_graduation_credit_prefers_curriculum_evidence(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="career_page",
                chunk_id="career_page_1",
                title="진로 및 취업 현황 | 컴퓨터공학과",
                content="컴퓨터공학과 진로 약사 취업 현황 안내",
                score=5.0,
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="curriculum_page",
                chunk_id="curriculum_page_1",
                title="이수표 | 교육과정 | 컴퓨터공학과",
                content="컴퓨터공학과 졸업학점 이수학점 전공필수 교양필수 졸업기준",
                score=5.0,
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="컴퓨터공학과 졸업학점 알려줘",
            keywords=["컴퓨터공학과", "졸업학점", "학점"],
            category="graduation",
            ranking_hints={"query_family": "department_curriculum", "document_category": ["department"]},
        )

        self.assertEqual(reranked[0].doc_id, "curriculum_page")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["query_family_boost"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_department_curriculum_query_still_prefers_curriculum_page(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="career_page",
                chunk_id="career_page_1",
                title="학과 약사 | 컴퓨터공학과",
                content="컴퓨터공학과 약사 및 진로 안내",
                score=5.0,
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="curriculum_page",
                chunk_id="curriculum_page_1",
                title="이수표 | 교육과정 | 컴퓨터공학과",
                content="컴퓨터공학과 교육과정 이수표 전공필수",
                score=5.0,
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="컴퓨터공학과 교육과정 알려줘",
            keywords=["컴퓨터공학과", "교육과정"],
            category="department",
            ranking_hints={"query_family": "department_curriculum", "document_category": ["department"]},
        )

        self.assertEqual(reranked[0].doc_id, "curriculum_page")

    def test_dormitory_query_prefers_dormitory_source_over_housing_scholarship(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="housing_scholarship",
                chunk_id="housing_scholarship_1",
                title="2026-1학기 주거안정장학금 신청 안내",
                content="주거안정장학금 지원금 수혜를 위한 오리엔테이션 (기숙사용)",
                score=10.0,
                category="scholarship",
                metadata={"source_type": "scholarship", "section_type": "attachment"},
            ),
            RetrievedDoc(
                doc_id="dorm_apply",
                chunk_id="dorm_apply_1",
                title="동의대학교 효민생활관",
                content="입사신청 방법안내(공통) 효민생활관 행복기숙사 입사 신청 절차",
                score=4.0,
                category="dormitory",
                metadata={"source_type": "dormitory", "section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="기숙사 신청 방법 알려줘",
            keywords=["기숙사", "생활관", "신청", "입사신청"],
            category="dormitory",
            filters={"document_category": ["dormitory", "notice"]},
        )

        self.assertEqual(reranked[0].doc_id, "dorm_apply")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["query_family_boost"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_dormitory_application_intent_prefers_notice_over_homepage(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="dorm_home",
                chunk_id="dorm_home_1",
                title="동의대학교 효민생활관",
                content="생활관 소개 생활관안내 시설현황 찾아오시는 길",
                score=10.0,
                source="https://dorm.deu.ac.kr/main.do",
                category="dormitory",
                metadata={"source_type": "dormitory", "section_type": "body"},
            ),
            RetrievedDoc(
                doc_id="dorm_recruit",
                chunk_id="dorm_recruit_1",
                title="2026학년도 1학기 효민생활관 입사생 모집 안내",
                content="기숙사 입사신청 신청기간 및 제출서류 안내",
                score=4.0,
                source="https://dorm.deu.ac.kr/board/notice",
                category="dormitory",
                metadata={"source_type": "dormitory", "section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="기숙사 신청 날짜",
            keywords=["기숙사", "신청", "날짜"],
            category="dormitory",
        )

        self.assertEqual(reranked[0].doc_id, "dorm_recruit")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["query_family_boost"], reranked[1].metadata["rerank_signals"]["query_family_boost"])
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_general_club_query_prefers_central_club_info_over_department_career_club(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="career_club",
                chunk_id="career_club_1",
                title="컴퓨터공학과 학과 진로동아리 모집",
                content="취업동아리 전공동아리 참여 학생 모집 안내",
                score=10.0,
                category="department",
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="central_club",
                chunk_id="central_club_1",
                title="중앙동아리 안내",
                content="학생활동 중앙동아리 동아리 종류와 동아리 가입 신청 안내",
                score=4.0,
                category="club_activity",
                metadata={"source_type": "club_activity"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="동아리 종류",
            keywords=["동아리", "종류"],
            category="club_activity",
        )

        self.assertEqual(reranked[0].doc_id, "central_club")
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_person_title_query_prefers_former_president_page_over_message_noise(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="president_message",
                chunk_id="president_message_1",
                title="총장메시지",
                content="총장 인사말과 대학 소식 안내",
                score=10.0,
                category="notice",
                metadata={"source_type": "notice"},
            ),
            RetrievedDoc(
                doc_id="former_presidents",
                chunk_id="former_presidents_1",
                title="역대총장",
                content="제9대 총장 홍길동 재임기간 안내",
                score=4.0,
                category="institution",
                metadata={"source_type": "institution"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="9대 총장",
            keywords=["9대", "총장"],
            category="institution",
        )

        self.assertEqual(reranked[0].doc_id, "former_presidents")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["verified_title_boost"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["query_family_penalty"], 0)

    def test_penalizes_high_base_score_documents_missing_core_terms(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="course_notice",
                chunk_id="course_notice_1",
                title="2026 하계 계절수업 안내",
                content="오늘 진행 강의 전자출결 안내",
                score=10.0,
                metadata={"section_type": "attachment"},
            ),
            RetrievedDoc(
                doc_id="meal_notice",
                chunk_id="meal_notice_1",
                title="학생식당 학식 식단 안내",
                content="오늘 메뉴와 가격 안내",
                score=5.0,
                metadata={"section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="오늘 학식",
            keywords=["오늘", "학식"],
        )

        self.assertEqual(reranked[0].doc_id, "meal_notice")
        self.assertLess(reranked[1].metadata["rerank_signals"]["missing_strong_terms"], 0)

    def test_faculty_query_prefers_exact_professor_match_over_lifelong_faculty_list(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="lifelong_music",
                chunk_id="lifelong_music_1",
                title="동의대학교 평생교육원 > 음악학사 > 교수진소개",
                content="김민선 교수 김준태 교수 김혜현 교수",
                score=10.0,
                source="https://lifelong.deu.ac.kr/CreditBank/MusicIntro_New.aspx",
                metadata={"source_type": "lifelong"},
            ),
            RetrievedDoc(
                doc_id="computer_faculty",
                chunk_id="computer_faculty_1",
                title="교수소개 게시판목록 | 컴퓨터공학과",
                content="최병윤 교수님\n컴퓨터구조, 정보보호\n연구실\n정보공학관 802호",
                score=4.0,
                source="https://swcc.deu.ac.kr/computer/sub02.do",
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="최병윤 교수 정보",
            keywords=["교수", "최병윤", "정보"],
            category="faculty",
        )

        self.assertEqual(reranked[0].doc_id, "computer_faculty")
        self.assertGreater(reranked[0].metadata["rerank_signals"]["faculty_entity_match"], 0)
        self.assertLess(reranked[1].metadata["rerank_signals"]["faculty_entity_penalty"], 0)

    def test_department_faculty_list_query_does_not_penalize_as_missing_professor_name(self) -> None:
        docs = [
            RetrievedDoc(
                doc_id="office",
                chunk_id="office_1",
                title="학과사무실-공지사항 게시판목록 | K-뷰티학과",
                content="학과사무실 안내",
                score=10.0,
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="faculty",
                chunk_id="faculty_1",
                title="전임교수 게시판목록 | K-뷰티학과",
                content="김미용 교수님\n뷰티디자인",
                score=4.0,
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="k-뷰티학과 교수 목록",
            keywords=["k뷰티학과", "교수", "목록"],
            category="department",
        )

        self.assertEqual(reranked[0].metadata["rerank_signals"]["faculty_entity_match"], 0)
        self.assertEqual(reranked[0].metadata["rerank_signals"]["faculty_entity_penalty"], 0)


if __name__ == "__main__":
    unittest.main()
