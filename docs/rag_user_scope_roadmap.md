# RAG User Scope Roadmap

기준: 정보성 카테고리 분류 이후, 사용자 작업 범위(1~6)

## 1주차: 엔티티 추출 기반 구축 (범위 1)

- TODO
1. 엔티티 스키마 확정(카테고리/대상/기간/부서/행위)
2. 사전(lexicon) + 규칙 패턴 정의
3. `entity_extractor` 초안 구현

- 산출물
1. `entity_schema.md`
2. `entity_lexicon.yaml` 또는 `domain_knowledge.py`
3. `entity_extractor.py` v1 + 단위테스트

## 2주차: Query 재작성/확장 고도화 (범위 2)

- TODO
1. 정규화-키워드추출-재작성 파이프라인 정합화
2. 의도별 확장어(기간/방법/신청/확인 등) 룰 추가
3. 재작성 품질 점검용 샘플셋 구축

- 산출물
1. `normalizer.py`, `keyword_extractor.py`, `query_rewriter.py` v2
2. 샘플 질의셋 150+
3. 전/후 쿼리 비교 리포트

## 3주차: 검색 전략 결정기 구현 (범위 3)

- TODO
1. 전략 결정 규칙(하이브리드/카테고리 우선/전체 fallback)
2. top-k, 가중치, 필터(카테고리/기간) 정책화
3. 전략 결정 로그 필드 정의

- 산출물
1. `search_strategy.py`
2. `retrieval_policy.yaml`
3. 전략 결정 케이스 테스트 + 로그 스키마

## 4주차: Hybrid Search + Re-ranking (범위 4)

- TODO
1. 벡터 검색 + 키워드(BM25) 결합
2. 후보 문서 병합/중복 제거/점수 정규화
3. Re-ranking 적용 및 fallback 연결

- 산출물
1. `retriever.py` 실구현
2. `reranker.py` (또는 모듈)
3. 검색 품질 리포트(hit@k, MRR)

## 5주차: 컨텍스트/프롬프트 구성 (범위 5)

- TODO
1. 상위 문서 선택 기준 확정(점수+다양성)
2. 컨텍스트 압축/길이 제한/근거 포함 규칙
3. 질의 유형별 프롬프트 템플릿 분리

- 산출물
1. `topk_selector.py`, `context_builder.py` v2
2. `prompt_builder.py` v2
3. 프롬프트 템플릿 문서 + 예시

## 6주차: 생성/검증/로그 운영화 (범위 6)

- TODO
1. LLM 응답 생성 실제 연동
2. 응답 검증(근거 부족/환각/금지어) + 후처리
3. QA 로그(질문/전략/문서/응답시간/성공여부) 적재

- 산출물
1. `answer_generator.py` 실구현
2. `response_validator.py` + `fallback_handler.py` 정리
3. E2E 데모 + 운영 체크리스트
