"""Postprocess generated answers before returning them to users."""

from __future__ import annotations

import re
from typing import MutableMapping

from rag.fallback.policy import NO_ANSWER_MESSAGE, has_not_found_answer, strip_not_found_answer, NOT_FOUND_ANSWER_PATTERNS

# 거의 모든 학교 문서에 등장해 변별력이 없는 토큰 — repair 스니펫 매칭에서 제외한다.
_GENERIC_MATCH_TERMS = {
    "동의대",
    "동의대학교",
    "동의",
    "대학교",
    "학교",
    "학생",
    "알려줘",
    "알려",
    "어디",
    "어디서",
    "언제",
    "뭐야",
    "무엇",
    "방법",
    "안내",
}

# 스니펫이 답변으로 채택되려면 변별 토큰이 최소 이만큼 겹쳐야 한다.
_MIN_SNIPPET_OVERLAP = 1


def repair_negative_answer_with_context(
    answer: str,
    metadata: MutableMapping[str, object] | None = None,
    *,
    context: str | None = None,
    selected_docs: list[object] | None = None,
    query: str | None = None,
    keywords: list[str] | None = None,
) -> str:
    if not has_not_found_answer(answer):
        return answer
    cleaned = strip_negative_answer_sentences(answer)
    if has_substantive_answer(cleaned):
        if metadata is not None:
            metadata["negative_answer_repair"] = "stripped_negative_sentence"
        return cleaned
    if selected_docs and has_substantive_context(context):
        repaired = build_selected_context_answer(selected_docs, query=query, keywords=keywords)
        if repaired and not has_not_found_answer(repaired):
            if metadata is not None:
                metadata["negative_answer_repair"] = "selected_context_extract"
                metadata["negative_answer_issue_stage"] = "answer_generation"
            return repaired
    return answer


def strip_negative_answer_sentences(answer: str) -> str:
    # 부정 패턴이 포함된 라인 전체를 제거하여 문장 조각이 남지 않도록 한다
    lines = (answer or "").splitlines()
    kept = [line for line in lines if not any(p in line for p in NOT_FOUND_ANSWER_PATTERNS)]
    text = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def has_substantive_answer(answer: str) -> bool:
    normalized = re.sub(r"\s+", " ", answer or "").strip()
    # 20자 이상이면 실질적 내용으로 판단 (기존 40자에서 완화)
    return len(normalized) >= 20 and not has_not_found_answer(normalized)


def has_substantive_context(context: str | None) -> bool:
    normalized = re.sub(r"\s+", " ", context or "").strip()
    return len(normalized) >= 40


def build_selected_context_answer(
    selected_docs: list[object],
    *,
    query: str | None = None,
    keywords: list[str] | None = None,
) -> str:
    snippets = _ranked_doc_snippets(selected_docs, query=query, keywords=keywords)
    if not snippets:
        return ""  # 빈 문자열 반환 → 호출자가 원본 부정 답변으로 fallback
    lines = ["선택된 문서 기준으로 확인된 내용입니다."]
    for snippet in snippets[:3]:
        title = snippet["title"]
        content = snippet["content"]
        if title:
            lines.append(f"- {title}: {content}")
        else:
            lines.append(f"- {content}")
    source_url = _first_source_url(selected_docs)
    if source_url:
        lines.append(f"자세한 내용은 다음에서 확인하세요: {source_url}")
    return "\n".join(lines)


def _ranked_doc_snippets(
    selected_docs: list[object],
    *,
    query: str | None = None,
    keywords: list[str] | None = None,
) -> list[dict[str, str]]:
    # 쿼리 어휘에 더해 동의어 확장/정규화 키워드까지 매칭 대상에 포함해
    # 어휘 불일치 질의(예: "심리상담" vs 문서의 "학생상담센터")에서도 정답 문장을 고른다.
    query_terms = set(_tokenize(query or ""))
    for keyword in keywords or []:
        query_terms.update(_tokenize(str(keyword)))
    # 거의 모든 학교 문서에 등장하는 변별력 없는 토큰은 제거해, 학교명/의문형만
    # 겹친 무관 문서(예: "설립 연도" 질의에 매칭된 채용공고)가 답변으로 새지 않게 한다.
    query_terms -= _GENERIC_MATCH_TERMS
    snippets: list[dict[str, str]] = []
    for doc in selected_docs:
        content = _clean_snippet_markup(_doc_value(doc, "content"))
        snippet = _best_content_snippet(content, query_terms)
        if not snippet:
            continue
        # 변별 토큰이 하나도 겹치지 않는 스니펫(=무관 문서)은 채택하지 않는다.
        # 통과 스니펫이 없으면 호출자가 빈 결과를 받아 원본 거절문으로 안전하게 fallback한다.
        if _term_overlap_score(snippet, query_terms) < _MIN_SNIPPET_OVERLAP:
            continue
        snippets.append(
            {
                "title": _doc_value(doc, "title"),
                "content": snippet,
                "score": str(_term_overlap_score(snippet, query_terms)),
            }
        )
    return sorted(snippets, key=lambda item: int(item["score"]), reverse=True)


_STRUCT_MARKER_RE = re.compile(r"\[/?[A-Z][A-Z_]*\]")


def _clean_snippet_markup(text: str) -> str:
    """청크 본문의 구조 마커([TITLE]/[ATTACHMENT] 등)와 다운로드 문구를 제거한다.

    첨부/이수표 청크가 repair 스니펫으로 노출될 때 `[TITLE] ... [ATTACHMENT] 원본파일
    Download ...` 같은 원본 마크업이 그대로 답변에 새는 것을 막는다(G046).
    """
    cleaned = _STRUCT_MARKER_RE.sub(" ", text or "")
    cleaned = re.sub(r"원본파일\s*Download", " ", cleaned)
    cleaned = re.sub(r"\bDownload\b", " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _best_content_snippet(content: str, query_terms: set[str]) -> str:
    sentences = _split_content_sentences(content)
    if not sentences:
        return ""
    ranked = sorted(
        sentences,
        key=lambda sentence: (_term_overlap_score(sentence, query_terms), len(sentence)),
        reverse=True,
    )
    best = ranked[0]
    # 변별 토큰이 하나도 안 겹치는 문서는 무관 문서로 보고 스니펫을 만들지 않는다.
    if query_terms and _term_overlap_score(best, query_terms) < _MIN_SNIPPET_OVERLAP:
        return ""
    return best[:240].strip()


def _split_content_sentences(content: str) -> list[str]:
    cleaned_lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    normalized = re.sub(r"\s+", " ", " ".join(cleaned_lines)).strip()
    chunks = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+", normalized)
    return [chunk.strip(" -") for chunk in chunks if len(chunk.strip()) >= 10]


def _term_overlap_score(text: str, query_terms: set[str]) -> int:
    if not query_terms:
        return 0
    # 한국어는 조사가 붙어 토큰 정확일치가 자주 실패한다("학생상담센터" vs "학생상담센터에서").
    # 부분문자열 매칭으로 겹치는 변별 토큰 수를 센다.
    normalized = (text or "").lower()
    return sum(1 for term in query_terms if term and term in normalized)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", (text or "").lower())


def _first_source_url(selected_docs: list[object]) -> str:
    for doc in selected_docs:
        source = _doc_value(doc, "source") or _doc_value(doc, "source_url")
        if source:
            return source
    return ""


def _doc_value(doc: object, key: str) -> str:
    if isinstance(doc, dict):
        value = doc.get(key)
    else:
        value = getattr(doc, key, "")
    return str(value or "").strip()


def strip_markdown_formatting(text: str) -> str:
    if not text:
        return text
    cleaned = text.replace("```", "")
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__(.*?)__", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", cleaned)
    return cleaned.strip()
