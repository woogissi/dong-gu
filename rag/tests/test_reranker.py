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
                content="Registration office hours and campus announcements.",
                score=10.0,
                category="notice",
                metadata={"source_type": "notice", "published_at": "2026-01-01"},
            ),
            RetrievedDoc(
                doc_id="scholarship_notice",
                chunk_id="scholarship_notice_1",
                title="Scholarship application period",
                content="Scholarship application documents and deadline information.",
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
