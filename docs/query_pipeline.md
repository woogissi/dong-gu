# Week 2 쿼리 파이프라인

## 범위 (Scope)

Week 2에서는 다음 모듈들을 정렬하여:

- `normalizer.py`
- `keyword_extractor.py`
- `entity_extractor.py`
- `query_rewriter.py`

검색(retrieval)이 하나의 일관된 계약(contract)을 사용할 수 있도록 합니다.

## 출력 계약 (Output Contract)

```json
{
  "original_query": "중앙도서관 주말에도 열어?",
  "normalized_query": "중앙도서관 주말에도 열어?",
  "keywords": ["중앙도서관", "주말"],
  "entities": {
    "category": [],
    "target": [],
    "time": [],
    "department": [],
    "action": []
  },
  "filters": {},
  "primary_category": null,
  "rewritten_queries": [
    "중앙도서관 주말에도 열어?",
    "중앙도서관 주말에도 열어? 중앙도서관 주말"
  ]
}
```

## 참고 사항 (Notes)

전처리 로직은 이제 QueryPreprocessor를 통해 실행
전처리 결과는 PipelineState에 직접 기록
rewrite_queries()는 검색에 바로 사용할 수 있는 여러 변형 쿼리를 반환 예정
rewrite_query()는 이전 버전과의 호환성을 위해 유지
엔티티 기반 filters는 이제 검색 이전 단계에서 생성