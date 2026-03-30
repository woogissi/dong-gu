import re
from typing import Literal


PrimaryIntent = Literal["GENERAL", "INFO"]


class PrimaryIntentClassifier:
    """
    1차 분류기
    - GENERAL: 일반채팅
    - INFO: 정보성 질문

    규칙
    1. 정보성 키워드/패턴이 보이면 INFO 우선
    2. 아니면 GENERAL
    """

    def __init__(self) -> None:
        self.info_keywords = {
            "알려줘", "알려주세요", "언제", "어디", "어디야", "어디임",
            "어떻게", "신청", "기간", "날짜", "시간", "운영", "운영시간",
            "방법", "어디서", "가능", "몇시", "몇 시", "며칠", "일정", "일정표",
            "위치", "지도", "장소",

            "수강", "수강신청", "장학", "장학금", "기숙사", "도서관",
            "학점", "졸업", "학사", "학사일정", "교육과정", "강의실",
            "등록금", "휴학", "복학", "성적", "학식", "동아리", "공지", "공지사항",
            "증명서", "수업", "강의", "시간표", "학과",

            "오늘", "내일", "이번주", "다음주", "이번 학기", "다음 학기",
            "1학기", "2학기",
            "1월", "2월", "3월", "4월", "5월", "6월",
            "7월", "8월", "9월", "10월", "11월", "12월",
        }

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

    def is_info(self, text: str) -> bool:
        if any(keyword in text for keyword in self.info_keywords):
            return True

        if any(re.search(pattern, text) for pattern in self.info_patterns):
            return True

        return False

    def classify(self, utterance: str) -> PrimaryIntent:
        text = self.normalize_text(utterance)

        if not text:
            return "INFO"

        if self.is_info(text):
            return "INFO"

        return "GENERAL"