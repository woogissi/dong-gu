from __future__ import annotations

import json

from rag.pipeline.preprocessor import QueryPreprocessor
from rag.pipeline.state import PipelineState
from rag.retrieval.retriever import retrieve_documents
from rag.retrieval.search_strategy import build_retrieval_request


QUERIES = [
    "학식 점심시간 몇시부터야?",
    "학생식당 운영시간 알려줘",
    "셔틀버스 시간표 알려줘",
    "통학버스 노선 알려줘",
    "주차권 신청 방법 알려줘",
    "등록금 납부 기간 알려줘",
    "장학금 신청 방법 알려줘",
    "국가장학금 신청 기간 알려줘",
    "수강신청 기간 알려줘",
    "학사일정 알려줘",
    "휴학 신청 방법 알려줘",
    "복학 신청 방법 알려줘",
    "졸업요건 알려줘",
    "성적 확인은 어디서 해?",
    "증명서 발급 방법 알려줘",
    "도서관 운영시간 알려줘",
    "기숙사 신청 기간 알려줘",
    "교내 와이파이 연결 방법 알려줘",
    "학생상담센터 위치 알려줘",
    "장애학생지원센터 지원 서비스 알려줘",
]


def audit_query(preprocessor: QueryPreprocessor, query: str) -> dict:
    state = PipelineState.from_query(query)
    preprocessor.run(state)
    request = build_retrieval_request(state)
    docs = retrieve_documents(request=request)
    top_docs = [
        {
            "score": doc.score,
            "title": doc.title,
            "source_type": doc.metadata.get("source_type"),
            "department": doc.metadata.get("department"),
            "content_len": len(doc.content or ""),
            "source": doc.source,
        }
        for doc in docs[:3]
    ]
    return {
        "query": query,
        "normalized_query": state.normalized_query,
        "keywords": state.keywords,
        "category": state.category,
        "filters": state.filters,
        "retrieved": len(docs),
        "top_score": docs[0].score if docs else 0,
        "top_docs": top_docs,
    }


def main() -> None:
    preprocessor = QueryPreprocessor()
    results = [audit_query(preprocessor, query) for query in QUERIES]
    print(json.dumps(results, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
