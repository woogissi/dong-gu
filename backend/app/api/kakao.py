from fastapi import APIRouter, Request

# 1차 의도 분류기 (일반대화 / 정보성 질문 구분)
from backend.app.utils.intent_classifier import PrimaryIntentClassifier

# 일반 대화 처리 서비스
from backend.app.api.chat import general_chat_service


# 카카오 관련 API 라우터 생성
router = APIRouter(tags=["kakao"])

# 의도 분류기 인스턴스 생성 (서버 시작 시 1회 생성)
primary_intent_classifier = PrimaryIntentClassifier()


def kakao_simple_text(text: str) -> dict:
    """
    카카오 챗봇 응답 포맷 (simpleText 형태)으로 변환하는 함수
    """
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
    """
    카카오 챗봇에서 호출하는 Webhook 엔드포인트

    전체 흐름:
    1. 사용자 발화 추출
    2. 1차 의도 분류 (GENERAL / INFO)
    3. GENERAL이면 일반 대화 처리
    4. INFO이면 (현재는) 안내 메시지 반환
    """

    # 카카오에서 보낸 JSON 요청 데이터 받기
    body = await request.json()

    # 사용자 입력(utterance) 추출
    # 안전하게 get() 체인 사용 (키 없을 경우 대비)
    utterance = body.get("userRequest", {}).get("utterance", "").strip()

    # 1차 의도 분류 수행
    primary_intent = primary_intent_classifier.classify(utterance)

    # -----------------------------
    # 1. 일반 대화 처리
    # -----------------------------
    if primary_intent == "GENERAL":
        # chat.py로 넘겨서 상세 처리
        answer_text = general_chat_service.process_general_chat(utterance)

        # 카카오 응답 포맷으로 변환 후 반환
        return kakao_simple_text(answer_text)

    # -----------------------------
    # 2. 정보성 질문 처리 (현재는 임시)
    # -----------------------------
    # 추후 RAG 파이프라인으로 넘길 예정
    return kakao_simple_text(
        f"정보성 질문으로 분류되었습니다.\n입력: {utterance}"
    )