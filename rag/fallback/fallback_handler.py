from rag.fallback.policy import (
    GENERAL_FALLBACK_MESSAGE,
    NO_RETRIEVAL_FALLBACK_MESSAGE,
    is_no_retrieval_error,
)


def handle_fallback(query: str, error: str | None = None) -> str:
    if error and is_no_retrieval_error(error):
        return NO_RETRIEVAL_FALLBACK_MESSAGE
    return GENERAL_FALLBACK_MESSAGE
