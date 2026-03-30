from typing import Literal
from rapidfuzz import fuzz


GeneralIntent = Literal[
    "GREETING",
    "THANKS",
    "GOODBYE",
    "BOT_IDENTITY",
    "GENERAL_FALLBACK",
]


class GeneralChatService:
    def __init__(self) -> None:
        self.intent_examples = {
            "GREETING": [
                "안녕", "안녕하세요", "안뇽", "하이", "ㅎㅇ",
                "반가워", "반갑습니다", "헬로", "하이루"
            ],
            "THANKS": [
                "고마워", "감사", "감사합니다", "ㄳ", "땡큐",
                "고맙다", "감사해", "고마워요"
            ],
            "GOODBYE": [
                "잘가", "바이", "bye", "ㅂㅂ", "종료", "끝",
                "다음에 봐", "수고해", "빠이", "안녕히가세요"
            ],
            "BOT_IDENTITY": [
                "너 뭐야", "너 누구야", "정체가 뭐야",
                "무슨 챗봇이야", "뭐하는 애야", "누구세요"
            ],
        }

        self.greeting_roots = ["안녕", "하이", "반가", "ㅎㅇ", "헬로"]
        self.thanks_roots = ["감사", "고마", "고맙", "ㄳ", "땡큐"]
        self.goodbye_roots = ["잘가", "바이", "bye", "ㅂㅂ", "빠이", "수고", "종료", "끝"]
        self.identity_roots = ["너 뭐", "너 누구", "정체", "챗봇", "뭐하는 애"]

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.strip().lower()
        text = " ".join(text.split())

        while text and text[-1] in {"?", "!", ".", "~"}:
            text = text[:-1].strip()

        return text

    def contains_any_root(self, text: str, roots: list[str]) -> bool:
        return any(root in text for root in roots)

    def similarity_score(self, text: str, examples: list[str]) -> int:
        max_score = 0

        for example in examples:
            score = fuzz.partial_ratio(text, example)
            if score > max_score:
                max_score = score

        return max_score

    def classify_general_intent(self, utterance: str) -> GeneralIntent:
        text = self.normalize_text(utterance)

        if not text:
            return "GENERAL_FALLBACK"

        # 1. 뿌리 문자열 우선
        if self.contains_any_root(text, self.greeting_roots):
            return "GREETING"

        if self.contains_any_root(text, self.thanks_roots):
            return "THANKS"

        if self.contains_any_root(text, self.goodbye_roots):
            return "GOODBYE"

        if self.contains_any_root(text, self.identity_roots):
            return "BOT_IDENTITY"

        # 2. 유사도 비교
        scores = {
            intent: self.similarity_score(text, examples)
            for intent, examples in self.intent_examples.items()
        }

        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        if best_score < 55:
            return "GENERAL_FALLBACK"

        return best_intent

    def build_answer(self, general_intent: GeneralIntent) -> str:
        if general_intent == "GREETING":
            return "안녕하세요! 동의대 신입생 정보 안내 챗봇 동구입니다."

        if general_intent == "THANKS":
            return "천만에요. 궁금한 학교 정보가 있으면 언제든 물어보세요."

        if general_intent == "GOODBYE":
            return "이용해주셔서 감사합니다. 다음에 또 찾아주세요."

        if general_intent == "BOT_IDENTITY":
            return "저는 동의대 신입생 정보 안내 챗봇 동구입니다."

        return "안녕하세요. 동의대 관련 정보가 궁금하면 질문해 주세요."

    def process_general_chat(self, utterance: str) -> str:
        general_intent = self.classify_general_intent(utterance)
        return self.build_answer(general_intent)


general_chat_service = GeneralChatService()