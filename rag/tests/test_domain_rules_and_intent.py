import unittest

from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.preprocess.primary_intent import PrimaryIntentClassifier


DOMAIN_CASES = {
    "23번 건물 어디야": ("building_location", "facility", ["23번건물", "건물"]),
    "수덕전 위치 알려줘": ("building_location", "facility", ["수덕전", "위치"]),
    "지천관 위치 알려줘": ("building_location", "facility", ["지천관", "위치"]),
    "상영관 어디야": ("building_location", "facility", ["상영관"]),
    "학생회관 위치": ("building_location", "facility", ["학생회관", "위치"]),
    "콜라보라운지 운영 시간": ("building_location", "facility", ["콜라보라운지"]),
    "정보관 위치": ("building_location", "facility", ["정보관", "위치"]),
    "컴퓨터공학과 사무실 전화번호": ("department_curriculum", "department", ["컴퓨터공학과", "전화번호"]),
    "통학버스 시간표": ("general", "shuttle", ["통학버스", "시간표"]),
    "오늘 학식 뭐야": ("welfare_facility", "cafeteria", ["학생식당"]),
    "장학금 신청 방법": ("general", "scholarship", ["장학금", "신청"]),
    "국가장학금 언제 신청해": ("general", "scholarship", ["국가장학금", "신청"]),
    "수강신청 기간 알려줘": ("course_registration", "course", ["수강신청", "기간"]),
    "졸업요건 확인하고 싶어": ("graduation", "graduation", ["졸업요건", "확인"]),
    "성적 확인 어디서 해": ("general", "grade", ["성적", "확인"]),
    "휴학 신청 방법": ("academic_admin", "academic", ["휴학", "신청"]),
    "복학 신청 기간": ("academic_admin", "academic", ["복학", "신청"]),
    "도서관 운영시간": ("general", "library", ["도서관", "운영시간"]),
    "기숙사 신청": ("dormitory", "dormitory", ["기숙사", "신청"]),
    "현장실습 신청 방법": ("general", "career", ["현장실습", "신청"]),
    "취업지원센터 위치": ("building_location", "career", ["취업지원센터", "위치"]),
    "증명서 발급 방법": ("certificate", "certificate", ["증명서", "발급"]),
    "등록금 납부 기간": ("general", "tuition", ["등록금", "납부"]),
    "예비군 관련 안내": ("general", "military", ["예비군"]),
    "첨부파일에 있는 신청서 찾아줘": ("general", "attachment", ["첨부파일", "신청서"]),
}


class DomainRulesAndIntentTest(unittest.TestCase):
    def test_university_domain_queries_route_to_info(self) -> None:
        classifier = PrimaryIntentClassifier()

        for query in DOMAIN_CASES:
            with self.subTest(query=query):
                self.assertEqual(classifier.classify(query), "INFO")

    def test_smalltalk_stays_general(self) -> None:
        classifier = PrimaryIntentClassifier()

        self.assertEqual(classifier.classify("안녕하세요"), "GENERAL")
        self.assertEqual(classifier.classify("감사합니다"), "GENERAL")

    def test_dormitory_query_is_not_treated_as_general_family(self) -> None:
        state = PipelineState.from_query("기숙사 신청 방법 알려줘")
        QueryPreprocessor().run(state)

        features = state.metadata["query_understanding"]["query_features"]

        self.assertEqual(features["family"], "dormitory")
        self.assertEqual(features["domain"], "dormitory")
        self.assertIn("dormitory", state.filters.get("category", []))

    def test_family_detection_requires_domain_anchor_for_generic_intents(self) -> None:
        cases = {
            "기숙사 신청 날짜": ("dormitory", "dormitory"),
            "기숙사 운영시간": ("dormitory", "dormitory"),
            "정보공학관 학생식당 운영시간": ("welfare_facility", {"cafeteria", "campus_facility"}),
            "셔틀버스 시간표": ("shuttle", "shuttle"),
            "성적우수장학금 신청 기간": ("specific_scholarship", "scholarship"),
            "성적 확인 방법": ("grade", "grade"),
            "동아리 종류": ("club_program", "club_activity"),
            "동아리 신청 방법": ("club_program", "club_activity"),
            "컴퓨터공학과 졸업학점 알려줘": ("department_curriculum", "department_major"),
            "지천관 위치 알려줘": ("building_location", {"campus_facility", "facility"}),
            "상영관 어디야": ("building_location", {"campus_facility", "facility"}),
            "콜라보라운지 운영 시간": ("building_location", {"campus_facility", "facility", "welfare_facility"}),
            "정보관 위치": ("building_location", {"campus_facility", "facility"}),
        }
        preprocessor = QueryPreprocessor()

        for query, (expected_family, expected_domain) in cases.items():
            with self.subTest(query=query):
                state = PipelineState.from_query(query)
                preprocessor.run(state)
                features = state.metadata["query_understanding"]["query_features"]

                self.assertEqual(features["family"], expected_family)
                if isinstance(expected_domain, set):
                    self.assertIn(features["domain"], expected_domain)
                else:
                    self.assertEqual(features["domain"], expected_domain)

                if "식당" in query or "정보공학관" in query:
                    self.assertNotEqual(features["domain"], "library")
                    self.assertNotIn("library", state.keywords)

    def test_generic_intent_terms_alone_do_not_select_specific_family(self) -> None:
        preprocessor = QueryPreprocessor()

        for query in ["운영시간", "신청 방법", "기간 정보", "날짜 알려줘"]:
            with self.subTest(query=query):
                state = PipelineState.from_query(query)
                preprocessor.run(state)
                features = state.metadata["query_understanding"]["query_features"]

                self.assertEqual(features["family"], "general")

    def test_preprocessor_preserves_core_keywords_and_soft_filters(self) -> None:
        preprocessor = QueryPreprocessor()

        for query, (family, category, required_terms) in DOMAIN_CASES.items():
            with self.subTest(query=query):
                state = PipelineState.from_query(query)
                preprocessor.run(state)
                understanding = state.metadata["query_understanding"]
                features = understanding["query_features"]
                keyword_text = " ".join([state.rewritten_query, *state.rewritten_queries, *state.keywords])
                expected_family = {
                    "career": "career",
                    "grade": "grade",
                    "library": "library",
                    "shuttle": "shuttle",
                    "tuition": "tuition",
                }.get(category, family)

                self.assertEqual(features["family"], expected_family)
                self.assertEqual(understanding["detected_category"], category)
                for term in required_terms:
                    self.assertIn(term, keyword_text)
                self.assertNotIn("학과사무실", state.filters.get("department", []))
                self.assertIn("rule_hit_names", understanding)
                self.assertIn("applied_boosts", understanding)


if __name__ == "__main__":
    unittest.main()
