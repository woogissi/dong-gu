import re
from typing import Literal

from rapidfuzz import fuzz


# 일반 대화 의도 타입 정의
# → LLM이 아니라 규칙 기반으로 분류할 라벨들
GeneralIntent = Literal[
    "GREETING",          # 인사
    "THANKS",            # 감사
    "GOODBYE",           # 작별
    "BOT_IDENTITY",      # 챗봇 정체 질문
    "EMOTION",           # 감정 표현 (배고파, 힘들어 등)
    "REACTION",          # 감탄/반응 (ㅋㅋ, 와 등)
    "CONFIRMATION",      # 긍정/부정 (응, 네, 아니 등)
    "SMALL_TALK",        # 일상 대화 (뭐해?, 잘 지내?)
    "GENERAL_FALLBACK",  # 분류 실패 시
]


class GeneralChatService:
    def __init__(self) -> None:
        """
        일반 대화 처리 서비스

        설계 구조:
        1차 → 규칙 기반 (빠르고 정확)
        2차 → 유사도 기반 (애매한 문장 보완)

        + 짧은 입력은 오분류 방지 로직 포함
        """

        # -----------------------------
        # 2차 분류용: 대표 문장 샘플
        # → RapidFuzz 비교 대상
        # -----------------------------
        self.intent_examples: dict[GeneralIntent, list[str]] = {
            "GREETING": ["안녕", "안녕하세요", "안뇽", "하이", "ㅎㅇ", "반가워", "헬로"],
            "THANKS": ["고마워", "감사합니다", "ㄳ", "땡큐"],
            "GOODBYE": ["잘가", "바이", "bye", "ㅂㅂ", "끝"],
            "BOT_IDENTITY": ["너 뭐야", "너 누구야", "챗봇이야"],
            "EMOTION": ["배고파", "피곤해", "힘들어", "우울해"],
            "REACTION": ["ㅋㅋ", "헐", "와", "대박"],
            "CONFIRMATION": ["응", "네", "맞아", "아니"],
            "SMALL_TALK": ["뭐해", "잘 지내", "오늘 어때"],
        }

        # -----------------------------
        # 1차 분류용: 핵심 키워드 (root 기반)
        # → substring 포함 여부로 빠르게 분류
        # -----------------------------
        self.root_keywords: dict[GeneralIntent, list[str]] = {
            "GREETING": ["안녕", "하이", "반가", "ㅎㅇ"],
            "THANKS": ["감사", "고마"],
            "GOODBYE": ["잘가", "바이", "ㅂㅂ"],
            "BOT_IDENTITY": ["너 뭐", "너 누구", "챗봇"],
            "EMOTION": ["배고", "졸려", "힘들", "우울"],
            "SMALL_TALK": ["뭐해", "잘 지내", "어때"],
        }

        # 짧은 단독 입력만 허용 (오분류 방지)
        self.reaction_words = {"ㅋㅋ", "ㅋㅋㅋ", "ㅎㅎ", "헐", "와", "오"}
        self.confirmation_words = {"응", "네", "넵", "맞아", "아니", "그래"}

        # -----------------------------
        # 의도별 응답 템플릿
        # -----------------------------
        self.answers: dict[GeneralIntent, str] = {
            "GREETING": "안녕하세요! 동의대 신입생 정보 안내 챗봇 동구입니다.",
            "THANKS": "천만에요. 궁금한 학교 정보가 있으면 언제든 물어보세요.",
            "GOODBYE": "이용해주셔서 감사합니다. 다음에 또 찾아주세요.",
            "BOT_IDENTITY": "저는 동의대 신입생 정보 안내 챗봇 동구입니다.",
            "EMOTION": "아이고 그러셨군요. 필요하시면 학교 정보도 도와드릴게요.",
            "REACTION": "ㅎㅎ 궁금한 게 있으면 말씀해주세요.",
            "CONFIRMATION": "좋아요. 이어서 질문해주세요.",
            "SMALL_TALK": "저는 학교 정보를 안내하고 있어요. 궁금한 거 있으신가요?",
            "GENERAL_FALLBACK": "잘 이해하지 못했어요.\n학교 관련 질문을 해주시면 더 정확히 도와드릴게요!",
        }

    def normalize_text(self, text: str) -> str:
        """
        입력 전처리

        - 소문자 변환
        - 공백 정리
        - 문장 끝 특수문자 제거
        """
        if not text:
            return ""

        text = text.strip().lower()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[?!.~]+$", "", text)

        return text

    def is_short_exact_match(self, text: str, words: set[str]) -> bool:
        """
        짧은 단어 단독 입력인지 확인

        ex) "응" → True
            "응 수강신청" → False (오분류 방지)
        """
        return text in words

    def contains_any_root(self, text: str, roots: list[str]) -> bool:
        """
        root 키워드 포함 여부 확인

        ex) "안녕하세요" → "안녕" 포함 → True
        """
        return any(root in text for root in roots)

    def similarity_score(self, text: str, examples: list[str]) -> int:
        """
        RapidFuzz partial_ratio 기반 유사도 계산

        → 가장 높은 점수 반환
        """
        return max(
            (fuzz.partial_ratio(text, example) for example in examples),
            default=0,
        )

    def classify_by_rule(self, text: str) -> GeneralIntent | None:
        """
        1차: 규칙 기반 분류

        - 빠르고 정확
        - 짧은 단어는 반드시 단독 입력일 때만 허용
        """

        # 짧은 긍정/부정
        if self.is_short_exact_match(text, self.confirmation_words):
            return "CONFIRMATION"

        # 짧은 감탄
        if self.is_short_exact_match(text, self.reaction_words):
            return "REACTION"

        # root 키워드 기반 분류
        for intent, roots in self.root_keywords.items():
            if self.contains_any_root(text, roots):
                return intent

        return None

    def classify_by_similarity(self, text: str) -> GeneralIntent:
        """
        2차: 유사도 기반 분류 (fallback)

        - 규칙으로 못 잡은 문장 처리
        - 너무 짧으면 오분류 많아서 제외
        """

        if len(text) < 3:
            return "GENERAL_FALLBACK"

        scores = {
            intent: self.similarity_score(text, examples)
            for intent, examples in self.intent_examples.items()
        }

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # 임계값 이하 → fallback
        if best_score < 65:
            return "GENERAL_FALLBACK"

        return best_intent

    def classify_general_intent(self, utterance: str) -> GeneralIntent:
        """
        전체 분류 흐름

        1. 전처리
        2. 규칙 기반 분류
        3. 실패 시 유사도 분류
        """

        text = self.normalize_text(utterance)

        if not text:
            return "GENERAL_FALLBACK"

        # 1차
        rule_intent = self.classify_by_rule(text)
        if rule_intent:
            return rule_intent

        # 2차
        return self.classify_by_similarity(text)

    def build_answer(self, general_intent: GeneralIntent) -> str:
        """
        의도 → 응답 매핑
        """
        return self.answers.get(general_intent, self.answers["GENERAL_FALLBACK"])

    def process_general_chat(self, utterance: str, user_id: str) -> str:
        """
        일반 대화 전체 처리 흐름

        1. 의도 분류
        2. 응답 생성
        3. 로그 저장
        """

        general_intent = self.classify_general_intent(utterance)
        answer = self.build_answer(general_intent)

        return answer


# 싱글톤처럼 사용
general_chat_service = GeneralChatService()