import time
from fastapi import APIRouter, BackgroundTasks, Request

from backend.app.utils.callback import kakao_callback
from backend.app.database.query_logs import create_query_log, update_query_intent
from backend.app.database.response_logs import save_response_log
from backend.app.database.retrieval_logs import save_retrieval_log
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
from rag.utils.demo_logger import demo_log


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


def add_retrieval_log_task(background_tasks, request_id, log_data):
    if not request_id:
        return

    if background_tasks is None:
        safe_save_retrieval_log(request_id, log_data)
        return

    background_tasks.add_task(safe_save_retrieval_log, request_id, log_data)


def safe_save_retrieval_log(request_id, log_data):
    try:
        save_retrieval_log(request_id, log_data)
    except Exception as e:
        print(f"[ERROR] save_retrieval_log: {e}")


def extract_retrieval_log(result):
    if isinstance(result, dict):
        return result.get("retrieval_log")
    if hasattr(result, "model_dump"):
        return result.model_dump().get("retrieval_log")
    if hasattr(result, "to_dict"):
        return result.to_dict().get("retrieval_log")
    return getattr(result, "retrieval_log", None)


def extract_pipeline_retrieval_log(pipeline):
    state = getattr(pipeline, "last_state", None)
    if state is None or not hasattr(state, "to_log_dict"):
        return None
    return state.to_log_dict()


def resolve_retrieval_log(result, utterance: str, pipeline=None):
    return (
        extract_retrieval_log(result)
        or extract_pipeline_retrieval_log(pipeline)
        or build_minimal_retrieval_log(result, utterance)
    )


def build_minimal_retrieval_log(result, utterance: str):
    return {
        "original_query": utterance,
        "normalized_query": None,
        "rewritten_query": None,
        "rewritten_queries": [],
        "keywords": [],
        "entities": {},
        "filters": {},
        "category": get_category_from_utterance(utterance),
        "retrieval_strategy": "lexical",
        "retrieval_top_k": 10,
        "retrieval_strategy_log": {"fallback_reason": "missing_pipeline_retrieval_log"},
        "fallback_used": not _result_success(result),
        "retrieved_doc_count": 0,
        "reranked_doc_count": 0,
        "selected_doc_count": 0,
        "selected_docs": [],
        "context": None,
        "success": _result_success(result),
        "error": None,
        "metadata": {},
    }


@router.post("/webhook")
async def kakao_webhook(request: Request, background_tasks: BackgroundTasks = None):
    start_time = time.time()
    callback_mode = False
    request_id = None

    body = await request.json()

    callback_url = body.get("userRequest", {}).get("callbackUrl")
    user_id = body.get("userRequest", {}).get("user", {}).get("id", "unknown")
    utterance = body.get("userRequest", {}).get("utterance", "").strip()
    demo_log(
        "1. Kakao webhook received",
        {
            "user_id": user_id,
            "utterance": utterance,
            "callback_mode": bool(callback_url),
        },
    )

    if not utterance:
        return kakao_response("질문 내용을 입력해주세요.")

    if not acquire_user_lock(user_id):
        return kakao_response("이전 질문을 처리 중입니다.\n잠시 후 다시 질문해주세요.")

    try:
        request_id = create_query_log(user_id=user_id, question=utterance)

        intent = primary_intent_classifier.classify(utterance)
        update_query_intent(request_id=request_id, intent_type=intent)
        demo_log(
            "1-1. Intent classified",
            {
                "request_id": request_id,
                "intent": intent,
            },
        )

        if intent == "PROFANITY":
            answer = "부적절한 표현은 사용할 수 없어요."

            save_response_log(
                request_id=request_id,
                answer_text=answer,
                success=True,
                error_message=None,
                response_time_ms=int((time.time() - start_time) * 1000),
            )

            return kakao_response(answer)

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

        # 콜백 URL이 없는 경우에도 RAG -> Ollama 파이프라인을 동기로 실행해 응답합니다.
        response_body, final_answer, success, retrieval_log = process_info_sync(utterance)
        add_retrieval_log_task(background_tasks, request_id, retrieval_log)
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


def process_info_with_callback(callback_url, request_id, user_id, utterance, start_time):
    try:
        pipeline = get_chat_pipeline()
        result = pipeline.run(Query(text=utterance))

        response_body, final_answer = build_info_response(result, utterance)

        kakao_callback(callback_url, response_body)

        safe_save_retrieval_log(
            request_id,
            resolve_retrieval_log(result, utterance, pipeline),
        )

        save_response_log(
            request_id=request_id,
            answer_text=final_answer,
            success=_result_success(result),
            response_time_ms=int((time.time() - start_time) * 1000),
            error_message=None
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


def process_info_sync(utterance: str):
    pipeline = get_chat_pipeline()
    result = pipeline.run(Query(text=utterance))
    response_body, final_answer = build_info_response(result, utterance)
    success = _result_success(result)
    retrieval_log = resolve_retrieval_log(result, utterance, pipeline)
    return response_body, final_answer, success, retrieval_log


def _result_success(result) -> bool:
    if isinstance(result, dict):
        return bool(result.get("success", True))
    return bool(getattr(result, "success", True))


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
