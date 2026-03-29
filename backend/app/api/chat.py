from typing import Literal

GeneralIntent = Literal[
    "GREETING",
    "THANKS",
    "GOODBYE",
    "GENERAL_FALLBACK",
]


class GeneralChatService:
    def __init__(self) -> None:
        self.greeting_words = {
            "안녕", "안녕하세요", "안뇽", "하이", "ㅎㅇ"
        }
        self.thanks_words = {
            "고마워", "감사", "감사합니다", "ㄳ", "땡큐"
        }
        self.goodbye_words = {
            "잘가", "바이", "bye", "ㅂㅂ", "종료", "끝"
        }

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.strip().lower()
        text = " ".join(text.split())

        while text and text[-1] in {"?", "!", ".", "~"}:
            text = text[:-1].strip()

        return text

    def classify_general_intent(self, utterance: str) -> GeneralIntent:
        text = self.normalize_text(utterance)

        if text in self.greeting_words:
            return "GREETING"

        if text in self.thanks_words:
            return "THANKS"

        if text in self.goodbye_words:
            return "GOODBYE"

        return "GENERAL_FALLBACK"

    def build_answer(self, general_intent: GeneralIntent) -> str:
        if general_intent == "GREETING":
            return "안녕하세요! 동의대 신입생 정보 안내 챗봇 동구입니다."

        if general_intent == "THANKS":
            return "천만에요. 궁금한 학교 정보가 있으면 언제든 물어보세요."

        if general_intent == "GOODBYE":
            return "이용해주셔서 감사합니다. 다음에 또 찾아주세요."

        return "안녕하세요. 동의대 관련 정보가 궁금하면 질문해 주세요."

    def process_general_chat(self, utterance: str) -> str:
        general_intent = self.classify_general_intent(utterance)
        return self.build_answer(general_intent)


general_chat_service = GeneralChatService()