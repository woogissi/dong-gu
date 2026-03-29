from typing import Literal

PrimaryIntent = Literal["GENERAL", "INFO"]


class PrimaryIntentClassifier:
    """
    1차 분류기
    - GENERAL: 일반채팅
    - INFO: 정보성 질문

    규칙
    1. 정보성 키워드가 보이면 INFO 우선
    2. 아니면 짧고 명확한 일반채팅만 GENERAL
    3. 애매하면 INFO
    """

    def __init__(self) -> None:
        self.general_words = {
            "안녕", "안녕하세요", "안뇽", "하이", "ㅎㅇ", 
            "고마워", "감사", "감사합니다", "ㄳ", "땡큐",
            "잘가", "바이", "bye", "ㅂㅂ", "종료", "끝", 
            "ㅋㅋ", "ㅎㅎ", "ㅇㅇ", "응", "넵", "네", "오", "오케이"
        }

        self.info_keywords = {
            "알려줘", "언제", "어디", "어떻게", "신청", "기간", "날짜",
            "시간", "운영", "운영시간", "방법", "어디서", "가능", "몇 시",
            "수강", "수강신청", "장학", "장학금", "기숙사", "도서관",
            "학점", "졸업", "학사", "교육과정", "강의실", "등록금",
            "휴학", "복학", "성적", "학식", "동아리", "공지", "공지사항"
        }

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.strip().lower()
        text = " ".join(text.split())

        while text and text[-1] in {"?", "!", ".", "~"}:
            text = text[:-1].strip()

        return text

    def is_info(self, text: str) -> bool:
        return any(keyword in text for keyword in self.info_keywords)

    def is_general(self, text: str) -> bool:
        return text in self.general_words

    def classify(self, utterance: str) -> PrimaryIntent:
        text = self.normalize_text(utterance)

        if not text:
            return "INFO"

        # 정보성 우선
        if self.is_info(text):
            return "INFO"

        # 그다음 일반채팅
        if self.is_general(text):
            return "GENERAL"

        # 애매하면 INFO
        return "INFO"