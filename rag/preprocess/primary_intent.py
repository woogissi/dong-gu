from __future__ import annotations

import re
from typing import Literal

from rag.preprocess.query_features import detect_domain


PrimaryIntent = Literal["GENERAL", "INFO", "PROFANITY"]

_PROFANITY_TERMS = {"시발", "시벌", "병신", "지랄"}

_SMALLTALK_EXACT = {"안녕", "안녕하세요", "고마워", "감사", "감사합니다", "하이", "hi", "hello"}

_INFO_HINTS = {
    "수강",
    "수강신청",
    "수업",
    "강의",
    "성적",
    "학점",
    "졸업",
    "장학",
    "장학금",
    "국가장학",
    "등록금",
    "납부",
    "기숙사",
    "생활관",
    "통학버스",
    "셔틀",
    "버스",
    "도서관",
    "학식",
    "식당",
    "학생식당",
    "학사",
    "휴학",
    "복학",
    "증명서",
    "신청",
    "기간",
    "일정",
    "시간",
    "방법",
    "위치",
    "요건",
    "동의대",
    "동의대학교",
    "교수",
    "이메일",
    "메일",
    "연구실",
    "학과",
    "전공",
    "건물",
    "호관",
    "정보공학관",
    "수덕전",
    "캠퍼스",
    "총장",
    "전화번호",
    "연락처",
    "행정실",
    "공지",
    "첨부파일",
    "pdf",
    "서식",
    "신청서",
    "취업",
    "현장실습",
    "ipp",
    "예비군",
}

_QUESTION_HINTS = {
    "알려줘",
    "알려주세요",
    "언제",
    "어디",
    "어떻게",
    "무엇",
    "뭐",
    "몇",
    "몇시",
    "누구",
    "운영",
    "가능",
    "확인",
    "위치",
    "전화번호",
    "연락처",
    "찾아줘",
}


class PrimaryIntentClassifier:
    def classify(self, utterance: str) -> PrimaryIntent:
        text = self._normalize(utterance)
        if not text:
            return "GENERAL"
        if any(term in text for term in _PROFANITY_TERMS):
            return "PROFANITY"
        if text in _SMALLTALK_EXACT:
            return "GENERAL"

        domain, _ = detect_domain(text)
        if domain:
            return "INFO"
        if any(term in text for term in _INFO_HINTS):
            return "INFO"
        if re.search(r"\d+\s*번\s*건물|\d+\s*층|\d+\s*학년", text):
            return "INFO"
        if re.search(r"\d{2,4}[-.]\d{3,4}[-.]\d{4}", text):
            return "INFO"
        if any(term in text for term in _QUESTION_HINTS):
            return "INFO"
        return "GENERAL"

    def _normalize(self, utterance: str) -> str:
        return " ".join((utterance or "").strip().lower().split())
