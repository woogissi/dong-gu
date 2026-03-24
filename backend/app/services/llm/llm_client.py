from app.core.config import settings


async def ask_llm(prompt: str) -> str:
    """
    추후 OpenAI API 실제 연결 예정.
    현재는 테스트 응답 반환.
    """
    if settings.OPENAI_API_KEY:
        return (
            "현재는 OpenAI API 실제 호출 전 단계입니다. "
            "향후 prompt를 기반으로 생성된 답변이 여기에 들어옵니다."
        )

    return "현재는 LLM 연동 전 테스트 응답입니다."
