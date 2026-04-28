print("🔥 실제 routers/chat.py 로드됨")

from fastapi import APIRouter
from backend.app.utils.kakao_template import kakao_response
from backend.app.utils.intent_classifier import PrimaryIntentClassifier

router = APIRouter()
classifier = PrimaryIntentClassifier()

@router.post("/kakao/webhook")
@router.post("/api/kakao/webhook")
async def kakao_webhook(data: dict):
    user_text = data["userRequest"]["utterance"]

    intent = classifier.classify(user_text)

    if intent == "PROFANITY":
        answer = "부적절한 표현은 사용할 수 없습니다."
    elif intent == "INFO":
        answer = f"정보성 질문입니다: {user_text}"
    else:
        answer = f"일반 대화입니다: {user_text}"

    return kakao_response(answer)