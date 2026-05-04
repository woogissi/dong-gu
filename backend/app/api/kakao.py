import time
from fastapi import APIRouter, Request, BackgroundTasks

from backend.app.utils.callback import kakao_callback
from backend.app.database.query_logs import create_query_log, update_query_intent
from backend.app.database.response_logs import save_response_log
from backend.app.api.chat import general_chat_service
from backend.app.utils.intent_classifier import PrimaryIntentClassifier
from backend.app.utils.user_lock import acquire_user_lock, release_user_lock
from backend.app.utils.kakao_template import kakao_response, kakao_text_card
from backend.app.utils.kakao_ui import (
    get_category_from_utterance,
    get_quick_replies_by_context,
    get_link_url_by_category,
    get_title_by_category,
)
from rag.schemas.query import Query


router = APIRouter(tags=["kakao"])

primary_intent_classifier = PrimaryIntentClassifier()
chat_pipeline = None


def get_chat_pipeline():
    global chat_pipeline
    if chat_pipeline is None:
        from rag.pipeline.chat_pipeline import ChatPipeline
        chat_pipeline = ChatPipeline()
    return chat_pipeline


@router.post("/webhook")
async def kakao_webhook(request: Request, background_tasks: BackgroundTasks):
    start_time = time.time()
    callback_mode = False
    request_id = None

    body = await request.json()

    callback_url = body.get("userRequest", {}).get("callbackUrl")
    user_id = body.get("userRequest", {}).get("user", {}).get("id", "unknown")
    utterance = body.get("userRequest", {}).get("utterance", "").strip()

    if not utterance:
        return kakao_response("질문 내용을 입력해주세요.")

    if not acquire_user_lock(user_id):
        return kakao_response("이전 질문을 처리 중입니다.\n잠시 후 다시 질문해주세요.")

    try:
        request_id = create_query_log(user_id=user_id, question=utterance)

        intent = primary_intent_classifier.classify(utterance)
        update_query_intent(request_id=request_id, intent_type=intent)

        if intent == "PROFANITY":
            return kakao_response("부적절한 표현은 사용할 수 없어요.")

        if intent == "GENERAL":
            answer = general_chat_service.process_general_chat(
                utterance=utterance,
                user_id=user_id,
            )
            save_response_log(
                request_id=request_id,
                answer_text=answer,
                success=True,
                error_message=None,
                response_time_ms=int((time.time() - start_time) * 1000),
            )
            return kakao_response(answer)

        if callback_url:
            callback_mode = True

            background_tasks.add_task(
                process_info_with_callback,
                callback_url,
                request_id,
                user_id,
                utterance,
                start_time,
            )

            return {
                "version": "2.0",
                "useCallback": True,
                "data": {
                    "text": "답변을 생성 중입니다. 잠시만 기다려주세요."
                },
            }

        return kakao_response(
            "콜백 URL이 전달되지 않았습니다.\n카카오톡 채널에서 다시 테스트해주세요."
        )

    except Exception as e:
        print(f"[ERROR] kakao_webhook: {e}")
        return kakao_response("오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

    finally:
        if not callback_mode:
            release_user_lock(user_id)


def process_info_with_callback(callback_url, request_id, user_id, utterance, start_time):
    try:
        result = get_chat_pipeline().run(Query(text=utterance))

        response_body, final_answer = build_info_response(result, utterance)

        kakao_callback(callback_url, response_body)

        save_response_log(
            request_id=request_id,
            answer_text=final_answer,
            success=True,
            error_message=None,
            response_time_ms=int((time.time() - start_time) * 1000),
        )

    except Exception as e:
        print(f"[ERROR] callback: {e}")

        kakao_callback(
            callback_url,
            kakao_response("답변 생성 중 오류가 발생했습니다."),
        )

        save_response_log(
            request_id=request_id,
            answer_text=None,
            success=False,
            error_message=str(e),
            response_time_ms=int((time.time() - start_time) * 1000),
        )

    finally:
        release_user_lock(user_id)


def build_info_response(result, utterance):
    if isinstance(result, dict):
        result_dict = result
    elif hasattr(result, "model_dump"):
        result_dict = result.model_dump()
    elif hasattr(result, "to_dict"):
        result_dict = result.to_dict()
    else:
        result_dict = {}

    answer = (
        result_dict.get("answer_text")
        or result_dict.get("answer")
        or getattr(result, "answer_text", None)
        or getattr(result, "answer", None)
        or "답변을 생성하지 못했습니다."
    )

    category = (
        result_dict.get("category")
        or getattr(result, "category", None)
        or get_category_from_utterance(utterance)
    )

    answer = answer.strip()
    answer = answer.replace("[DUMMY ANSWER]", "").strip()

    if "문맥:" in answer:
        answer = answer.split("문맥:")[0].strip()

    title = get_title_by_category(category)
    link = get_link_url_by_category(category)
    quick = get_quick_replies_by_context(category, utterance)

    final = f"{answer}\n\n사이트 바로가기: {link}"

    return (
        kakao_text_card(
            title=title,
            description=final,
            link_url=link,
            quick_replies=quick,
        ),
        final,
    )