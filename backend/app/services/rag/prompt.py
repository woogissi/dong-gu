def build_rag_prompt(question: str, docs: list[dict]) -> str:
    if not docs:
        return (
            "당신은 동의대학교 정보 안내 챗봇입니다.\n"
            f"질문: {question}\n"
            "참고 문서가 없으므로 일반적인 안내 문구로 답변하세요."
        )

    context = "\n\n".join(
        [
            f"[문서 {idx + 1}] 제목: {doc.get('title', '')}\n내용: {doc.get('content', '')}"
            for idx, doc in enumerate(docs)
        ]
    )

    return (
        "당신은 동의대학교 정보 안내 챗봇입니다.\n"
        "아래 참고 문서를 기반으로 정확하고 간결하게 답변하세요.\n\n"
        f"참고 문서:\n{context}\n\n"
        f"질문:\n{question}\n"
    )
