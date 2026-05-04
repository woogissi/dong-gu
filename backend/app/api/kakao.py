import time
from fastapi import APIRouter, BackgroundTasks, Request

from backend.app.utils.callback import kakao_callback
from backend.app.database.query_logs import create_query_log, update_query_intent
from backend.app.database.response_logs import save_response_log
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


def add_response_log_task(background_tasks, request_id, answer_text, success, response_time_ms, error_message=None):
    if not request_id:
        return

    if background_tasks is None:
        save_response_log(
            request_id,
            answer_text,
            success,
            error_message,
            response_time_ms,
        )
        return

    background_tasks.add_task(
        save_response_log,
        request_id,
        answer_text,
        success,
        error_message,
        response_time_ms,
    )


@router.post("/webhook")
async def kakao_webhook(request: Request, background_tasks: BackgroundTasks = None):
    start_time = time.time()
    request_id = None
    callback_mode = False

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

        # 욕설
        if intent == "PROFANITY":
            return kakao_response("부적절한 표현은 사용할 수 없어요.")

        # 일반 대화
        if intent == "GENERAL":
            answer = general_chat_service.process_general_chat(
                utterance=utterance,
                user_id=user_id,
            )
            return kakao_response(answer)

        # -------------------------
        # 정보성 질문 (콜백)
        # -------------------------
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

        # 콜백 URL이 없는 경우에도 RAG -> Ollama 파이프라인을 동기로 실행해 응답합니다.
        response_body, final_answer, success = process_info_sync(utterance)
        add_response_log_task(
            background_tasks,
            request_id,
            final_answer,
            success,
            int((time.time() - start_time) * 1000),
        )
        return response_body

    except Exception as e:
        print(f"[ERROR] kakao_webhook: {e}")
        return kakao_response("오류가 발생했습니다. 잠시 후 다시 시도해주세요.")

    finally:
        if not callback_mode:
            release_user_lock(user_id)


# -------------------------
# 콜백 처리
# -------------------------

def process_info_with_callback(callback_url, request_id, user_id, utterance, start_time):
    try:
        result = get_chat_pipeline().run(Query(text=utterance))

        response_body, final_answer = build_info_response(result, utterance)

        kakao_callback(callback_url, response_body)

        save_response_log(
            request_id=request_id,
            answer_text=final_answer,
            success=_result_success(result),
            response_time_ms=int((time.time() - start_time) * 1000),
            error_message=None,
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
            response_time_ms=int((time.time() - start_time) * 1000),
            error_message=str(e),
        )

    finally:
        release_user_lock(user_id)


def process_info_sync(utterance: str):
    result = get_chat_pipeline().run(Query(text=utterance))
    response_body, final_answer = build_info_response(result, utterance)
    success = _result_success(result)
    return response_body, final_answer, success


def _result_success(result) -> bool:
    if isinstance(result, dict):
        return bool(result.get("success", True))
    return bool(getattr(result, "success", True))


def build_info_response(result, utterance):
    result_dict = result if isinstance(result, dict) else getattr(result, "model_dump", lambda: {})()

    answer = result_dict.get("answer_text") or result_dict.get("answer") or "답변을 생성하지 못했습니다."

    category = result_dict.get("category") or get_category_from_utterance(utterance)

    title = get_title_by_category(category)
    link = get_link_url_by_category(category)
    quick = get_quick_replies_by_category(category)

    final = f"{answer.strip()}\n\n사이트 바로가기: {link}"

    return (
        kakao_text_card(
            title=title,
            description=final,
            link_url=link,
            quick_replies=quick,
        ),
        final,
    )
