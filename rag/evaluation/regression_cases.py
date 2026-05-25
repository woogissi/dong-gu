"""Representative RAG regression cases.

These cases are intentionally small and stable enough to run as a smoke check.
They focus on routing, source filtering, citation consistency, and the common
failure mode where documents are selected but the final answer still says no
document was found.
"""

from __future__ import annotations


NOT_FOUND_ANSWER_PATTERNS = (
    "제공된 문서에서 관련 정보를 찾지 못했습니다",
    "관련 정보를 찾지 못했습니다",
    "문서를 찾지 못했습니다",
    "찾을 수 없습니다",
)

REGRESSION_CASES = [
    {
        "id": "course_registration_period",
        "query": "수강신청 기간 알려줘",
        "expected_source_types": {"academic_notice"},
        "forbidden_source_types": {"job", "external_notice", "bids", "scholarship"},
        "expected_title_terms": {"수강신청"},
    },
    {
        "id": "scholarship_period",
        "query": "장학금 신청 기간 알려줘",
        "expected_source_types": {"scholarship", "notice"},
        "forbidden_source_types": {"job", "bids", "dormitory"},
        "expected_title_terms": {"장학"},
    },
    {
        "id": "dormitory_application",
        "query": "기숙사 신청 방법 알려줘",
        "expected_source_types": {"dormitory"},
        "forbidden_source_types": {"scholarship", "job", "bids", "department"},
        "expected_title_terms": {"효민생활관", "기숙사", "생활관"},
    },
    {
        "id": "graduation_requirement",
        "query": "졸업요건 알려줘",
        "expected_source_types": {"academic_notice", "academic_support", "department", "institution", "academic"},
        "forbidden_source_types": {"job", "bids", "external_notice", "dormitory"},
        "expected_title_terms": {"졸업", "학칙", "학사"},
    },
    {
        "id": "leave_of_absence",
        "query": "휴학 신청 방법 알려줘",
        "expected_source_types": {"academic_support", "academic_notice"},
        "forbidden_source_types": {"scholarship", "job", "bids", "dormitory"},
        "expected_title_terms": {"휴학"},
    },
    {
        "id": "return_to_school",
        "query": "복학 신청 기간 알려줘",
        "expected_source_types": {"academic_support", "academic_notice"},
        "forbidden_source_types": {"scholarship", "job", "bids", "dormitory"},
        "expected_title_terms": {"복학"},
    },
    {
        "id": "certificate_issue",
        "query": "증명서 발급 방법 알려줘",
        "expected_source_types": {"academic_support", "institution"},
        "forbidden_source_types": {"job", "bids", "external_notice", "scholarship"},
        "expected_title_terms": {"증명서", "제증명서"},
    },
    {
        "id": "former_presidents",
        "query": "동의대 역대 총장 목록",
        "expected_source_types": {"institution"},
        "forbidden_source_types": {"job", "scholarship", "bids", "external_notice", "department"},
        "expected_title_terms": {"역대총장", "총장"},
    },
    {
        "id": "shuttle_bus",
        "query": "통학버스 시간표 알려줘",
        "expected_source_types": {"notice", "institution"},
        "forbidden_source_types": {"job", "scholarship", "bids", "external_notice"},
        "expected_title_terms": {"통학버스"},
    },
    {
        "id": "tuition_payment",
        "query": "등록금 납부 기간 알려줘",
        "expected_source_types": {"notice", "academic_notice", "academic_support", "institution"},
        "forbidden_source_types": {"job", "scholarship", "bids", "external_notice", "dormitory"},
        "expected_title_terms": {"등록금", "납부"},
    },
]


def answer_has_not_found_pattern(answer: str) -> bool:
    return any(pattern in (answer or "") for pattern in NOT_FOUND_ANSWER_PATTERNS)


def selected_context_has_not_found_mismatch(result: dict) -> bool:
    retrieval_log = result.get("retrieval_log") or {}
    return (
        int(retrieval_log.get("retrieved_doc_count") or 0) > 0
        and int(retrieval_log.get("selected_doc_count") or 0) > 0
        and answer_has_not_found_pattern(str(result.get("answer") or result.get("answer_text") or ""))
    )
