# RAG 품질 개선 작업 프롬프트

아래 작업은 `dong-gu/reports/rag_log_failure_report.md`와 `dong-gu/reports/rag_log_failure_report.json`의 실제 Supabase 로그 분석 결과를 기준으로 수행한다.

## 목표

사용자 질문과 최종 답변이 어긋나는 RAG 품질 문제를 코드 레벨에서 수정한다.

특히 최근 INFO/RAG 로그 15건에서 확인된 다음 문제를 우선 해결한다.

- D. 노이즈 문서가 상위 context에 섞임: 9건
- B. 데이터는 있지만 검색 실패: 3건
- C. 검색은 됐지만 selection/rerank 실패: 3건
- fallback 사용: 2건
- DB에는 관련 후보가 있는데 retrieval/selected chunk와 겹치지 않는 사례 다수

분석 당시 실제 로그는 `query_logs`, `response_logs`, `retrieval_logs` 각각 15건뿐이므로, 20건 이상을 가정하거나 임의 생성하지 않는다.

## 반드시 참조할 파일

- `reports/rag_log_failure_report.md`
- `reports/rag_log_failure_report.json`
- `rag/preprocess/query_rewriter.py`
- `rag/preprocess/query_analysis.py`
- `rag/preprocess/keyword_extractor.py`
- `rag/preprocess/hybrid_keyword_extractor.py`
- `rag/retrieval/retriever.py`
- `rag/retrieval/search_strategy.py`
- `rag/selection/reranker.py`
- `rag/selection/topk_selector.py`
- `rag/selection/context_builder.py`
- `rag/pipeline/chat_pipeline.py`
- `rag/llm/answer_generator.py`
- `backend/app/database/retrieval_logs.py`
- 관련 테스트: `rag/tests/**`, `backend/tests/**`

## 대표 실패 query

아래 query를 회귀 테스트 또는 수동 검증 기준으로 사용한다.

- query_id 482: `정보공학관 2층에 뭐 있어`
- query_id 477: `1번 건물 이름`
- query_id 483: `동의대 동아리 정보`
- query_id 473: `컴퓨터공학과 2학년 전공필수 과목`
- query_id 472: `컴퓨터공학과 이수표 정보`
- query_id 469: `7대 총장 누구야?`
- query_id 478: `동의대 23번 건물 이름`
- query_id 475: `동의대 23번 건물 정보`
- query_id 474: `IPP사업 정보`
- query_id 481: `정보공학관 편의점 위치`
- query_id 480: `정보공학관은 몇번 건물?`
- query_id 476: `정보공학관 정보`
- query_id 471: `7대 총장 정보`
- query_id 470: `동의대 7대 총장 정보`
- query_id 479: `23번 건물은 정보공학관?`

## 우선 수정 범위

### 1. Query preprocessing / rewriting

문제:

- 숫자+건물, 건물명+층, 학과+이수표, 학과+학년+전공필수 같은 질의에서 핵심어가 약해지고 일반어가 많이 남는다.
- protected term 누락 또는 형태 변형이 발생한다.

수정 방향:

- 다음 패턴을 strong/protected entity로 보존한다.
  - `숫자 + 번 + 건물`
  - `건물명 + 층`
  - `정보공학관`
  - `컴퓨터공학과`
  - `이수표`
  - `전공필수`
  - `동아리`
  - `IPP`
  - `총장`
- rewrite/query variants 전체에서 protected term이 사라지지 않게 한다.
- 단, `동의대`, `정보`, `안내` 같은 범용어는 protected term으로 과보호하지 않는다.

### 2. Filter / category extraction

문제:

- `department` filter에 `학과사무실` 같은 실제 corpus facet으로 쓰기 어려운 값이 들어가 검색 범위가 왜곡된다.

수정 방향:

- department/site/page_type filter는 실제 corpus facet 값과 매칭될 때만 적용한다.
- 필터 적용 전 후보 수와 적용 후 후보 수를 로그에 남긴다.
- 필터 적용 후 후보가 급감하거나 0개가 되면 필터를 완화하거나 fallback branch를 실행한다.

### 3. Lexical search / hybrid merge

문제:

- DB에는 관련 후보가 있는데 retrieval 후보와 겹치지 않는 B 유형이 있다.
- lexical/vector final_score가 rerank 전 후보 적합성을 충분히 보장하지 못한다.

수정 방향:

- strong_terms는 title, section_title, chunk content에 별도 가중치를 둔다.
- 시설/건물/위치 질의는 vector보다 lexical/title exact signal을 우선한다.
- query family별 fusion weight를 분리한다.
  - building/location/facility query
  - department curriculum query
  - person/title query
  - club/program query
- branch별 minimum evidence gate를 둔다.

### 4. Rerank / TopK selection

문제:

- 후보에는 관련 chunk가 있으나 selected에서 밀리는 C 유형이 있다.
- duplicate_doc_ratio가 높은 케이스에서 반복 chunk가 context를 잠식한다.
- UI/menu/share/SNS/footer 성격의 텍스트가 selected chunk에 섞인다.

수정 방향:

- rerank_signals에 `strong_term_match`, `exact_heading_match`, `required_entity_match` 하한을 둔다.
- selected context에는 다음 gate를 적용한다.
  - max chunks per doc
  - near duplicate content hash 제한
  - source diversity
  - UI noise penalty/gate
  - attachment noise 유지
- 건물/위치 질의에서는 `campus map`, `건물번호`, `정보공학관`, `층` 같은 신호를 강하게 반영한다.

### 5. Context formatting / citation mapping

문제:

- selected chunk에는 source_url이 있으나 답변이 어떤 근거에서 왔는지 추적하기 어렵다.
- chunk 제목/본문/출처 경계가 불명확해 LLM이 근거를 혼동할 수 있다.

수정 방향:

- context를 chunk 단위로 구조화한다.
  - chunk_id
  - title
  - source_url
  - source_type
  - content_type
  - score / lexical_score / vector_score / rerank_score / final_score
  - content
- response metadata에 사용된 chunk_id/source_url/citation trace를 저장한다.
- 사용자 노출 citation과 내부 디버그 citation을 분리한다.

## 테스트 요구사항

코드 수정 후 최소한 다음 검증을 수행한다.

- 기존 단위 테스트 실행
  - `python -m unittest` 또는 repo에서 사용 중인 테스트 명령 확인 후 실행
- RAG 관련 테스트 추가 또는 보강
  - query rewrite protected term 보존
  - filter facet 검증
  - strong_terms lexical 가중치
  - rerank strong term gate
  - TopK duplicate/noise gate
  - context metadata/citation trace
- 대표 query 15개를 fixture로 두고, selected chunk의 source/title이 질문군과 명백히 맞는지 검증한다.

## 성공 기준

- `정보공학관 2층에 뭐 있어`가 교직과정/교육과정 chunk를 선택하지 않는다.
- `1번 건물 이름`이 교육과정 PDF chunk를 선택하지 않는다.
- `정보공학관은 몇번 건물?`, `23번 건물은 정보공학관?`은 건물번호/캠퍼스맵/컴퓨터공학과 위치 근거를 우선 선택한다.
- `컴퓨터공학과 이수표 정보`, `컴퓨터공학과 2학년 전공필수 과목`은 학과/교육과정 근거를 우선 선택한다.
- `동의대 동아리 정보`는 동아리 관련 페이지들을 선택하되, 답변에서 “확인할 수 없다”류 문장을 근거와 모순되게 생성하지 않는다.
- selected chunk에 HOME, 공유, SNS, 메뉴, footer, copyright 등 UI 노이즈가 상위 context로 들어가지 않는다.
- retrieval log에 필터 적용 전후 후보 수, strong_terms, rerank signals, selected/rejected reason이 남는다.

## 작업 원칙

- Supabase 실제 데이터는 수정하지 않는다.
- 리포트에 없는 데이터를 추측하지 않는다.
- 먼저 코드 흐름을 읽고 기존 패턴을 따른다.
- 수정 범위는 RAG preprocessing, retrieval, rerank, selection, context/logging에 한정한다.
- 크롤러/DB 스키마 변경이 꼭 필요하면 별도 계획으로 분리하고, 즉시 적용하지 않는다.
- 수정 후 테스트 결과와 남은 리스크를 요약한다.
