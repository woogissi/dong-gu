# Week 2 Query Pipeline

## Scope

Week 2 aligns:

- `normalizer.py`
- `keyword_extractor.py`
- `entity_extractor.py`
- `query_rewriter.py`

so retrieval can consume one consistent contract.

## Output Contract

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

## Notes

- preprocessing logic now runs through `QueryPreprocessor`
- preprocessing output is written directly to `PipelineState`
- `rewrite_queries()` returns multiple retrieval-ready variants
- `rewrite_query()` remains for backward compatibility
- entity-derived `filters` are now produced before retrieval
