# Week 3 Retrieval Contract

## 범위

Week 3에서는 실제 DB 검색 구현보다 검색 단계의 입력/출력 계약과 전략 로그를 먼저 고정한다. 기본 검색 방식은 `lexical`이며, PostgreSQL FTS 실구현은 Week 4에서 `retriever.py`에 연결한다.

## 검색 요청 계약

```json
{
  "query": "수강신청 언제까지야?",
  "query_variants": [
    "수강신청 언제까지야?",
    "수강신청 언제까지야? 수강 신청 기간"
  ],
  "keywords": ["수강신청", "기간"],
  "filters": {
    "category": ["수강"],
    "time": ["기간"],
    "document_category": ["academic_notice"]
  },
  "category": "수강",
  "strategy": "lexical",
  "top_k": 10,
  "fallback_triggers": [],
  "log_fields": {
    "strategy": "lexical",
    "query": "수강신청 언제까지야?",
    "query_variant_count": 2,
    "keywords": ["수강신청", "기간"],
    "filters": {
      "category": ["수강"],
      "time": ["기간"],
      "document_category": ["academic_notice"]
    },
    "category": "수강",
    "document_category_hints": ["academic_notice"],
    "top_k": 10,
    "fallback_triggers": [],
    "filter_rules_applied": [
      "category_filter",
      "time_filter",
      "category_to_document_category_hint"
    ]
  }
}
```

## 검색 응답 계약

`retrieve_documents()`는 현재 `list[RetrievedDoc]`를 반환한다. Week 4 이후에는 필요하면 `RetrievalResponse`로 감싸서 요청, 문서 목록, fallback 여부, 로그 필드를 한 번에 반환할 수 있다.

```json
{
  "doc_id": "doc-1",
  "chunk_id": "chunk-1",
  "content": "문서 본문 chunk",
  "score": 0.9,
  "title": "공지 제목",
  "source": "url 또는 source id",
  "category": "수강",
  "metadata": {
    "strategy": "lexical",
    "query": "수강신청 언제까지야?",
    "keywords": ["수강신청", "기간"],
    "filters": {
      "category": ["수강"],
      "time": ["기간"],
      "document_category": ["academic_notice"]
    }
  }
}
```

## 필터 규칙

`SUPPORTED_FILTER_FIELDS`는 전처리 단계에서 `state.filters`로 넘어오는 입력 필터만 검증한다. `build_retrieval_request()`는 이 입력 필터를 정규화한 뒤, `category` 값이 `_CATEGORY_DOCUMENT_HINTS`에 매핑되면 `document_category`를 파생 필터로 추가한다.

따라서 `RetrievalRequest.filters`를 소비하는 하위 검색 모듈은 다음 두 그룹의 필터 키를 모두 계약으로 인지해야 한다.

- 입력 필터: `category`, `target`, `department`, `time`, `time_scope`
- 파생 필터: `document_category`

- `category`: 엔티티의 대표 카테고리를 검색 범위 힌트로 사용한다.
- `target`: 신입생, 재학생, 편입생 등 대상자 조건이 있는 문서의 metadata 필터 후보로 사용한다.
- `department`: 교무처, 학생지원팀, 입학처 등 부서 metadata 필터 후보로 사용한다.
- `time`: 기간, 일정, 오늘, 이번학기 등 시간 조건을 date/time scope 힌트로 사용한다.
- `time_scope`: 정확한 시점 엔티티가 있을 때 `time`에서 복사된 보조 필터로 사용한다.
- `document_category`: `category`를 crawler 문서 묶음(`academic_notice`, `notice`, `dormitory`)으로 매핑한 검색 힌트다. 이 값은 전처리 입력 필터가 아니라 검색 요청 생성 단계에서 동적으로 추가된다.

## Fallback 트리거

- `empty_query`: 검색 쿼리가 비어 있을 때
- `insufficient_search_terms`: 키워드와 필터가 모두 없을 때
- `filter_only_query`: 필터는 있지만 lexical 검색 키워드가 없을 때

## 전략 로그 필드

전략 로그는 `PipelineState.metadata["retrieval_strategy_log"]`에 기록한다. 최소 필드는 `strategy`, `query`, `query_variant_count`, `keywords`, `filters`, `category`, `document_category_hints`, `top_k`, `fallback_triggers`, `filter_rules_applied`이다.
