# RAG 품질 저하 단계별 진단 리포트

## 전체 요약

- 총 분석 query 수: 54
- 실패/의심 케이스 수: 10
- 원인별 분포:
  - crawler/data 부족: 0
  - query rewrite 문제: 0
  - keyword/category/filter: 0
  - lexical search 문제: 0
  - vector search 문제: 0
  - hybrid merge 문제: 0
  - rerank 문제: 0
  - fallback 문제: 0
  - final generation 문제: 0
  - mixed: 0
  - out_of_scope: 0

## 데이터/크롤러 품질

| gap | count |
| --- | --- |
| documents_without_chunks | 0 |
| chunks_without_embeddings | 0 |
| documents_without_contents | 0 |
| assets_without_extracted_content | 4532 |
| very_short_chunks_lt_120 | 88 |

해석: documents/chunks/embeddings의 큰 적재 누락은 제한적이지만, assets_without_extracted_content와 very_short_chunks가 검색 잡음 및 답변 누락 리스크다.

## 대표 실패 케이스

### Query ID: 293

원 질문: 버스 알려줘
Rewrite: None
Intent: GENERAL
Keywords: None
Category: None
Filters: None

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: No retrieval log exists, but DB contains evidence-like chunks; intent classification or route selection likely bypassed RAG.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 없음
- evidence ranks: {}

원인 분류: D_INTENT_OR_ROUTING_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 296

원 질문: 6-1번 버스 정보
Rewrite: None
Intent: GENERAL
Keywords: None
Category: None
Filters: None

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: No retrieval log exists, but DB contains evidence-like chunks; intent classification or route selection likely bypassed RAG.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 없음
- evidence ranks: {}

원인 분류: D_INTENT_OR_ROUTING_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 297

원 질문: 6-1번 버스 운행 정보
Rewrite: None
Intent: GENERAL
Keywords: None
Category: None
Filters: None

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: No retrieval log exists, but DB contains evidence-like chunks; intent classification or route selection likely bypassed RAG.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 없음
- evidence ranks: {}

원인 분류: D_INTENT_OR_ROUTING_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 301

원 질문: 하씨발
Rewrite: None
Intent: PROFANITY
Keywords: None
Category: None
Filters: None

최종 답변: 부적절한 표현은 사용할 수 없어요.
문제 요약: The request was classified as profanity and intentionally did not enter RAG retrieval.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 하씨발
- evidence ranks: {}

원인 분류: OUT_OF_SCOPE_POLICY_ROUTE / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 306

원 질문: 26년 1학기 보강일정 알려줘
Rewrite: 보강일정 26년 1학기 기간 마감일
Intent: INFO
Keywords: ['기간', '일정', '보강일정', '26년', '1학기', '1학기보강일정', '학기보강일정', '1학기보강', '학기보강', '26', '학기', '보강']
Category: None
Filters: {'time': ['1학기', '기간'], 'time_scope': ['1학기']}

최종 답변: 26년 1학기 보강일정은 제공된 문서에서 관련 정보를 찾을 수 없습니다. 

26년 1학기의 주요 일정은 다음과 같습니다.

*   학기개시일: 3월 1일
*   개강일: 3월 3일
*   중간시험: 4월 21일 ~ 27일
*   기말 시험: 6월 16일 ~ 22일

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: Selected chunks contain query evidence, but final answer is negative, incomplete, or non-committal.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 1. 학사일정 | 학사정보 | 대학생활 (3.836065)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 26년, 1학기, 보강일정, 보강일정 26년 1학기 기간 마감일, 26년 1학기 보강일정 알려줘 기간, 26 1 학기 보강 일정, 26년 1학기 보강일정 알려줘, 1학기보강일정
- evidence ranks: {}

원인 분류: C_GENERATION_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 315

원 질문: 지천관 위치가 어떻게 돼?
Rewrite: None
Intent: GENERAL
Keywords: None
Category: None
Filters: None

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: No retrieval log exists, but DB contains evidence-like chunks; intent classification or route selection likely bypassed RAG.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 지천관, 위치가
- evidence ranks: {}

원인 분류: D_INTENT_OR_ROUTING_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 317

원 질문: 동의대 정보관의 정보를 알고 싶어
Rewrite: None
Intent: GENERAL
Keywords: None
Category: None
Filters: None

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: No retrieval log exists, but DB contains evidence-like chunks; intent classification or route selection likely bypassed RAG.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 정보관의, 정보를
- evidence ranks: {}

원인 분류: D_INTENT_OR_ROUTING_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 320

원 질문: 학교내 편의점 어디에 있어
Rewrite: None
Intent: INFO
Keywords: None
Category: None
Filters: None

최종 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: Evidence-like chunks exist in DB, but retrieval selected no chunks.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 학교내, 편의점, 어디에
- evidence ranks: {}

원인 분류: B_RETRIEVAL_SELECTION_GAP / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 329

원 질문: 시발
Rewrite: None
Intent: PROFANITY
Keywords: None
Category: None
Filters: None

최종 답변: 부적절한 표현은 사용할 수 없어요.
문제 요약: The request was classified as profanity and intentionally did not enter RAG retrieval.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 없음
- evidence ranks: {}

원인 분류: OUT_OF_SCOPE_POLICY_ROUTE / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 330

원 질문: 시발련아
Rewrite: None
Intent: PROFANITY
Keywords: None
Category: None
Filters: None

최종 답변: 부적절한 표현은 사용할 수 없어요.
문제 요약: The request was classified as profanity and intentionally did not enter RAG retrieval.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 없음
- hybrid top 결과: 없음
- rerank 후 결과: 없음
- selected chunks: 없음

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 시발련아
- evidence ranks: {}

원인 분류: OUT_OF_SCOPE_POLICY_ROUTE / log_only
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

## 6단계 개선안

### 크롤러 개선

- 본문 추출 품질 개선: document_assets 중 document_contents가 없는 첨부를 우선 재처리한다.
- UI/메뉴/목록/preview 텍스트 제거: 메뉴, breadcrumb, 목록 preview, 회의록/공고 하단 반복 텍스트를 chunk 전처리에서 제거한다.
- PDF/첨부 본문 추출 여부 확인: file_ext/parser_type별 추출 실패율을 로그화하고 ZIP/HWP/PDF를 별도 retry queue로 분리한다.
- static/index 페이지 chunk 제외 또는 낮은 가중치: source_type이 static/index/menu 성격이면 검색 score penalty를 적용한다.
- 중복 chunk 제거: content_hash뿐 아니라 normalized title+body 기반 중복 제거를 추가한다.
- 짧은/무의미 chunk 필터링: 120자 미만 또는 날짜/메뉴/링크 중심 chunk는 embedding/search 대상에서 제외하거나 낮은 가중치를 준다.
- 문서 타입별 metadata 강화: building/facility, department, scholarship, academic_calendar, shuttle/bus 같은 domain 태그를 crawler 단계에서 확정한다.

### Retrieval 개선

- keyword/category/filter 추출 검증: 건물명, 학과명, 부서명, 숫자/호관/버스번호가 rewrite 뒤에도 보존되는지 테스트한다.
- rewrite 전후 검색 결과 비교: original_query, rewritten_query, keywords 각각의 lexical/vector top-k를 저장해 나빠진 rewrite를 감지한다.
- filter relaxation 전략: selected_doc_count=0뿐 아니라 low-confidence일 때 department/category/time filter 제거 retry를 수행한다.
- lexical/vector top-k 확대: merge 전 후보를 최소 60개 이상 유지하고, short/static/source penalty는 merge 후가 아니라 후보 점수에 반영한다.
- hybrid RRF 또는 weighted merge 개선: 현재 weighted 모드에서 vector_norm이 강하게 작동하므로 lexical exact/strong term match를 더 크게 보정한다.
- score normalization 점검: lexical_score null, vector-only 후보가 final_score를 지배하는 케이스를 분리 로그화한다.
- doc type/source별 penalty: external_notice, council, attachment, static 메뉴성 문서가 domain query를 덮지 않도록 penalty를 둔다.
- attachment 공고/회의자료 잡음 완화: 제목/본문에 핵심 고유명사가 없으면 첨부 chunk의 rerank 상향을 제한한다.
- 정답 후보가 2~5위에 있을 때 selection 보정: selected top3가 모두 같은 source_type 또는 low evidence면 다음 후보를 섞는다.

### Rerank 개선

- rerank 전후 정답 후보 순위 비교 로그 추가: hybrid_rank, rerank_rank, selected_rank를 request_id별로 저장한다.
- reranker 입력 텍스트 길이 제한 점검: 제목/section/앞부분만 보고 첨부 공고를 과대평가하지 않도록 핵심문장 추출을 적용한다.
- 제목/본문/metadata 조합 개선: title exact match, source_type domain match, department match를 별도 신호로 기록한다.
- UI성 문서 penalty 적용: static/index/menu/회의록/외부채용 공고는 query family mismatch 시 강한 penalty를 둔다.
- rerank threshold 조정: strong_term_match가 낮은 후보는 base_score가 높아도 selected에서 제외한다.

### Fallback 개선

- fallback 조건 명확화: empty result뿐 아니라 top score 낮음, selected evidence 없음, answer negative 예상 케이스에도 fallback한다.
- category/filter 제거 fallback: filters/category/time_scope를 제거한 검색 결과와 원 결과를 비교한다.
- rewrite 제거 fallback: rewritten_query가 고유명사를 손상시키면 original_query 기반 검색으로 되돌린다.
- lexical-only/vector-only fallback 비교: 두 branch 중 evidence rank가 더 좋은 쪽을 selected 후보에 강제로 포함한다.

### Logging 개선

현재 로그는 selected_chunks 중심이라 후보 탈락 위치를 사후에 완전히 복원하기 어렵다. 다음 로그를 추가해야 한다.

- original_query
- rewritten_query
- extracted_keywords
- extracted_category
- applied_filters
- lexical_candidates
- vector_candidates
- merged_candidates
- reranked_candidates
- selected_chunks
- rejected_chunks
- rejection_reason
- fallback_reason
- final_context
- answer_grounding_score