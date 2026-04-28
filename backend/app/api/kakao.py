from fastapi import APIRouter, Request

from backend.app.api.chat import general_chat_service
from backend.app.utils.intent_classifier import PrimaryIntentClassifier
from backend.app.utils.user_lock import acquire_user_lock, release_user_lock
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

    if not utterance:
        return kakao_simple_text("질문 내용을 입력해주세요.")

    if not acquire_user_lock(user_id):
        return kakao_simple_text(
            "이전 질문을 처리 중입니다.\n잠시 후 다시 질문해주세요."
        )

    try:
        primary_intent = primary_intent_classifier.classify(utterance)

        if primary_intent == "PROFANITY":
            return kakao_simple_text("부적절한 표현은 사용할 수 없어요.")

        if primary_intent == "GENERAL":
            answer_text = general_chat_service.process_general_chat(
                utterance=utterance,
                user_id=user_id,
            )
            return kakao_simple_text(answer_text)

        result = chat_pipeline.run(Query(text=utterance))
        
        if isinstance(result, dict):
            
            answer_text = result.get("answer_text") or result.get("answer")
            
        else:
            answer_text = getattr(result, "answer_text", None) or getattr(result, "answer", None)

        if not answer_text:
            answer_text = "답변을 생성하지 못했습니다."

        return kakao_simple_text(answer_text)

    except Exception as e:
        print(f"[ERROR] kakao_webhook: {e}")
        return kakao_simple_text(
            "질문 처리 중 오류가 발생했어요.\n잠시 후 다시 시도해주세요."
        )

    finally:
        release_user_lock(user_id)  