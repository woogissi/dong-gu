import re
from typing import Literal
from backend.app.utils.profanity_filter import contains_profanity #profanity_filter랑 연결해줌


# 1차 분류 결과 타입 정의
PrimaryIntent = Literal["GENERAL", "INFO", "PROFANITY"] #욕설 필터 추가


class PrimaryIntentClassifier:
    """
    1차 의도 분류기

    역할:
    - 사용자 입력을 "일반 대화" vs "정보성 질문"으로 나눔

    분류 기준:
    1. 정보 관련 키워드 or 패턴이 있으면 → INFO
    2. 아니면 → GENERAL

    ※ INFO를 우선적으로 잡는 구조 (RAG로 보내기 위함)
    """

    def __init__(self) -> None:
        """
        정보성 질문을 판단하기 위한 기준 데이터 정의
        """

        # 정보성 키워드 (질문 느낌 + 학교 도메인 키워드)
        self.info_keywords = {
            # 질문 표현
            "알려줘", "알려주세요", "언제", "어디", "어디야", "어디임",
            "어떻게", "신청", "기간", "날짜", "시간", "운영", "운영시간",
            "방법", "어디서", "가능", "몇시", "몇 시", "며칠", "일정", "일정표",
            "위치", "지도", "장소",

            # 학교 관련 키워드 (도메인 특화)
            "수강", "수강신청", "장학", "장학금", "기숙사", "도서관",
            "학점", "졸업", "학사", "학사일정", "교육과정", "강의실",
            "등록금", "휴학", "복학", "성적", "학식", "동아리", "공지", "공지사항",
            "증명서", "수업", "강의", "시간표", "학과",

            # 시간 관련 표현
            "오늘", "내일", "이번주", "다음주", "이번 학기", "다음 학기",
            "1학기", "2학기",
            "1월", "2월", "3월", "4월", "5월", "6월",
            "7월", "8월", "9월", "10월", "11월", "12월",
        }

        # 정규식 패턴 (숫자 기반 시간 표현 등)
        self.info_patterns = [
            r"\d+\s*월",     # ex) 3월
            r"\d+\s*일",     # ex) 15일
            r"\d+\s*시",     # ex) 10시
            r"\d+\s*학기",   # ex) 1학기
            r"(이번|다음)\s*주",
            r"(이번|다음)\s*학기",
        ]

    def normalize_text(self, text: str) -> str:
        """
        입력 텍스트 정규화

        - 소문자 변환
        - 공백 정리
        - 문장 끝 특수문자 제거
        """
        if not text:
            return ""

        text = text.strip().lower()
        text = " ".join(text.split())
        text = re.sub(r"[?!.~]+$", "", text).strip()
        return text

    def is_info(self, text: str) -> bool:
        """
        정보성 질문인지 판단하는 핵심 함수

        1. 키워드 포함 여부 체크
        2. 정규식 패턴 매칭
        """

        # 키워드 기반 판단
        if any(keyword in text for keyword in self.info_keywords):
            return True

        # 패턴 기반 판단 (날짜/시간 등)
        if any(re.search(pattern, text) for pattern in self.info_patterns):
            return True

        return False

    def classify(self, utterance: str) -> PrimaryIntent:
        """
        최종 의도 분류 함수

        흐름:
        1. 텍스트 정규화
        2. 정보성 여부 판단
        3. INFO / GENERAL 반환
        """

        text = self.normalize_text(utterance)

        #욕설을 먼저 검사해야 욕설+정보성 질문 들어와도 걸러내기 가능
        if contains_profanity(text):
            return "PROFANITY"

        # 입력이 비어있으면 정보성으로 처리 (fallback을 RAG로 보내기 위함)
        if not text:
            return "INFO"

        # 정보성 질문이면 INFO
        if self.is_info(text):
            return "INFO"

        # 나머지는 GENERAL (일반 대화)
        return "GENERAL"