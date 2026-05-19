import re
from typing import Literal
from backend.app.utils.profanity_filter import contains_profanity

PrimaryIntent = Literal["GENERAL", "INFO", "PROFANITY"]


class PrimaryIntentClassifier:
    """
    1차 의도 분류기

    역할:
    - 욕설 → PROFANITY
    - 학교 정보성 질문 → INFO
    - 그 외 → GENERAL
    """

    def __init__(self) -> None:
        # 질문 의도 표현
        self.question_keywords = {
            "알려줘", "알려주세요", "궁금", "궁금해",
            "언제", "어디", "어디야", "어디임", "어디서",
            "어떻게", "방법", "몇시", "몇 시", "며칠",
            "기간", "날짜", "시간", "일정", "일정표",
            "위치", "지도", "장소", "가능", "신청",
            "운영", "운영시간", "확인", "조회", "볼 수 있어",
            "뭐야", "뭔데", "무엇", "안내",
            "가는 길", "길", "찾아가", "찾아가는",
        }

        # 학교 도메인 키워드
        self.domain_keywords = {
            # 학사
            "수강", "수강신청", "수강정정", "장바구니",
            "학점", "졸업", "학사", "학사일정", "교육과정",
            "등록금", "휴학", "복학", "성적", "출석",
            "시험", "중간고사", "기말고사", "계절학기",
            "휴강", "보강", "수업", "강의", "시간표",

            # 학생 생활
            "장학", "장학금", "기숙사", "도서관",
            "학식", "식당", "학생식당", "구내식당", "식단", "메뉴",
            "학생증", "통학버스", "셔틀", "셔틀버스", "버스", "상담",
            "동아리", "비교과",

            # 학교 조직/시설
            "학과", "전공", "학부", "단과대", "대학",
            "대학원", "일반대학원", "특수대학원",
            "강의실", "캠퍼스", "건물", "호관", "관", "라운지", "정보관", "정보공학관", "지천관",
            "행정실", "학생회관", "상영관", "도서관",
            "교수", "교수님", "교직원", "연구실",
            "이메일", "메일", "전화번호", "연락처",
            "총장", "학장", "역대", "이름",

            # 공지/취업
            "공지", "공지사항", "증명서",
            "취업", "진로", "현장실습", "ipp"
        }

        # 동의대 직접 지칭 표현
        self.school_keywords = {
            "동의대", "동의대학교", "학교", "우리학교", "우리 학교"
        }

        # 시간 표현
        self.time_keywords = {
            "오늘", "내일", "모레", "이번주", "다음주",
            "이번 주", "다음 주",
            "이번 학기", "다음 학기",
            "1학기", "2학기",
            "1월", "2월", "3월", "4월", "5월", "6월",
            "7월", "8월", "9월", "10월", "11월", "12월",
        }

        # 숫자 기반 시간/날짜 패턴
        self.info_patterns = [
            r"\d+\s*월",
            r"\d+\s*일",
            r"\d+\s*시",
            r"\d+\s*학기",
            r"\d+\s*호관",
            r"\d+[- ]?\d*\s*번\s*버스",
            r"\d{2,4}[-.]\d{3,4}[-.]\d{4}",
            r"(이번|다음)\s*주",
            r"(이번|다음)\s*학기",
        ]

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.strip().lower()
        text = " ".join(text.split())
        text = re.sub(r"[?!.~]+$", "", text).strip()
        return text

    def contains_any(self, text: str, keywords: set[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def has_info_pattern(self, text: str) -> bool:
        return any(re.search(pattern, text) for pattern in self.info_patterns)

    def is_info(self, text: str) -> bool:
        has_question = self.contains_any(text, self.question_keywords)
        has_domain = self.contains_any(text, self.domain_keywords)
        has_school = self.contains_any(text, self.school_keywords)
        has_time = self.contains_any(text, self.time_keywords)
        has_pattern = self.has_info_pattern(text)

        # 1. 학교 도메인 키워드가 있으면 정보성으로 처리
        # ex) 수강신청, 장학금, 기숙사, 식당, 대학원
        if has_domain:
            return True

        # 2. 학교 지칭 + 질문 표현이 있으면 정보성으로 처리
        # ex) 학교 식당 어디야, 우리 학교 일정 알려줘
        if has_school and has_question:
            return True

        # 3. 질문 표현 + 시간/날짜 표현이 있으면 정보성으로 처리
        # ex) 3월 일정 알려줘, 다음 학기 언제야
        if has_question and (has_time or has_pattern):
            return True

        return False

    def classify(self, utterance: str) -> PrimaryIntent:
        text = self.normalize_text(utterance)

        if contains_profanity(text):
            return "PROFANITY"

        if not text:
            return "GENERAL"

        if self.is_info(text):
            return "INFO"

        return "GENERAL"
