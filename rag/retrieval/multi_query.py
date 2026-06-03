"""LLM Multi-Query 검색 보조 모듈.

- ``generate_query_variants``: 원질의를 LLM으로 의미가 다양한 재표현으로 확장.
- ``reciprocal_rank_fusion``: 질의별 검색 결과 리스트들을 RRF로 융합.

검색 fan-out과 파이프라인 통합은 ``rag/pipeline/chat_pipeline.py``에서 수행한다.
이 모듈은 외부 의존(LLM 호출은 주입 가능)을 최소화해 단위테스트가 쉽도록 순수 함수 위주로 둔다.
"""

from __future__ import annotations

import json
import re

from rag.llm.answer_generator import generate_answer
from rag.schemas.retrieved_doc import RetrievedDoc

_MULTI_QUERY_SYSTEM_PROMPT = (
    "당신은 동의대학교 학사 안내 RAG 검색기의 질의 확장기입니다. "
    "사용자의 한국어 질문을 검색 recall을 높이도록 의미가 서로 다른 재표현(패러프레이즈, "
    "핵심어 강조형, 동의어 치환형)으로 바꿔 출력하세요.\n"
    "규칙:\n"
    "- 원래 질문의 의도를 보존하되 표현/어휘를 달리할 것.\n"
    "- 설명, 머리말, 번호, 불릿, 따옴표 없이 재표현 문장만 출력.\n"
    "- 한 줄에 하나씩, 또는 JSON 문자열 배열로만 출력.\n"
    "- 새로운 사실을 지어내지 말 것."
)

# 줄 앞의 번호/불릿 마커 제거용 (예: "1. ", "- ", "* ", "1) ")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def generate_query_variants(
    original_query: str,
    *,
    num: int,
    generate=generate_answer,
) -> list[str]:
    """원질의를 LLM으로 ``num``개의 재표현으로 확장한다.

    실패하거나 유효한 변형이 없으면 빈 리스트를 반환한다(호출부가 단일검색으로 폴백).
    ``generate``는 테스트에서 주입할 수 있도록 ``generate_answer`` 시그니처
    ``(prompt, *, system_prompt=None) -> str``를 따른다.
    """

    query = (original_query or "").strip()
    if not query or num <= 0:
        return []

    prompt = f"질문: {query}\n\n위 질문의 재표현 {num}개를 출력하세요."
    try:
        raw = generate(prompt, system_prompt=_MULTI_QUERY_SYSTEM_PROMPT)
    except Exception:
        return []

    variants = _parse_variants(raw)
    return _dedupe_against(variants, original=query, limit=num)


def _parse_variants(raw: str) -> list[str]:
    """LLM 응답을 변형 질의 리스트로 파싱한다(JSON 배열 우선, 줄단위 폴백)."""

    text = (raw or "").strip()
    if not text:
        return []

    # 1) JSON 배열 우선 시도 (코드펜스 ```json ... ``` 안에 올 수도 있음)
    json_candidate = _strip_code_fence(text)
    try:
        parsed = json.loads(json_candidate)
        if isinstance(parsed, list):
            return [_clean_line(str(item)) for item in parsed if _clean_line(str(item))]
    except (ValueError, TypeError):
        pass

    # 2) 줄 단위 분리 폴백
    lines = [_clean_line(line) for line in text.splitlines()]
    return [line for line in lines if line]


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        # 첫 줄(``` 또는 ```json)과 마지막 펜스 제거
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _clean_line(value: str) -> str:
    line = _LIST_PREFIX_RE.sub("", (value or "").strip())
    # 양끝 따옴표 제거
    line = line.strip().strip('"').strip("'").strip()
    return line


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).casefold().strip()


def _dedupe_against(variants: list[str], *, original: str, limit: int) -> list[str]:
    """원질의 및 상호 중복을 제거하고 ``limit``개로 캡한다."""

    seen = {_normalize_for_compare(original)}
    result: list[str] = []
    for variant in variants:
        key = _normalize_for_compare(variant)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(variant.strip())
        if len(result) >= limit:
            break
    return result


def _fusion_key(doc: RetrievedDoc) -> str:
    """RRF 중복 제거 키: chunk_id 우선, 없으면 doc_id+content_hash."""

    chunk_id = (doc.chunk_id or "").strip()
    if chunk_id:
        return f"chunk:{chunk_id}"
    content_hash = str(doc.metadata.get("content_hash") or "").strip()
    return f"doc:{(doc.doc_id or '').strip()}|{content_hash}"


def reciprocal_rank_fusion(
    result_lists: list[list[RetrievedDoc]],
    *,
    rrf_k: int = 60,
    top_k: int | None = None,
) -> list[RetrievedDoc]:
    """질의별 결과 리스트들을 Reciprocal Rank Fusion으로 융합한다.

    각 리스트에서 rank ``r``(0-base)인 문서에 ``1/(rrf_k + r)``를 더한다.
    동일 키(``_fusion_key``) 문서는 최초(최고 rank) 인스턴스를 유지하고 점수를 합산한다.
    RRF 점수 내림차순으로 정렬하며, 동률은 등장 순서를 보존(안정 정렬)한다.

    **score 분리:** ``doc.score``에는 정렬용 RRF 점수(순위 기반, 최대 ~N/rrf_k)를 넣되,
    quality gate가 쓰는 절대 매칭 강도는 입력 문서들의 원 점수(Layer-1 보너스 보정
    final_score) 중 최댓값을 ``metadata['quality_score']``로 보존한다. RRF가 작은 스케일이라
    gate 임계값(0~1 기준)을 못 넘어 100% fallback이 발동하던 문제를 방지한다.
    """

    scores: dict[str, float] = {}
    docs: dict[str, RetrievedDoc] = {}
    order: dict[str, int] = {}
    quality_scores: dict[str, float] = {}
    next_index = 0

    for result_list in result_lists:
        for rank, doc in enumerate(result_list):
            key = _fusion_key(doc)
            scores[key] = scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
            # 입력 doc.score = 각 질의의 Layer-1 보정 relevance(0~1). 키별 최댓값을 보존.
            source_score = float(doc.score or 0.0)
            quality_scores[key] = max(quality_scores.get(key, 0.0), source_score)
            if key not in docs:
                docs[key] = doc
                order[key] = next_index
                next_index += 1

    fused_keys = sorted(
        docs.keys(),
        key=lambda key: (-scores[key], order[key]),
    )

    fused: list[RetrievedDoc] = []
    for key in fused_keys:
        doc = docs[key]
        metadata = {**doc.metadata, "rrf_score": scores[key], "quality_score": quality_scores[key]}
        fused.append(doc.model_copy(update={"score": scores[key], "metadata": metadata}))

    if top_k is not None and top_k >= 0:
        fused = fused[:top_k]
    return fused
