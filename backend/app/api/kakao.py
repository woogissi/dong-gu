from fastapi import APIRouter, Request

# 카카오 웹훅 처리 라우터
router = APIRouter()

@router.post("/webhook")
async def kakao_webhook(request: Request):
    body = await request.json()

    # 사용자 입력 추출
    utterance = body.get("userRequest", {}).get("utterance", "")

    # 카카오 응답 포맷
    return {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": f"입력한 내용: {utterance}"
                    }
                }
            ]
        }
    }