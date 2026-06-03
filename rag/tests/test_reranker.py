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

    def test_cross_encoder_signal_absent_by_default(self) -> None:
        """CE 플래그 기본(off)에서는 cross_encoder_score 신호가 생성되지 않아야 한다.

        CE 코드 도입이 기존 결정적 경로에 무영향임을 보장한다.
        """
        reranked = rerank_documents(
            [RetrievedDoc(doc_id="a", chunk_id="a_1", title="장학 공지", content="장학 신청 안내", score=1.0)],
            query="장학금 신청",
            keywords=["장학금", "신청"],
        )
        self.assertNotIn("cross_encoder_score", reranked[0].metadata["rerank_signals"])

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

    def test_dormitory_query_penalizes_exchange_without_foreign_content(self) -> None:
        # exchange 출처이지만 외국인/유학생 문맥이 없는 일반 공지가
        # 일반 기숙사 쿼리에서 페널티를 받아야 한다 (r027 회귀 방지).
        docs = [
            RetrievedDoc(
                doc_id="exchange_general_notice",
                chunk_id="exchange_general_notice_1",
                title="국제교류처 공지사항",
                content="기숙사 관련 일정 안내 및 국제 교류 행사 공지",
                score=10.0,
                metadata={"source_type": "exchange"},
            ),
            RetrievedDoc(
                doc_id="dorm_application",
                chunk_id="dorm_application_1",
                title="효민생활관 입사신청 안내",
                content="기숙사 입사 신청방법 신청기간 생활관",
                score=6.0,
                metadata={"source_type": "dormitory"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="기숙사 신청 어디서 해?",
            keywords=["기숙사", "신청"],
            category="dormitory",
        )

        exchange_doc = next(d for d in reranked if d.doc_id == "exchange_general_notice")
        self.assertLess(
            exchange_doc.metadata["rerank_signals"]["query_family_penalty"],
            0.0,
            "외국인 문맥 없는 exchange 문서도 일반 기숙사 쿼리에서 페널티를 받아야 한다",
        )
        self.assertEqual(
            reranked[0].doc_id,
            "dorm_application",
            "dorm.deu.ac.kr 정답 문서가 exchange 공지보다 상위여야 한다",
        )

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

    def test_attachment_penalty_exempt_for_department_curriculum(self) -> None:
        # department_curriculum 쿼리에서는 첨부파일(HWP/PDF)이 원본 소스이므로
        # attachment_noise_penalty가 0이어야 한다.
        docs = [
            RetrievedDoc(
                doc_id="curriculum_attachment",
                chunk_id="curriculum_attachment_1",
                title="이수표 | 교육과정 | 간호학과",
                content="간호학과 2학년 1학기 전공필수 인간의 성장 발달 해부학 성인간호학",
                score=10.0,
                metadata={"source_type": "department", "section_type": "attachment"},
            ),
            RetrievedDoc(
                doc_id="general_notice",
                chunk_id="general_notice_1",
                title="학과 소개 | 간호학과",
                content="간호학과 학과 소개 및 안내",
                score=5.0,
                metadata={"source_type": "department", "section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="간호학과 2학년 1학기 전공필수 알려줘",
            keywords=["간호학과", "2학년", "1학기", "전공필수"],
            category="department_curriculum",
        )

        attachment_doc = next(d for d in reranked if d.doc_id == "curriculum_attachment")
        self.assertEqual(
            attachment_doc.metadata["rerank_signals"]["attachment_noise"],
            0.0,
            "department_curriculum 쿼리에서 attachment_noise_penalty는 0이어야 한다",
        )
        self.assertEqual(reranked[0].doc_id, "curriculum_attachment")

    def test_attachment_penalty_still_applies_outside_exempt_families(self) -> None:
        # dormitory 쿼리에서는 attachment_noise_penalty가 여전히 적용되어야 한다.
        docs = [
            RetrievedDoc(
                doc_id="dorm_attachment",
                chunk_id="dorm_attachment_1",
                title="주거안정장학금 신청 안내",
                content="기숙사 관련 장학금 첨부 서류",
                score=10.0,
                metadata={"source_type": "scholarship", "section_type": "attachment"},
            ),
            RetrievedDoc(
                doc_id="dorm_body",
                chunk_id="dorm_body_1",
                title="효민생활관 입사 안내",
                content="기숙사 입사신청 방법 절차 생활관",
                score=5.0,
                metadata={"source_type": "dormitory", "section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="기숙사 신청 방법",
            keywords=["기숙사", "신청", "생활관"],
            category="dormitory",
        )

        attachment_doc = next(d for d in reranked if d.doc_id == "dorm_attachment")
        self.assertLess(
            attachment_doc.metadata["rerank_signals"]["attachment_noise"],
            0.0,
            "dormitory 쿼리에서 attachment_noise_penalty는 여전히 음수여야 한다",
        )

    def test_department_entity_match_boosts_correct_department_doc(self) -> None:
        # ranking_hints에 department_entity가 있을 때,
        # 해당 학과명이 포함된 문서가 포함되지 않은 문서보다 높게 랭크돼야 한다.
        docs = [
            RetrievedDoc(
                doc_id="wrong_dept",
                chunk_id="wrong_dept_1",
                title="이수표 | 교육과정 | 컴퓨터공학과",
                content="컴퓨터공학과 전공필수 교육과정 이수표",
                score=10.0,
                metadata={"source_type": "department", "section_type": "attachment"},
            ),
            RetrievedDoc(
                doc_id="correct_dept",
                chunk_id="correct_dept_1",
                title="이수표 | 교육과정 | 간호학과",
                content="간호학과 전공필수 교육과정 이수표",
                score=8.0,
                metadata={"source_type": "department", "section_type": "attachment"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="간호학과 전공필수 알려줘",
            keywords=["간호학과", "전공필수"],
            category="department_curriculum",
            ranking_hints={"department_entity": "간호학과"},
        )

        correct = next(d for d in reranked if d.doc_id == "correct_dept")
        wrong = next(d for d in reranked if d.doc_id == "wrong_dept")
        self.assertEqual(reranked[0].doc_id, "correct_dept", "학과명 일치 문서가 1위여야 한다")
        self.assertGreater(
            correct.metadata["rerank_signals"]["department_entity_match"],
            0.0,
            "일치 문서의 department_entity_match는 양수여야 한다",
        )
        self.assertLess(
            wrong.metadata["rerank_signals"]["department_entity_match"],
            0.0,
            "불일치 문서의 department_entity_match는 음수여야 한다",
        )

    def test_department_entity_match_uses_boundary_not_substring(self) -> None:
        # '경영' 질의가 '창업투자경영학과'에 substring으로 매칭되어 +1.5를 받던 문제(G049)를
        # 경계 매칭으로 차단한다. 정확히 일치하는 '경영학과'만 양수, 합성 학과명은 음수여야 한다.
        docs = [
            RetrievedDoc(
                doc_id="superset_dept",
                chunk_id="superset_dept_1",
                title="이수표 | 교육과정 | 창업투자경영학과",
                content="창업투자경영학과 전공필수 교육과정 이수표",
                score=10.0,
                metadata={"source_type": "department", "section_type": "attachment"},
            ),
            RetrievedDoc(
                doc_id="exact_dept",
                chunk_id="exact_dept_1",
                title="경영학과 교육과정",
                content="경영학과 1학년 2학기 전공필수 교육과정",
                score=8.0,
                metadata={"source_type": "static", "section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="경영학과 1학년 2학기 전공필수 알려줘",
            keywords=["경영학과", "전공필수"],
            category="department_curriculum",
            ranking_hints={"department_entity": "경영학과"},
        )

        exact = next(d for d in reranked if d.doc_id == "exact_dept")
        superset = next(d for d in reranked if d.doc_id == "superset_dept")
        self.assertGreater(
            exact.metadata["rerank_signals"]["department_entity_match"],
            0.0,
            "정확히 일치하는 경영학과 문서는 양수여야 한다",
        )
        self.assertLess(
            superset.metadata["rerank_signals"]["department_entity_match"],
            0.0,
            "'경영'을 부분 포함하는 창업투자경영학과 문서는 음수여야 한다",
        )

    def test_department_entity_match_inactive_outside_curriculum_families(self) -> None:
        # department_curriculum·graduation 이외 패밀리에서는 department_entity_match가 0이어야 한다.
        docs = [
            RetrievedDoc(
                doc_id="dorm_notice",
                chunk_id="dorm_notice_1",
                title="효민생활관 입사 안내",
                content="기숙사 입사신청 방법 절차 생활관",
                score=10.0,
                metadata={"source_type": "dormitory", "section_type": "body"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="기숙사 신청 방법",
            keywords=["기숙사", "신청"],
            category="dormitory",
            ranking_hints={"department_entity": "간호학과"},
        )

        self.assertEqual(
            reranked[0].metadata["rerank_signals"]["department_entity_match"],
            0.0,
            "dormitory 쿼리에서 department_entity_match는 0이어야 한다",
        )


    def test_career_query_boosts_advising_source_over_department_notice(self) -> None:
        # 일반 취업지원 쿼리에서 advising(취업지원센터) 문서가
        # department(학과 공지) 문서보다 상위여야 한다 (r029 회귀 방지).
        docs = [
            RetrievedDoc(
                doc_id="dept_notice",
                chunk_id="dept_notice_1",
                title="도시공학과 공지사항",
                content="취업지원 프로그램 안내 공지",
                score=10.0,
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="career_center",
                chunk_id="career_center_1",
                title="취업/진로 프로그램 | 취업지원센터",
                content="학생 성장 주기별 취업지원 프로그램 취업지원센터 안내",
                score=9.9,
                metadata={"source_type": "advising"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="취업지원 프로그램 어디서 봐?",
            keywords=["취업지원", "프로그램"],
            category="career",
        )

        self.assertEqual(reranked[0].doc_id, "career_center",
                         "advising 취업지원센터 문서가 학과 공지보다 상위여야 한다")
        career_doc = next(d for d in reranked if d.doc_id == "career_center")
        dept_doc   = next(d for d in reranked if d.doc_id == "dept_notice")
        self.assertGreater(career_doc.metadata["rerank_signals"]["query_family_boost"], 0,
                           "advising 문서의 query_family_boost는 양수여야 한다")
        self.assertLess(dept_doc.metadata["rerank_signals"]["query_family_penalty"], 0,
                        "department 문서의 query_family_penalty는 음수여야 한다")

    def test_career_query_preserves_department_when_dept_specific(self) -> None:
        # 학과명이 쿼리에 포함된 경우 department 문서에 페널티 없음
        docs = [
            RetrievedDoc(
                doc_id="dept_career_notice",
                chunk_id="dept_career_notice_1",
                title="컴퓨터공학과 취업지원 프로그램 안내",
                content="컴퓨터공학과 전용 취업지원 프로그램",
                score=10.0,
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="컴퓨터공학과 취업지원 프로그램",
            keywords=["컴퓨터공학과", "취업지원", "프로그램"],
            category="career",
        )

        self.assertEqual(
            reranked[0].metadata["rerank_signals"]["query_family_penalty"],
            0.0,
            "학과명이 쿼리에 있으면 department 문서에 페널티 없어야 한다",
        )


    def test_department_board_notice_penalized_for_non_department_query(self) -> None:
        # 비학과 쿼리(심리상담)에서 전 학과 복제 게시판 공지가
        # 공식 안내 페이지(상담센터)보다 하위여야 한다 (G036 회귀 방지).
        docs = [
            RetrievedDoc(
                doc_id="dept_board_notice",
                chunk_id="dept_board_notice_1",
                title="컴퓨터공학과 공지사항",
                content="심리 상담 관련 비교과 프로그램 안내 공지",
                score=10.0,
                source="https://swcc.deu.ac.kr/computer/sub06_03.do?article.offset=0&articleLimit=10&articleNo=85750&mode=view",
                metadata={"source_type": "department"},
            ),
            RetrievedDoc(
                doc_id="counsel_page",
                chunk_id="counsel_page_1",
                title="심리검사 | 심리검사 | 학생상담센터",
                content="학생상담센터 심리상담 신청 및 이용 안내",
                score=8.0,
                source="https://www.deu.ac.kr/counsel/sub03_01.do",
                metadata={"source_type": "advising"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="심리상담 어디서 받아?",
            keywords=["심리상담", "상담"],
        )

        board_doc = next(d for d in reranked if d.doc_id == "dept_board_notice")
        self.assertLess(
            board_doc.metadata["rerank_signals"]["department_board_noise"],
            0.0,
            "비학과 쿼리에서 학과 게시판 복제 공지는 페널티를 받아야 한다",
        )
        self.assertEqual(
            reranked[0].doc_id,
            "counsel_page",
            "공식 안내 페이지가 학과 게시판 복제 공지보다 상위여야 한다",
        )

    def test_department_board_notice_not_penalized_when_department_named(self) -> None:
        # 쿼리에 학과명이 명시되면 해당 학과 게시판 글에 페널티가 없어야 한다.
        docs = [
            RetrievedDoc(
                doc_id="dept_board_notice",
                chunk_id="dept_board_notice_1",
                title="컴퓨터공학과 공지사항",
                content="컴퓨터공학과 졸업논문 제출 안내",
                score=10.0,
                source="https://swcc.deu.ac.kr/computer/sub06_03.do?article.offset=0&articleLimit=10&articleNo=85750&mode=view",
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="컴퓨터공학과 공지사항 알려줘",
            keywords=["컴퓨터공학과", "공지사항"],
        )

        self.assertEqual(
            reranked[0].metadata["rerank_signals"]["department_board_noise"],
            0.0,
            "학과명이 쿼리에 있으면 학과 게시판 글에 페널티가 없어야 한다",
        )

    def test_department_static_page_not_treated_as_board_notice(self) -> None:
        # articleNo 없는 정적 안내 페이지(이수표)는 게시판 복제 공지가 아니다 (G060 회귀 방지).
        docs = [
            RetrievedDoc(
                doc_id="curriculum_page",
                chunk_id="curriculum_page_1",
                title="이수표 | 교육과정 | 경찰행정학과",
                content="경찰행정학과 3학년 2학기 전공선택 과목",
                score=10.0,
                source="https://police2001.deu.ac.kr/police/sub01_04_01.do",
                metadata={"source_type": "department"},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="경찰행정학과 3학년 2학기 전공선택 알려줘",
            keywords=["경찰행정학과", "전공선택"],
        )

        self.assertEqual(
            reranked[0].metadata["rerank_signals"]["department_board_noise"],
            0.0,
            "articleNo 없는 정적 안내 페이지는 게시판 복제 공지 페널티 대상이 아니다",
        )


    def test_content_required_match_prefers_chunk_with_answer_keyword(self) -> None:
        # 같은 문서(제목 동일)의 청크 중 required_term('보강')이 본문에 있는 청크가
        # 없는 청크보다 상위여야 한다 (G001 회귀 방지).
        docs = [
            RetrievedDoc(
                doc_id="schedule",
                chunk_id="schedule_march",
                title="학사일정 | 학사정보 | 대학생활",
                content="3월 1일 학기개시일 2일 대체휴일 개강",
                score=5.0,
                metadata={"source_type": "academic_calendar", "section_title": ""},
            ),
            RetrievedDoc(
                doc_id="schedule",
                chunk_id="schedule_june",
                title="학사일정 | 학사정보 | 대학생활",
                content="6월 9일~12일 지정보강일 보강 16~22일 기말시험",
                score=5.0,
                metadata={"source_type": "academic_calendar", "section_title": ""},
            ),
        ]

        reranked = rerank_documents(
            docs,
            query="보강 일정 알려줘",
            keywords=["보강", "일정"],
            category="academic_schedule",
            ranking_hints={"query_family": "academic_schedule"},
        )

        june = next(d for d in reranked if d.chunk_id == "schedule_june")
        march = next(d for d in reranked if d.chunk_id == "schedule_march")
        self.assertGreater(
            june.metadata["rerank_signals"]["content_required_match"],
            march.metadata["rerank_signals"]["content_required_match"],
            "'보강'이 본문에 있는 청크의 content_required_match가 더 커야 한다",
        )
        self.assertEqual(reranked[0].chunk_id, "schedule_june", "보강 청크가 상위여야 한다")

    def test_board_list_page_penalized_for_info_query(self) -> None:
        """정보성 질의에서 게시판/목록 인덱스 페이지는 안내 페이지보다 낮아야 한다(G037)."""
        docs = [
            RetrievedDoc(
                doc_id="board_list",
                chunk_id="board_list_1",
                title="공지사항",
                content="중앙도서관 공지사항 목록. 최근 게시글 안내 목록.",
                score=10.0,
                metadata={"source_type": "static", "source": "https://lib.deu.ac.kr/sb/default_notice_list.mir"},
            ),
            RetrievedDoc(
                doc_id="info_page",
                chunk_id="info_page_1",
                title="도서관소개",
                content="도서관 이용시간 안내. 자료실 월요일~금요일 09:00~20:00 운영.",
                score=9.0,
                metadata={"source_type": "static", "source": "https://lib.deu.ac.kr/intro_rule.mir"},
            ),
        ]

        reranked = rerank_documents(docs, query="도서관 이용 시간 알려줘", keywords=["도서관", "이용", "시간"])

        board = next(d for d in reranked if d.doc_id == "board_list")
        self.assertLess(
            board.metadata["rerank_signals"]["board_list_noise"], 0.0,
            "게시판 목록 페이지에 board_list_noise 페널티가 적용돼야 한다",
        )
        self.assertEqual(reranked[0].doc_id, "info_page", "안내 페이지가 목록 페이지보다 상위여야 한다")

    def test_board_list_page_exempt_for_notice_query(self) -> None:
        """사용자가 공지/게시판을 명시적으로 찾으면 목록 페이지를 페널티하지 않는다(G058)."""
        doc = RetrievedDoc(
            doc_id="board_list",
            chunk_id="board_list_1",
            title="학사공지 게시판",
            content="학사공지 게시판 목록입니다.",
            score=10.0,
            metadata={"source_type": "static", "source": "https://www.deu.ac.kr/www/gra-notice.do"},
        )

        reranked = rerank_documents(doc and [doc], query="학사공지 게시판 어디서 봐", keywords=["학사공지", "게시판"])

        self.assertEqual(
            reranked[0].metadata["rerank_signals"]["board_list_noise"], 0.0,
            "공지/게시판 명시 질의에서는 목록 페널티가 면제돼야 한다",
        )


if __name__ == "__main__":
    unittest.main()
