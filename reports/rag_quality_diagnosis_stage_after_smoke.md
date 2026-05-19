# RAG 품질 저하 단계별 진단 리포트

## 전체 요약

- 총 분석 query 수: 54
- 실패/의심 케이스 수: 5
- 원인별 분포:
  - crawler/data 부족: 0
  - query rewrite 문제: 0
  - keyword/category/filter: 2
  - lexical search 문제: 1
  - vector search 문제: 0
  - hybrid merge 문제: 0
  - rerank 문제: 0
  - fallback 문제: 0
  - final generation 문제: 0
  - mixed: 0
  - out_of_scope: 2

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

### Query ID: 315

원 질문: 지천관 위치가 어떻게 돼?
Rewrite: 지천관 위치 방법 절차
Intent: GENERAL
Keywords: ['지천관', '위치']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: DB evidence exists, but intent/routing bypassed RAG.

검색 후보:
- lexical top 결과: 1. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (0.555555553200804); 2. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (0.555555553200804); 3. 2026년도 한국연구재단 체험형 청년인턴(장애) 채용 안내 (0.473684217130709)
- vector top 결과: 1. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (0.358180693279547); 2. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (0.350715558252202); 3. 동의대학교 효민생활관 (0.339692730940257)
- hybrid top 결과: 1. 동의대학교 효민생활관 (0.8797060237976162); 2. 동의대학교 효민생활관 (0.8772106284612424); 3. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (0.5000000000000001)
- rerank 후 결과: 1. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (3.596353); 2. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (3.587022); 3. 교내 사고 발생 시 보고 절차 (2.216626)
- selected chunks: 1. 2026학년도 신입생 수강신청 관련 안내(신입생 필독) (3.596353); 2. 2026학년도 1학기 1학년 신입생 및 복학생 수강신청 안내 (3.587022); 3. 교내 사고 발생 시 보고 절차 (2.216626)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 지천관, 지천관 위치 방법 절차, 지천관 위치가 어떻게 돼?
- evidence ranks: {'lexical': 1, 'vector': 1, 'hybrid': 3, 'reranked': 1, 'selected': 1}

원인 분류: keyword/category/filter / query_analysis
수정 제안: intent/category/filter 추출을 보수화하고, 고유명사 보존 및 filter relaxation fallback을 추가한다.

### Query ID: 317

원 질문: 동의대 정보관의 정보를 알고 싶어
Rewrite: 동의대 정보관 알고 싶어
Intent: GENERAL
Keywords: ['동의대', '정보관', '정보', '알고', '싶어']
Category: None
Filters: {}

최종 답변: 잘 이해하지 못했어요.
학교 관련 질문을 해주시면 더 정확히 도와드릴게요!
문제 요약: DB evidence exists, but intent/routing bypassed RAG.

검색 후보:
- lexical top 결과: 1. 동의대학교 대외협력팀 (0.615384618911517); 2. 찾아오는 길 | 학생지원처 (0.534883720930233); 3. 홍보영상 | 동의소식 | 정보광장 (0.512195123369533)
- vector top 결과: 1. 조직도 | 대학기관/규정 | DEU (0.632697723347085); 2. 찾아가는 동행 온라인 진로멘토링 > 동의대학교(DONG_EUI UNIVERSITY) 입학안내 (0.632372504644543); 3. 동의대신문 | 학생기구 | 학생활동 | 대학생활 (0.631029195005443)
- hybrid top 결과: 1. 동의대학교 대외협력팀 (0.55); 2. 찾아오는 길 | 학생지원처 (0.47805232284157506); 3. 홍보영상 | 동의소식 | 정보광장 (0.45777438888791666)
- rerank 후 결과: 1. 동의대학교 직원 채용 안내_정보화개발팀 (2.609305); 2. 동의대신문 | 학생기구 | 학생활동 | 대학생활 (2.119229); 3. 동의대학교 대외협력팀 (2.02)
- selected chunks: 1. 동의대학교 직원 채용 안내_정보화개발팀 (2.609305); 2. 동의대신문 | 학생기구 | 학생활동 | 대학생활 (2.119229); 3. 동의대학교 대외협력팀 (2.02)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 정보관, 동의대 정보관 알고 싶어, 동의대 정보관의 정보를 알고 싶어
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: keyword/category/filter / query_analysis
수정 제안: intent/category/filter 추출을 보수화하고, 고유명사 보존 및 filter relaxation fallback을 추가한다.

### Query ID: 320

원 질문: 학교내 편의점 어디에 있어
Rewrite: 학교내 편의점
Intent: INFO
Keywords: ['학교내', '편의점']
Category: None
Filters: {}

최종 답변: 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요. 학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.

사이트 바로가기: https://www.deu.ac.kr/
문제 요약: Evidence exists, but logged retrieval returned or selected zero chunks.

검색 후보:
- lexical top 결과: 1. 복지문화시설 | 편의·복지 | 대학생활 (0.428571436356525); 2. 복지문화시설 | 편의·복지 | 대학생활 (0.428571436356525)
- vector top 결과: 1. 복지문화시설 | 편의·복지 | 대학생활 (0.450635373592377); 2. 복지문화시설 | 편의·복지 | 대학생활 (0.436926688964766); 3. 동의대학교 효민생활관 (0.381799354338726)
- hybrid top 결과: 1. 복지문화시설 | 편의·복지 | 대학생활 (1.075); 2. 복지문화시설 | 편의·복지 | 대학생활 (1.0613106439398052); 3. 동의대학교 효민생활관 (0.41626103612948384)
- rerank 후 결과: 1. 복지문화시설 | 편의·복지 | 대학생활 (3.1); 2. 복지문화시설 | 편의·복지 | 대학생활 (3.084719); 3. 동의대학교 효민생활관 (1.464663)
- selected chunks: 1. 복지문화시설 | 편의·복지 | 대학생활 (3.1); 2. 동의대학교 효민생활관 (1.464663); 3. 동의대학교 효민생활관 (1.403038)

정답 근거 DB 존재 여부: 있음
- 근거 탐색어: 학교내, 편의점, 학교내 편의점, 학교내 편의점 어디에 있어
- evidence ranks: {'lexical': 1, 'vector': 1, 'hybrid': 1, 'reranked': 1, 'selected': 1}

원인 분류: lexical search 문제 / retrieval_empty
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 329

원 질문: 시발
Rewrite: 시발
Intent: PROFANITY
Keywords: ['시발']
Category: None
Filters: {}

최종 답변: 부적절한 표현은 사용할 수 없어요.
문제 요약: Profanity route intentionally bypassed RAG.

검색 후보:
- lexical top 결과: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(3월 2차) (0.333333333333333)
- vector top 결과: 1. 동의대학교 대외협력팀 (0.215278331604203); 2. 동의대학교 대외협력팀 (0.2151095759738); 3. 학부 Undergraduate | 장학금 | 외국인 입학 | 국제교류처 국제교류팀 (0.17049769040956)
- hybrid top 결과: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(3월 2차) (0.4650000000000001); 2. 동의대학교 대외협력팀 (0.45); 3. 동의대학교 대외협력팀 (0.44964724720265403)
- rerank 후 결과: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(3월 2차) (3.53292); 2. 스위스 바이오헬스 시장의 숨은 다섯 가지 규칙 (-0.817261); 3. 동의대학교 대외협력팀 (-0.83871)
- selected chunks: 1. [한국장애인개발원] 장애청년 채용 취업 정보 안내(3월 2차) (3.53292); 2. 스위스 바이오헬스 시장의 숨은 다섯 가지 규칙 (-0.817261); 3. 동의대학교 대외협력팀 (-0.83871)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 없음
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: out_of_scope / policy_route
수정 제안: 후보 로그를 추가한 뒤 동일 query를 재실행해 탈락 단계를 확정한다.

### Query ID: 330

원 질문: 시발련아
Rewrite: 시발련아
Intent: PROFANITY
Keywords: ['시발련아']
Category: None
Filters: {}

최종 답변: 부적절한 표현은 사용할 수 없어요.
문제 요약: Profanity route intentionally bypassed RAG.

검색 후보:
- lexical top 결과: 없음
- vector top 결과: 1. 교육안내 | BLS센터 | 부설교육 | 교육 (0.210223913192749); 2. [후원의 집] 밝은세상안과 3~4월 우대 혜택 안내 (0.199053248734869); 3. 2026학년도 전기 외국인특별전형 2차 모집 예비 합격자 발표 / 2026 Spring Semester 2nd Round Result (0.18373296454752)
- hybrid top 결과: 1. 교육안내 | BLS센터 | 부설교육 | 교육 (0.45); 2. 교육안내 | BLS센터 | 부설교육 | 교육 (0.3782071738874024); 3. [정부지원] AI와 빅데이터를 활용한 인지중재 실버케어 개발자(자바풀스택) 훈련생 모집 안내 (0.35725363008453814)
- rerank 후 결과: 1. [정부지원] AI와 빅데이터를 활용한 인지중재 실버케어 개발자(자바풀스택) 훈련생 모집 안내 (-0.660261); 2. 교육안내 | BLS센터 | 부설교육 | 교육 (-0.8); 3. 교육안내 | BLS센터 | 부설교육 | 교육 (-0.991448)
- selected chunks: 1. [정부지원] AI와 빅데이터를 활용한 인지중재 실버케어 개발자(자바풀스택) 훈련생 모집 안내 (-0.660261); 2. 교육안내 | BLS센터 | 부설교육 | 교육 (-0.8); 3. Q&A (-1.077871)

정답 근거 DB 존재 여부: 없음/불확실
- 근거 탐색어: 시발련아
- evidence ranks: {'lexical': None, 'vector': None, 'hybrid': None, 'reranked': None, 'selected': None}

원인 분류: out_of_scope / policy_route
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