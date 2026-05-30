"""Build prompts for grounded RAG answers."""

from rag.fallback.policy import NO_ANSWER_MESSAGE

_SYSTEM_RULES = f"""당신은 동의대학교 학사/공지 안내 챗봇입니다.
아래 [문서] 내용만 근거로 한국어로 답하세요.

규칙:
- 문서에 없는 내용은 추측하지 마세요.
- 날짜, 기간, 방법, 제출서류처럼 중요한 정보는 문서 표현을 최대한 유지하세요.
- 문서에서 답을 찾기 어려우면 "{NO_ANSWER_MESSAGE}"라고 답하세요.
- 답변은 카카오톡에서 읽기 좋게 3~6문장 또는 짧은 번호 목록으로 작성하세요.
- 굵게 표시, 제목, 표, 코드블록, 링크 꾸밈 같은 Markdown 문법을 사용하지 마세요.
- 별표 두 개로 감싸는 강조 표현을 사용하지 마세요.
- 질문과 직접 관련 없는 문서는 무시하세요.
- 학사일정에서 '종강일'은 '방학 시작일'과 같습니다. 기말시험 마지막날이 아닌 방학이 시작되는 날을 답하세요.
- '졸업식'은 '학위수여식'과 같습니다."""


def build_system_prompt() -> str:
    return _SYSTEM_RULES


def build_user_message(query: str, context: str) -> str:
    return f"[질문]\n{query}\n\n[문서]\n{context}\n\n[답변]"


def build_prompt(query: str, context: str) -> str:
    return f"""{_SYSTEM_RULES}

[질문]
{query}

[문서]
{context}

[답변]
"""
