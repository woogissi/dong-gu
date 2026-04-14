from typing import Literal
from rapidfuzz import fuzz


# 일반 대화 의도 타입 정의
GeneralIntent = Literal[
    "GREETING",          # 인사
    "THANKS",            # 감사
    "GOODBYE",           # 작별
    "BOT_IDENTITY",      # 챗봇 정체 질문
    "EMOTION",           # 배고파, 졸려, 힘들어 등
    "REACTION",          # ㅋㅋㅋ, 헐, 와 등
    "CONFIRMATION",      # 응, 네, 아니 등
    "SMALL_TALK",        # 뭐해?, 잘 지내? 등
    "FOOD",              # 밥 뭐야, 뭐 먹지, 점심 추천 등
    "GENERAL_FALLBACK"   # 위에 해당 안될 경우
]


class GeneralChatService:
    def __init__(self) -> None:
        """
        일반 대화 처리 서비스

        - 규칙 기반 + 유사도 기반 혼합 방식 사용
        - 1차: 키워드(뿌리 문자열) 매칭
        - 2차: RapidFuzz 유사도 비교
        """

        # 각 의도별 대표 문장 예시
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
                "너 누구야", "정체가 뭐야",
                "무슨 챗봇이야", "뭐하는 애야", "누구세요"
            ],
            "EMOTION": [
                "배고파", "졸려", "피곤해", "심심해",
                "힘들어", "스트레스 받아", "우울해", "지친다"
            ],
            "REACTION": [
                "ㅋㅋ", "ㅋㅋㅋ", "헐", "와", "오", "대박", "ㄷㄷ"
            ],
            "CONFIRMATION": [
                "응", "네", "넵", "맞아", "아니", "아니야", "싫어", "그래"
            ],
            "SMALL_TALK": [
                "뭐해", "뭐하냐", "잘 지내", "오늘 어때",
                "심심하지", "밥 먹었어"
            ],
            "FOOD": [
                "밥 뭐야", "뭐 먹지", "뭐 먹을까",
                "점심 뭐 먹지", "저녁 추천", "먹을거 추천",
                "메뉴 추천", "오늘 밥 뭐 먹지"
            ],
        }

        # 빠른 분류용 핵심 키워드
        self.greeting_roots = ["안녕", "하이", "반가", "ㅎㅇ", "헬로"]
        self.thanks_roots = ["감사", "고마", "고맙", "ㄳ", "땡큐"]
        self.goodbye_roots = ["잘가", "바이", "bye", "ㅂㅂ", "빠이", "수고", "종료", "끝"]

        # 너무 짧고 애매한 "너 뭐" 같은 표현은 제거
        self.identity_roots = ["너 누구", "너 뭐야", "정체가 뭐야", "무슨 챗봇", "누구세요"]

        self.emotion_roots = [
            "배고", "졸려", "피곤", "심심", "힘들", "우울", "스트레스", "지친",
            "짜증", "외롭", "지루"
        ]
        self.reaction_roots = ["ㅋㅋ", "ㅎㅎ", "헐", "와", "오", "대박", "ㄷㄷ", "앗"]
        self.confirmation_roots = ["응", "네", "넵", "예", "맞아", "아니", "아냐", "싫어", "그래"]
        self.small_talk_roots = ["뭐해", "뭐하", "잘 지내", "어때", "바빠", "밥 먹었", "심심하지"]

        # FOOD 의도 추가
        self.food_roots = ["밥", "먹", "식사", "점심", "저녁", "야식", "메뉴", "배달", "맛집"]

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

        # 1차: 키워드 기반 빠른 분류
        if self.contains_any_root(text, self.greeting_roots):
            return "GREETING"

        if self.contains_any_root(text, self.thanks_roots):
            return "THANKS"

        if self.contains_any_root(text, self.goodbye_roots):
            return "GOODBYE"

        # FOOD를 identity보다 먼저 검사
        if self.contains_any_root(text, self.food_roots):
            return "FOOD"

        if self.contains_any_root(text, self.emotion_roots):
            return "EMOTION"

        if self.contains_any_root(text, self.reaction_roots):
            return "REACTION"

        if self.contains_any_root(text, self.confirmation_roots):
            return "CONFIRMATION"

        if self.contains_any_root(text, self.small_talk_roots):
            return "SMALL_TALK"

        # identity는 뒤쪽에서 검사
        if self.contains_any_root(text, self.identity_roots):
            return "BOT_IDENTITY"

        # 2차: 유사도 기반 분류
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

        if general_intent == "EMOTION":
            return "아이고 그러셨군요. 필요하시면 학교 정보나 학사 관련 내용도 바로 도와드릴게요."

        if general_intent == "REACTION":
            return "ㅎㅎ 궁금한 게 있으면 편하게 말씀해주세요."

        if general_intent == "CONFIRMATION":
            return "좋아요. 이어서 궁금한 내용을 말씀해주세요."

        if general_intent == "SMALL_TALK":
            return "저는 동의대 신입생 안내를 도와드리는 중이에요. 궁금한 학교 정보가 있으면 말씀해주세요."

        if general_intent == "FOOD":
            return "오늘의 학식 알려드릴까요?"

        return "잘 이해하지 못했어요.\n간단한 단어로 질문해주시면 제가 더 잘 이해할 수 있어요!"

    def process_general_chat(self, utterance: str, user_id: str) -> str:
        general_intent = self.classify_general_intent(utterance)
        answer = self.build_answer(general_intent)

        from backend.app.utils.save_log import save_qa_log

        save_qa_log(
            user_id=user_id,
            question=utterance,
            answer=answer,
            retrieved_chunks=[],
            response_time=0.01,
            intent_type=f"GENERAL:{general_intent}"
        )

        return answer


general_chat_service = GeneralChatService()