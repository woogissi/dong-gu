from typing import Literal
from rapidfuzz import fuzz


# 일반 대화 의도 타입 정의 (타입 안정성 + 가독성)
GeneralIntent = Literal[
    "GREETING",        # 인사
    "THANKS",          # 감사
    "GOODBYE",         # 작별
    "BOT_IDENTITY",    # 챗봇 정체 질문
    "GENERAL_FALLBACK" # 위에 해당 안될 경우
]


class GeneralChatService:
    def __init__(self) -> None:
        """
        일반 대화 처리 서비스

        - 규칙 기반 + 유사도 기반 혼합 방식 사용
        - 1차: 키워드(뿌리 문자열) 매칭
        - 2차: RapidFuzz 유사도 비교
        """

        # 각 의도별 대표 문장 예시 (유사도 비교용)
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

        # 빠른 분류를 위한 "핵심 키워드(뿌리 문자열)"
        # → 완전 일치가 아니라 "포함"만 되어도 잡아냄
        self.greeting_roots = ["안녕", "하이", "반가", "ㅎㅇ", "헬로"]
        self.thanks_roots = ["감사", "고마", "고맙", "ㄳ", "땡큐"]
        self.goodbye_roots = ["잘가", "바이", "bye", "ㅂㅂ", "빠이", "수고", "종료", "끝"]
        self.identity_roots = ["너 뭐", "너 누구", "정체", "챗봇", "뭐하는 애"]

    def normalize_text(self, text: str) -> str:
        """
        입력 텍스트 정규화

        - 소문자 변환
        - 공백 정리
        - 문장 끝 특수문자 제거 (?, !, ~ 등)
        """
        if not text:
            return ""

        text = text.strip().lower()
        text = " ".join(text.split())

        # 문장 끝 불필요한 기호 제거
        while text and text[-1] in {"?", "!", ".", "~"}:
            text = text[:-1].strip()

        return text

    def contains_any_root(self, text: str, roots: list[str]) -> bool:
        """
        특정 키워드(뿌리 문자열)가 포함되어 있는지 확인
        """
        return any(root in text for root in roots)

    def similarity_score(self, text: str, examples: list[str]) -> int:
        """
        RapidFuzz를 이용한 유사도 계산

        - partial_ratio 사용 → 부분 일치에도 강함
        - 여러 예시 중 가장 높은 점수 반환
        """
        max_score = 0

        for example in examples:
            score = fuzz.partial_ratio(text, example)
            if score > max_score:
                max_score = score

        return max_score

    def classify_general_intent(self, utterance: str) -> GeneralIntent:
        """
        일반 대화 의도 분류 핵심 함수

        흐름:
        1. 텍스트 정규화
        2. 키워드 기반 빠른 분류
        3. 유사도 기반 보정
        """
        text = self.normalize_text(utterance)

        # 입력이 비어있으면 fallback
        if not text:
            return "GENERAL_FALLBACK"

        # -----------------------------
        # 1차: 키워드 기반 빠른 분류
        # -----------------------------
        if self.contains_any_root(text, self.greeting_roots):
            return "GREETING"

        if self.contains_any_root(text, self.thanks_roots):
            return "THANKS"

        if self.contains_any_root(text, self.goodbye_roots):
            return "GOODBYE"

        if self.contains_any_root(text, self.identity_roots):
            return "BOT_IDENTITY"

        # -----------------------------
        # 2차: 유사도 기반 분류
        # -----------------------------
        scores = {
            intent: self.similarity_score(text, examples)
            for intent, examples in self.intent_examples.items()
        }

        # 가장 높은 점수의 intent 선택
        best_intent = max(scores, key=scores.get)
        best_score = scores[best_intent]

        # 임계값 이하이면 fallback 처리
        if best_score < 55:
            return "GENERAL_FALLBACK"

        return best_intent

    def build_answer(self, general_intent: GeneralIntent) -> str:
        """
        의도에 따른 응답 생성
        """
        if general_intent == "GREETING":
            return "안녕하세요! 동의대 신입생 정보 안내 챗봇 동구입니다."

        if general_intent == "THANKS":
            return "천만에요. 궁금한 학교 정보가 있으면 언제든 물어보세요."

        if general_intent == "GOODBYE":
            return "이용해주셔서 감사합니다. 다음에 또 찾아주세요."

        if general_intent == "BOT_IDENTITY":
            return "저는 동의대 신입생 정보 안내 챗봇 동구입니다."

        # fallback 응답
        return "안녕하세요. 동의대 관련 정보가 궁금하면 질문해 주세요."

    def process_general_chat(self, utterance: str, user_id: str) -> str:
        """
        일반 대화 전체 처리 흐름

        1. 의도 분류
        2. 응답 생성
        3. DB 저장
        """
        general_intent = self.classify_general_intent(utterance)
        answer = self.build_answer(general_intent)

        from backend.app.utils.save_log import save_qa_log

        save_qa_log(
            user_id=user_id,
            question=utterance,
            answer=answer,
            retrieved_chunks=[],
            response_time=0.01,
            intent_type="GENERAL"
        )

        return answer


# 외부에서 바로 사용할 수 있도록 싱글톤처럼 생성
general_chat_service = GeneralChatService()