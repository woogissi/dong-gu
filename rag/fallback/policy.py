"""Shared fallback and no-answer policy for RAG responses."""

NO_ANSWER_MESSAGE = "제공된 문서에서 관련 정보를 찾지 못했습니다."

NOT_FOUND_ANSWER_PATTERNS = (
    NO_ANSWER_MESSAGE,
    "제공된 문서에서 관련 정보를 찾지 못했습니다",
    "관련 정보를 찾지 못했습니다",
    "문서를 찾지 못했습니다",
    "관련 정보를 찾지 못했습니다.",
    "문서를 찾지 못했습니다.",
    "찾을 수 없습니다",
)

NO_RETRIEVAL_RESULTS_MESSAGE = "관련 문서를 찾지 못했습니다."
NO_RETRIEVAL_FALLBACK_MESSAGE = (
    "관련 문서를 찾지 못했습니다. "
    "질문을 조금 더 구체적으로 입력해 주세요."
)
GENERAL_FALLBACK_MESSAGE = (
    "현재 답변을 생성하지 못했습니다. "
    "잠시 후 다시 시도해 주세요."
)


def has_not_found_answer(text: str | None) -> bool:
    """Return True when text contains a known no-answer phrase."""
    return any(pattern in (text or "") for pattern in NOT_FOUND_ANSWER_PATTERNS)


def strip_not_found_answer(text: str | None) -> str:
    """Remove known no-answer phrases while preserving other generated content."""
    cleaned = text or ""
    for pattern in NOT_FOUND_ANSWER_PATTERNS:
        cleaned = cleaned.replace(pattern + ".", "")
        cleaned = cleaned.replace(pattern, "")
    return cleaned


def is_no_retrieval_error(error: str | None) -> bool:
    return NO_RETRIEVAL_RESULTS_MESSAGE in (error or "")
