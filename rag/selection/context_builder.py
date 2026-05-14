"""Build compact answer context from selected documents."""

from rag.schemas.retrieved_doc import RetrievedDoc


def build_context(docs: list[RetrievedDoc]) -> str:
    blocks: list[str] = []
    for index, doc in enumerate(docs, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[문서 {index}]",
                    f"제목: {doc.title or '제목 없음'}",
                    f"출처: {doc.source or doc.metadata.get('source_type') or '출처 없음'}",
                    f"게시일: {doc.metadata.get('published_at') or '날짜 없음'}",
                    "내용:",
                    doc.content,
                ]
            )
        )
    return "\n\n".join(blocks)
