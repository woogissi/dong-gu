# from fastapi import APIRouter, Request
# # 카카오 웹훅 처리 라우터
# router = APIRouter()
# @router.post("/webhook")
# async def kakao_webhook(request: Request):
#     body = await request.json()
#     # 사용자 입력 추출
#     utterance = body.get("userRequest", {}).get("utterance", "")
#     # 카카오 응답 포맷
#     return {
#         "version": "2.0",
#         "template": {
#             "outputs": [
#                 {
#                     "simpleText": {
#                         "text": f"입력한 내용: {utterance}"
#                     }
#                 }
#             ]
#         }
#    }

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