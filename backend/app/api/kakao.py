import time
from fastapi import APIRouter, Request, BackgroundTasks

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


def add_response_log_task(
    background_tasks: BackgroundTasks,
    request_id: str | None,
    answer_text: str | None,
    success: bool,
    response_time_ms: int,
    error_message: str | None = None,
):
    if not request_id:
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
async def kakao_webhook(request: Request, background_tasks: BackgroundTasks):
    start_time = time.time()
    request_id = None

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
        # 1. 질문 수신 즉시 저장
        request_id = create_query_log(
            user_id=user_id,
            question=utterance,
        )

        # 2. 의도 분류
        primary_intent = primary_intent_classifier.classify(utterance)

        # 3. 의도 결과 즉시 업데이트
        update_query_intent(
            request_id=request_id,
            intent_type=primary_intent,
        )

        # -------------------------
        # 욕설
        # -------------------------
        if primary_intent == "PROFANITY":
            answer_text = "부적절한 표현은 사용할 수 없어요."
            response_time_ms = int((time.time() - start_time) * 1000)

            # 응답 로그는 백그라운드 저장
            add_response_log_task(
                background_tasks=background_tasks,
                request_id=request_id,
                answer_text=answer_text,
                success=True,
                response_time_ms=response_time_ms,
            )

            return kakao_response(answer_text)

        # -------------------------
        # 일반 대화
        # -------------------------
        if primary_intent == "GENERAL":
            answer_text = general_chat_service.process_general_chat(
                utterance=utterance,
                user_id=user_id,
            )

            response_time_ms = int((time.time() - start_time) * 1000)

            # 응답 로그는 백그라운드 저장
            add_response_log_task(
                background_tasks=background_tasks,
                request_id=request_id,
                answer_text=answer_text,
                success=True,
                response_time_ms=response_time_ms,
            )

            return kakao_response(answer_text)

        # -------------------------
        # 정보성 질문
        # -------------------------
        print(f"[INFO] RAG start request_id={request_id}")

        result = get_chat_pipeline().run(Query(text=utterance))

        print(f"[INFO] RAG finished request_id={request_id}")

        if isinstance(result, dict):
            result_dict = result
        elif hasattr(result, "model_dump"):
            result_dict = result.model_dump()
        elif hasattr(result, "to_dict"):
            result_dict = result.to_dict()
        else:
            result_dict = {}

        answer_text = (
            result_dict.get("answer_text")
            or result_dict.get("answer")
            or getattr(result, "answer_text", None)
            or getattr(result, "answer", None)
        )

        category = (
            result_dict.get("category")
            or getattr(result, "category", None)
        )

        if not category:
            category = get_category_from_utterance(utterance)

        answer_text = (answer_text or "답변을 생성하지 못했습니다.").strip()
        answer_text = answer_text.replace("[DUMMY ANSWER]", "").strip()

        if "문맥:" in answer_text:
            answer_text = answer_text.split("문맥:")[0].strip()

        title = get_title_by_category(category)
        link_url = get_link_url_by_category(category)
        quick_replies = get_quick_replies_by_category(category)

        final_answer_text = f"{answer_text}\n\n사이트 바로가기: {link_url}"

        response_time_ms = int((time.time() - start_time) * 1000)

        # 응답 로그는 백그라운드 저장
        add_response_log_task(
            background_tasks=background_tasks,
            request_id=request_id,
            answer_text=final_answer_text,
            success=True,
            response_time_ms=response_time_ms,
        )

        return kakao_text_card(
            title=title,
            description=final_answer_text,
            link_url=link_url,
            quick_replies=quick_replies,
        )

    except Exception as e:
        print(f"[ERROR] kakao_webhook request_id={request_id}: {e}")

        response_time_ms = int((time.time() - start_time) * 1000)

        # 실패 응답 로그도 백그라운드 저장
        add_response_log_task(
            background_tasks=background_tasks,
            request_id=request_id,
            answer_text=None,
            success=False,
            response_time_ms=response_time_ms,
            error_message=str(e),
        )

        return kakao_response(
            "질문 처리 중 오류가 발생했어요.\n잠시 후 다시 시도해주세요."
        )

    finally:
        release_user_lock(user_id)