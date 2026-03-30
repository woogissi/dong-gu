from fastapi import APIRouter, Request

from backend.app.utils.intent_classifier import PrimaryIntentClassifier
from backend.app.api.chat import general_chat_service

router = APIRouter(tags=["kakao"])

primary_intent_classifier = PrimaryIntentClassifier()


def kakao_simple_text(text: str) -> dict:
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }


@router.post("/webhook")
async def kakao_webhook(request: Request):
    body = await request.json()
    utterance = body.get("userRequest", {}).get("utterance", "").strip()

    primary_intent = primary_intent_classifier.classify(utterance)

    if primary_intent == "GENERAL":
        answer_text = general_chat_service.process_general_chat(utterance)
        return kakao_simple_text(answer_text)

    return kakao_simple_text(
        f"정보성 질문으로 분류되었습니다.\n입력: {utterance}"
    )