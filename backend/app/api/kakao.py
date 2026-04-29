from fastapi import APIRouter, Request

from backend.app.api.chat import general_chat_service
from backend.app.utils.intent_classifier import PrimaryIntentClassifier
from backend.app.utils.user_lock import acquire_user_lock, release_user_lock
from backend.app.utils.kakao_template import kakao_response, kakao_text_card
from backend.app.utils.kakao_ui import (
    get_category_from_utterance,
    get_quick_replies_by_category,
    get_link_url_by_category,
    get_title_by_category,
)
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query


router = APIRouter(tags=["kakao"])

primary_intent_classifier = PrimaryIntentClassifier()
chat_pipeline = ChatPipeline()


@router.post("/webhook")
async def kakao_webhook(request: Request):
    body = await request.json()

    user_id = body.get("userRequest", {}).get("user", {}).get("id", "unknown")
    utterance = body.get("userRequest", {}).get("utterance", "").strip()

    if not utterance:
        return kakao_response("질문 내용을 입력해주세요.")

    if not acquire_user_lock(user_id):
        return kakao_response(
            "이전 질문을 처리 중입니다.\n잠시 후 다시 질문해주세요."
        )

    try:
        primary_intent = primary_intent_classifier.classify(utterance)

        if primary_intent == "PROFANITY":
            return kakao_response("부적절한 표현은 사용할 수 없어요.")

        if primary_intent == "GENERAL":
            answer_text = general_chat_service.process_general_chat(
                utterance=utterance,
                user_id=user_id,
            )
            return kakao_response(answer_text)

        # 🔥 RAG 실행
        result = chat_pipeline.run(Query(text=utterance))

        # 🔥 dict 변환
        if isinstance(result, dict):
            result_dict = result
        elif hasattr(result, "model_dump"):
            result_dict = result.model_dump()
        elif hasattr(result, "to_dict"):
            result_dict = result.to_dict()
        else:
            result_dict = {}

        # 🔥 answer 추출
        answer_text = (
            result_dict.get("answer_text")
            or result_dict.get("answer")
            or getattr(result, "answer_text", None)
            or getattr(result, "answer", None)
        )

        # 🔥 category 추출
        category = (
            result_dict.get("category")
            or getattr(result, "category", None)
        )

        # 🔥 fallback (핵심)
        if not category:
            category = get_category_from_utterance(utterance)

        # 🔥 답변 정리
        answer_text = (answer_text or "답변을 생성하지 못했습니다.").strip()
        answer_text = answer_text.replace("[DUMMY ANSWER]", "").strip()

        if "문맥:" in answer_text:
            answer_text = answer_text.split("문맥:")[0].strip()

        # 🔥 UI 생성
        quick_replies = get_quick_replies_by_category(category)
        link_url = get_link_url_by_category(category)

        print("DEBUG category:", category)
        print("DEBUG quick_replies:", quick_replies)

        answer_text = f"{answer_text}\n\n사이트 바로가기: {link_url}"

        title = get_title_by_category(category)

        return kakao_text_card(
            title=title,
            description=answer_text,
            link_url=link_url,
            quick_replies=quick_replies
        )

    except Exception as e:
        print(f"[ERROR] kakao_webhook: {e}")
        return kakao_response(
            "질문 처리 중 오류가 발생했어요.\n잠시 후 다시 시도해주세요."
        )

    finally:
        release_user_lock(user_id)