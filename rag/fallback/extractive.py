"""Extractive fallback answer generation for LLM provider failures."""

from __future__ import annotations

import re

from rag.fallback.policy import NO_ANSWER_MESSAGE


def build_extractive_fallback(prompt: str, *, error: str) -> str:
    context = _extract_section(prompt, "문서")
    query = _extract_section(prompt, "질문")
    sentences = _split_sentences(context)

    if not sentences:
        return NO_ANSWER_MESSAGE

    query_terms = set(_tokenize(query))
    ranked = sorted(
        sentences,
        key=lambda sentence: (
            _term_overlap_score(sentence, query_terms),
            len(sentence),
        ),
        reverse=True,
    )
    selected = [sentence for sentence in ranked[:4] if sentence.strip()]
    if not selected:
        return NO_ANSWER_MESSAGE

    answer = "\n".join(f"- {sentence.strip()}" for sentence in selected)
    return f"{answer}\n\n(텍스트 fallback: LLM 연결 실패 - {error})"


def _extract_section(prompt: str, section_name: str) -> str:
    next_sections = {
        "질문": "문서",
        "문서": "답변",
    }
    next_section = next_sections.get(section_name)
    if next_section:
        pattern = rf"\[{re.escape(section_name)}\]\n(.*?)(?=\n\[{re.escape(next_section)}\]\n|\Z)"
    else:
        pattern = rf"\[{re.escape(section_name)}\]\n(.*)"
    match = re.search(pattern, prompt, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _split_sentences(text: str) -> list[str]:
    content_lines = [
        line.strip()
        for line in text.splitlines()
        if _is_content_line(line.strip())
    ]
    normalized = re.sub(r"\s+", " ", " ".join(content_lines))
    chunks = re.split(r"(?<=[.!?])\s+|(?<=다\.)\s+", normalized)
    return [chunk.strip(" -")[:240] for chunk in chunks if len(chunk.strip()) >= 20]


def _is_content_line(line: str) -> bool:
    if not line:
        return False
    ignored_prefixes = (
        "[문서",
        "[TITLE]",
        "[BODY]",
        "[ATTACHMENT]",
        "title:",
        "source_url:",
        "source_type:",
        "content_type:",
        "published_at:",
        "scores:",
        "chunk_id:",
        "doc_id:",
        "section:",
        "content:",
    )
    if line in {"body"}:
        return False
    return not line.startswith(ignored_prefixes)


def _term_overlap_score(sentence: str, query_terms: set[str]) -> int:
    sentence_terms = set(_tokenize(sentence))
    return len(query_terms & sentence_terms)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower())
