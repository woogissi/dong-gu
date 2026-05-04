def handle_fallback(query: str, error: str | None = None) -> str:
    if error and "관련 문서를 찾지 못했습니다" in error:
        return "관련 문서를 찾지 못했습니다. 질문을 조금 더 구체적으로 입력해 주세요."
    return "현재 답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."
