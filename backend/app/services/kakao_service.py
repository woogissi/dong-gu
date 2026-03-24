from app.schemas.chat import ChatRequest
from app.services.chat_service import handle_chat


def parse_kakao_request(body: dict) -> ChatRequest:
    user_request = body.get("userRequest", {})
    user = user_request.get("user", {})

    return ChatRequest(
        user_id=user.get("id"),
        session_id=user_request.get("conversationId"),
        channel="kakao",
        message=user_request.get("utterance", "") or "질문이 비어 있습니다.",
    )


def build_kakao_simple_text(text: str) -> dict:
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text,
                    }
                }
            ]
        },
    }


async def handle_kakao(body: dict) -> dict:
    req = parse_kakao_request(body)
    result = await handle_chat(req)
    return build_kakao_simple_text(result.answer)
