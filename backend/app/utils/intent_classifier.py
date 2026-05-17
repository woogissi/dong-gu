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
            "알려줘", "알려주세요", "언제", "어디", "어디야", "어디임",
            "어떻게", "방법", "어디서", "몇시", "몇 시", "며칠",
            "기간", "날짜", "시간", "일정", "일정표", "위치", "지도", "장소",
            "가능", "신청", "운영", "운영시간", "총장", "정보"
        }

        # 학교 도메인 키워드
        self.domain_keywords = {
            "수강", "수강신청", "장학", "장학금", "기숙사", "도서관",
            "학점", "졸업", "학사", "학사일정", "교육과정", "강의실",
            "등록금", "휴학", "복학", "성적", "학식", "동아리",
            "공지", "공지사항", "증명서", "수업", "강의", "시간표", "학과",
            "학생증", "통학버스", "셔틀", "상담", "취업", "비교과",
            "교양", "전공", "출석", "시험", "중간고사", "기말고사",
            "계절학기", "휴강", "보강", "캠퍼스", "건물", "행정실", "총장", "정보"
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
        has_time = self.contains_any(text, self.time_keywords)
        has_pattern = self.has_info_pattern(text)

        # 1. 학교 도메인 키워드가 있으면 기본적으로 정보성 질문으로 처리
        # ex) 수강신청, 장학금, 기숙사, 도서관
        if has_domain:
            return True

        # 2. 질문 표현 + 시간/날짜 패턴이 같이 있으면 정보성으로 처리
        # ex) 3월 일정 알려줘, 다음 학기 언제야
        if has_question and (has_time or has_pattern):
            return True

        # 3. 질문 표현만 있으면 일반대화로 둠
        # ex) 알려줘, 가능?, 언제?
        return False

    def classify(self, utterance: str) -> PrimaryIntent:
        text = self.normalize_text(utterance)

        # 1. 욕설 우선 차단
        if contains_profanity(text):
            return "PROFANITY"

        # 2. 빈 입력은 일반대화로 처리
        if not text:
            return "GENERAL"

        # 3. 학교 정보성 질문
        if self.is_info(text):
            return "INFO"

        # 4. 나머지는 일반대화
        return "GENERAL"