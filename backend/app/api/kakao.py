from fastapi import APIRouter, Request

from backend.app.api.chat import general_chat_service
from backend.app.utils.intent_classifier import PrimaryIntentClassifier
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query

router = APIRouter(tags=["kakao"])

primary_intent_classifier = PrimaryIntentClassifier()
chat_pipeline = ChatPipeline()


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

    user_id = body.get("userRequest", {}).get("user", {}).get("id", "unknown")
    utterance = body.get("userRequest", {}).get("utterance", "").strip()

    primary_intent = primary_intent_classifier.classify(utterance)

    if primary_intent == "GENERAL":
        answer_text = general_chat_service.process_general_chat(
            utterance=utterance,
            user_id=user_id,
        )
        return kakao_simple_text(answer_text)

    result = chat_pipeline.run(Query(text=utterance))
    return kakao_simple_text(result.answer)
