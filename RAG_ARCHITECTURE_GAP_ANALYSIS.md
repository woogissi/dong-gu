# 동의대학교 RAG 챗봇 — 아키텍처 Gap 분석 보고서

> 작성 기준: 실제 코드(`rag/`, `crawler/`) + 골드셋 자동평가 로그(`rag/evaluation/goldset/`, 2026-06-01, 66문항).
> 모든 주장에 `파일:함수` 또는 로그 케이스 ID를 명시했다. 추정은 별도 표기했다.

---

## 핵심 요약 (먼저 읽을 것)

분석 의뢰는 "retrieval 품질 저하"를 전제했으나, **실측 데이터는 retrieval이 아니라 answer generation이 최대 병목**임을 보여준다.

| Metric | 값 | 해석 |
|---|---:|---|
| Top-1 Hit | 75.8% | 보충검색 과잉부스트로 일부 손실 |
| Top-3 Hit | 84.8% | |
| Top-5 Hit | 90.9% | 검색 자체는 정답을 잘 후보에 올림 |
| **Context Hit** | **90.9%** | **선택까지도 정답을 컨텍스트에 잘 넣음** |
| Answer Grounded | 87.9% | |
| **Answer Correct** | **71.2%** | **컨텍스트 대비 17%p 손실** |
| **Answer Refused** | **12.1%** | **정답이 있는데도 "못 찾음" 응답** |

출처: `rag/evaluation/goldset/goldset_eval_report.md`.

실패 13건의 단계 분포 (`failure_cases.md`):
- `answer_generation_issue` **7건** ← 정답이 컨텍스트에 있는데 LLM이 거절/누락
- `db_data_quality_issue` 4건 ← 정답 문서가 DB에 없음(크롤링 누락)
- `topk_selector_issue` 1건, `rerank_issue` 1건
- (별도) `pipeline_error` 1건 ← 연도 처리 버그

**결론: Context Hit(90.9%)와 Answer Correct(71.2%)의 격차를 메우는 것이 가장 비용 대비 효과가 크다.**

---

# 1. 현재 구조 요약 (End-to-End, 코드 기준)

```
사용자 질문
│
├─[Primary Intent] rag/preprocess/primary_intent.py:PrimaryIntentClassifier.classify()
│     규칙기반 3분류(PROFANITY / GENERAL / INFO). 비INFO는
│     rag/pipeline/chat_pipeline.py:_build_direct_answer()로 RAG 전체 우회
│
├─[Preprocess] rag/pipeline/preprocessor.py:QueryPreprocessor.run()
│     · normalize_query()            (normalizer.py)        NFKC + 85개 문맥치환 + 9개 정규식
│     · apply_synonym_filter()                              동의어 확장 → lexical_query
│     · extract_hybrid_keywords()    (hybrid_keyword_extractor) Aho + 정규식 + Kiwi 명사(최대 12)
│     · extract_entities()           (entity_extractor.py)  category/target/department/action/grade/time
│     · extract_query_features()     (query_features.py)    family(27종)/domain/protected/strong/required terms
│     · rewrite_query() +
│       rewrite_queries_from_bundle()(query_rewriter.py)    규칙기반 다중 쿼리 5~6개 변형
│     출력: PipelineState (state.py) + state.metadata["query_understanding"]
│
├─[Embed] rag/embedding/koe5_embedder.py:KoE5Embedder.embed_query()
│     "query: " prefix, nlpai-lab/KoE5, VECTOR(1024)
│
├─[Retrieve] rag/retrieval/retriever.py:retrieve_documents()
│     · Lexical : PostgreSQL FTS — to_tsvector('simple') + ts_rank_cd + ILIKE boost
│     · Vector  : pgvector HNSW, cosine(<=>)
│     · 도메인 보충검색 5종(아래)을 score 1.15~1.2 고정으로 prepend
│         _retrieve_canonical_documents_from_database_v4() (학사일정/수강신청)
│         _retrieve_graduation_policy_documents_from_database() (졸업)
│         _retrieve_department_curriculum_documents()         (학과 커리큘럼)
│         _retrieve_location_documents()                      (건물/위치)
│         _retrieve_faculty_documents()                       (교수)
│
├─[Merge] merge_retrieval_candidates() + _apply_hybrid_final_scores()
│     HYBRID_SCORE_MODE = weighted(기본 0.55/0.45) | max | rrf(k=60) | srrf
│
├─[Rerank] rag/selection/reranker.py:rerank_documents()
│     수제 30개 시그널 가중합(title/section/content match, faculty/department entity,
│     attachment/exif/ui noise, query_family_boost/penalty, recency, temporal …)
│
├─[Select] rag/selection/topk_selector.py:select_topk_with_diagnostics(k=3, max_chunks_per_doc=1)
│     dedup(chunk/doc) → 3단계 우선순위(exact/preferred/static_late)
│     → diversity 필터 + _is_context_contamination_candidate() 오염 필터
│
├─[Quality Gate] chat_pipeline.py:_evaluate_retrieval_quality()
│     미달 시 _fallback_retrieve() 5전략 체인
│     (original_query_no_rewrite / vector_only / relaxed_filters / increase_top_k / lexical_only)
│
├─[Rule Answer] chat_pipeline.py 룰기반 게이트(faculty/schedule/facility/cafeteria) → LLM 우회
│
├─[LLM] rag/prompt/prompt_builder.py:build_system_prompt()
│        + rag/llm/answer_generator.py:generate_answer()
│        OpenAI gpt-4o-mini(temp 0.2, max_tokens 800) | Ollama llama3.2:3b
│
└─[Postprocess] rag/generation/answer_postprocessor.py
       repair_negative_answer_with_context() + strip_markdown_formatting()
       → 최종 답변
```

모든 단계는 `rag/pipeline/state.py:PipelineState`에 누적되고 `to_log_dict()`로 직렬화되어
`retrieval_logs` / `retrieval_selected_chunks` / `response_logs` 테이블(`docker/postgres/init/init_db.sql`)에 기록된다.

**잘 설계된 부분:** 단계별 진단 로깅이 매우 상세하다. `state.metadata["query_understanding"]`에는
정규화·키워드·엔티티·rewrite 품질·feature·필터·적용 부스트가 전부 남고,
reranker는 문서마다 30개 시그널을 `metadata["rerank_signals"]`에 저장한다. 이 덕분에 본 분석의 단계별 원인 구분이 가능했다.

---

# 2. 업계 표준 RAG 대비 부족한 점

### 2.1 Query Understanding

| 기법 | 현재 구현 | 비고 |
|---|---|---|
| Intent 분류 | ✅ 규칙기반 (`primary_intent.py`) | INFO/non-INFO 게이트 |
| Entity Extraction | ✅ 사전+정규식 (`entity_extractor.py`) | 6필드 |
| Query Rewrite | ✅ 규칙기반 (`query_rewriter.py:rewrite_query`) | |
| Query Expansion | ✅ 동의어 사전 (`apply_synonym_filter`) | |
| Multi-Query | △ 번들 기반 5~6변형 | **전부 키워드 재배열 수준** |
| **HyDE** | ❌ 없음 | 가상 답변 임베딩으로 dense recall 보강 부재 |
| **Self-Query** | ❌ 없음 | 필터를 LLM이 아닌 정규식/사전으로만 추출 |

**영향(추정):** Multi-Query가 모두 어휘 재조합이라, 질문 어휘와 문서 어휘가 다른 경우(vocabulary mismatch)
recall이 dense 검색 한 갈래에만 의존한다. 예: "심리상담 어디서 받아?"(G036)는 정답이 "심리검사 | 학생상담센터"인데
어휘가 겹치지 않아 학과 교과목 페이지가 상위에 온다.

### 2.2 Retrieval

- **구현됨:** PostgreSQL FTS(BM25 유사 `ts_rank_cd`) + pgvector HNSW dense + hybrid(weighted/RRF k=60/SRRF).
  → RRF·SRRF에 도메인 보충검색까지 갖춘 점은 LangChain/LlamaIndex 기본 RAG 예제·OpenAI Cookbook 단순 예제보다 **앞선다**. (잘 설계된 부분)
- **약점 ①(중요):** 보충검색 5종이 **score 1.2 고정값으로 prepend**된다. 의미 정합과 무관하게 상단을 점유해
  정답을 밀어낸다(§3 G046/G049). Anthropic/최신 hybrid 권장 패턴은 "도메인 우선순위"를 가산점으로 주되
  **상한·조건을 두는데**, 여기선 고정 1.2가 사실상 무조건 1위를 만든다.
- **약점 ②:** FTS가 `to_tsvector('simple')` — 형태소 분석 없는 토큰화라 한국어 복합명사 분해를
  전적으로 전처리 키워드 확장에 의존한다(Kiwi는 optional, graceful degrade).

### 2.3 Chunking (`crawler/crawler/ingestion/chunker.py:DocumentChunker`)

- 설정: `max_chars=900`, `overlap_chars=100`. section_type/section_title/content_hash 메타데이터 부착, 첨부 분리,
  UI 스텁 제거 — **여기까지는 견고하다.**
- **부재(중요):** **Parent-Child / Auto-merging retrieval 없음.** 청크 단위로만 검색·선택하고
  selection은 `max_chunks_per_doc=1`(topk_selector.py)로 **문서당 1청크만** 컨텍스트에 넣는다.
  정적 페이지(기숙사 규정·도서관 안내)는 정보가 여러 청크에 흩어져 있어 근거가 단편화된다(§4 핵심 원인).
- 데이터 형식별: 정적/공지/PDF/HWP/HWPX/OCR 모두 텍스트 추출 후 동일 청커로 통합. OCR은 `korean_ocr.py`에서
  페이지 마커·EBook URL 제거 등 정제가 되어 있다.

### 2.4 Ranking

- **구현됨:** 수제 30시그널 reranker + 3단계 selection + contamination 필터. (정교하게 설계됨)
- **부재/위험:**
  - **Cross-encoder(신경망) reranker 없음** — 모든 시그널이 어휘 규칙 가중치라 의미 유사도를 직접 반영하지 못한다.
  - **Context Compression 없음** — 긴 컨텍스트를 그대로 LLM에 투입(§4와 직결).
  - selection의 `_is_context_contamination_candidate()`(`topk_selector.py:166`)가
    `query_family_boost ≥ 0.6 & heading_relevance ≤ 0 & exact_query_match ≤ 0 & strong_term_match ≤ 0.45`이면
    **본문이 정답이어도 탈락**시킬 수 있다. `content_match ≥ 0.3` 면제조항이 있지만, 제목이 약한 정답 문서엔 위험.

### 2.5 Answer Generation (`rag/prompt/prompt_builder.py`)

실제 system prompt(`_SYSTEM_RULES`)에서 발췌:
```
- 문서에서 답을 찾기 어려우면 "{NO_ANSWER_MESSAGE}"라고 답하세요.
- 질문과 직접 관련 없는 문서는 무시하세요.
```
- **위험 ①(최대 병목):** "답을 찾기 어려우면 못 찾았다고 답하라"는 **거절 유도 문구**가 명시적이다.
  컨텍스트가 길고 노이즈가 섞이면 LLM이 쉽게 이 출구로 빠진다(§4).
- **부재 ②:** **Citation(출처 표기) 강제 없음** — grounding 검증을 사후 패턴매칭(`answer_postprocessor`)에만 의존.
- **위험 ③:** gpt-4o-mini + temp 0.2 + 긴 멀티청크 컨텍스트 → needle-in-haystack 누락.

---

# 3. Retrieval 성능 저하 원인 (로그 근거)

순수 "검색 실패"는 소수다. 실제 손실은 **보충검색 과잉부스트 + DB 데이터 누락 + 버그**에서 발생한다.

| 케이스 | 질문 | 증상 | 단계 |
|---|---|---|---|
| **G046** | 컴퓨터공학과 홈페이지 | 정답=index.do인데 "이수표"(score 1.200) 2건이 상단 점유 → 정답 Top5 탈락 | 보충검색 과잉부스트 |
| **G049** | 경영학과 1학년 2학기 전공필수 | 정답=경영학과 교육과정인데 창업투자/부동산자산/스마트창업경영학과 이수표(각 1.200)가 상위 → 학과 엔티티 정합 실패 | 보충검색 과잉부스트 |
| **G044** | 교환학생 신청 방법 | 정답 미수집, 캠퍼스맵(1.200)이 상위 | DB 데이터 누락 |
| **G066** | 학생처 전화번호 | 정답=학생지원처 안내 미수집 | DB 데이터 누락 |
| **q019** | 2025년 학사일정 | `'in <string>' requires string as left operand, not int` → 파이프라인 자체 실패 | **버그** |

- G046/G049의 근본 원인: `_retrieve_department_curriculum_documents()`가 학과 의도면 무조건 이수표를 1.200으로 prepend.
  "홈페이지"·"전공필수" 같은 세부 의도를 무시한다.
- G049는 메모리 `project_dept_entity_fix`(학과 엔티티 Top1 67→100%)의 **회귀 신호**일 수 있다 → 골드셋 재확인 권장.
- q019는 연도 토큰이 int로 들어가 문자열 `in` 비교에서 터지는 **단순 버그**(수정 즉시 효과).

---

# 4. Answer 품질 저하 원인 (최대 병목, 로그 근거)

**공통 패턴: `Context Hit: True`(정답이 컨텍스트에 있음)인데 답변이 "찾지 못했습니다".** 7건.

| 케이스 | 질문 | rank1 컨텍스트 | 생성 답변 |
|---|---|---|---|
| **G001** | 보강 일정 알려줘 | 학사일정 페이지 score 1.150·1.140 (정답) | "보강 일정에 대한 정보를 찾지 못했습니다" |
| **G016** | 장학금 지급일 언제야 | 동의사랑 장학식비 지급 안내(정답 context hit) | "구체적인 정보는 찾을 수 없었습니다" |
| **G037** | 도서관 이용 시간 | 중앙도서관 안내(context hit) | "정보를 찾지 못했습니다" |
| **G038** | 콜라보라운지 운영시간 | 콜라보라운지 안내(context hit) | "운영시간에 대한 정보를 찾지 못했습니다" |
| **G033** | 기숙사 생활 규칙 | 효민생활관(context hit) | "구체적인 정보는 찾지 못했습니다" |
| **G036** | 심리상담 어디서 받아? | 학생상담센터(context hit) | "장소에 대한 정보는 찾지 못했습니다" |
| **q013** | 기숙사 생활 규칙 | context **16,796자**(효민생활관 멀티청크) | 거절. `diagnostic_reason: no_exact_or_strong_keyword_match` |

원인 3가지:
1. **거절 유도 프롬프트** (`prompt_builder.py`의 `NO_ANSWER_MESSAGE` 지시). LLM이 부분정보 합성보다 거절을 택함.
2. **긴 멀티청크 컨텍스트의 needle 누락** — q013은 16K자에 효민생활관 청크가 반복되며 정작 규칙 본문이 묻힌다.
   `max_chunks_per_doc=1` + parent-child 부재로 정답 근거가 단편화된 채 들어간다.
3. **`repair_negative_answer_with_context()`가 모든 거절을 복구하지 못함** — 발동 조건과 스니펫 추출 범위가 제한적
   (`answer_postprocessor.py:_ranked_doc_snippets()` 상위 3개 스니펫 한정).

> 참고로 selection 단계(`failure_analysis_latest.json` q013)에서 해당 문서의 rerank 시그널은
> `title_match 0.69`, `content_match 0.55`, `query_family_boost 6.2`로 매우 높았다.
> **검색·선택은 제대로 했고, 마지막 LLM 단계에서만 실패**했다는 결정적 증거다.

---

# 5. 가장 효과 큰 개선 Top 10 (중요도 순)

## High Impact / Low Cost — 즉시 적용, 효과 큼

**1. 거절 프롬프트 재설계** ⭐ 최우선
- 내용: `_SYSTEM_RULES`에서 거절 유도 문구를 약화하고 "컨텍스트에 부분 정보라도 있으면 그것을 우선 인용해 답하라.
  완전히 무관할 때만 못 찾았다고 하라"로 전환.
- 위치: `rag/prompt/prompt_builder.py:build_system_prompt()` (`_SYSTEM_RULES`)
- 효과(추정): 거절 7건 직접 타격 / 난이도 하

**2. 연도 처리 버그 수정 (`'in <string>' ... not int`)**
- 내용: temporal 비교에서 연도 토큰 int → str 캐스팅.
- 위치: `rag/retrieval/temporal.py` 또는 `query_features.py` 연도 비교부 (q019 스택)
- 효과: 파이프라인 실패 1건 제거 / 난이도 하

**3. negative-answer repair 강화**
- 내용: `Context Hit`인데 거절 응답이면 selected 문서 스니펫으로 답변을 합성하는 조건·커버리지 확대.
- 위치: `rag/generation/answer_postprocessor.py:repair_negative_answer_with_context()` / `_ranked_doc_snippets()`
- 효과: #1과 함께 거절 복구율 상승 / 난이도 하~중

**4. 보충검색 고정 score 조건화**
- 내용: 5종 보충검색의 1.2 고정값을 "쿼리-제목 의미 정합"이 일정 수준 이상일 때만, 또는 가산점+상한 방식으로 변경.
- 위치: `rag/retrieval/retriever.py:_retrieve_department_curriculum_documents()` 외 4종
- 효과: G046·G049류 오상위 해소(학과별 Top5 67%→개선) / 난이도 중

## High Impact / Medium Cost

**5. 정적 페이지 `max_chunks_per_doc` 완화**
- 내용: static/index/menu/dormitory 등은 문서당 2~3청크 허용(이미 diversity 예외 존재 → 자연스럽게 정렬).
- 위치: `rag/selection/topk_selector.py`
- 효과: q013·G033·G037 근거 단편화 해소 / 난이도 중

**6. LLM 기반 Multi-Query 1~2개 추가**
- 내용: 규칙 변형 대신 LLM이 동의 질의를 생성 → 기존 RRF 병합 파이프라인에 합류.
- 위치: `rag/pipeline/preprocessor.py` + `rag/retrieval/retriever.py`(merge)
- 효과: 어휘 불일치 질의(G036류) recall 향상 / 난이도 중

**7. Citation 강제 + grounding 프롬프트**
- 내용: 답변에 근거 문서/섹션 표기를 요구해 hallucination과 거절을 동시 억제.
- 위치: `rag/prompt/prompt_builder.py`
- 효과: 정확도·신뢰도 동반 상승 / 난이도 중

**8. DB 데이터 누락 4건 재수집**
- 내용: G044(교환학생)/G046(컴공 홈)/G049(경영 교육과정)/G066(학생처) URL 재크롤링.
- 위치: `crawler/crawler/run/run_retry_failed_documents.py` (`--from-retry-queue`)
- 효과: `db_data_quality_issue` 4건 → Hit 전환 / 난이도 중(크롤러 운영)

## High Impact / High Cost

**9. Cross-encoder reranker 도입**
- 내용: 한국어 cross-encoder로 1차 후보 재정렬, 수제 30시그널은 보조 신호로 강등.
- 위치: `rag/selection/reranker.py` (신규 스코어러)
- 효과: 의미 유사도 반영, 어휘기반 한계 돌파 / 난이도 상(모델·인프라)

**10. Parent-Child / Auto-merging Retrieval**
- 내용: 청크로 검색하되 부모 섹션/문서 단위로 컨텍스트 확장. 긴 정적 페이지 근거 단편화 근본 해소.
- 위치: `crawler` 청킹 + `rag/retrieval/retriever.py` + `rag/selection/topk_selector.py`
- 효과: §4의 구조적 원인 제거 / 난이도 상

---

# 6. 예상 성능 향상 효과 (추정 + 근거)

| 지표 | 현재 | 개선 후(추정) | 근거 |
|---|---:|---:|---|
| Top1 Hit | 75.8% | ~85% | #4 보충검색 조건화로 G046·G049류 오상위 해소(학과별 67%→상승) + #2 버그 제거 |
| Top3 Hit | 84.8% | ~90% | 동일 + #8 데이터 재수집 |
| Context Hit | 90.9% | ~95% | #5 멀티청크 허용 + #8 누락 보완 |
| **Answer Correct** | **71.2%** | **~88%** | #1·#3로 거절 7건 중 5~6건 복구, Refused 12.1%→~3%, 상한=Answer Grounded 87.9% |

**추정 방식(보수적):**
- 거절 7건은 **모두 Context Hit True** → 정답 근거가 이미 컨텍스트에 있으므로 프롬프트/repair 개선만으로 대부분 정답 전환 가능. 상한은 현재 Answer Grounded(87.9%).
- DB 누락 4건은 재수집 시 Hit→정답 전환.
- 보충검색 조건화는 학과별 카테고리(현재 Top5 67%, `goldset_eval_report.md`)에 집중 효과.
- 가장 확실한 이득은 **Answer Correct 71.2% → ~88%**: 추가 검색·모델 투자 없이 프롬프트/후처리 수정만으로 달성 가능한 구간이다.

---

# 부록. 잘 설계된 부분 (균형 평가)

무조건적 비판을 피하기 위해, 업계 기본 예제 대비 **앞서 있는** 설계를 명시한다.
- **Hybrid merge 완성도:** weighted뿐 아니라 RRF(k=60)·SRRF까지 구현(`retriever.py`). 대부분 튜토리얼은 단순 가중합에 그친다.
- **도메인 보충검색 전략:** recall 보강을 위한 5종 canonical 검색 — 방향성은 옳다(부작용은 §3, 고정 score만 조정하면 됨).
- **진단 로깅 인프라:** `state.metadata` 30시그널 + `retrieval_logs`/`retrieval_selected_chunks` 스냅샷. 본 분석을 가능케 한 핵심 자산.
- **selection의 관심사 분리:** dedup / diversity / contamination을 분리한 3단계 우선순위(`topk_selector.py`).
- **평가 자동화:** 골드셋 66문항 + 단계별 실패 귀속(`failure_cases.md`, `failure_analysis_latest.json`). 이 인프라가 있어 "어느 단계가 문제인가"를 데이터로 답할 수 있었다.

> **한 줄 결론:** 이 시스템은 retrieval 골격이 이미 탄탄하다(Context Hit 90.9%). 다음 한 걸음은
> 검색 고도화가 아니라 **마지막 LLM 답변 단계의 거절·누락을 막는 것**이며, 이는 프롬프트·후처리 수정만으로
> 가장 큰 정확도 상승(약 +17%p)을 얻을 수 있는 저비용 구간이다.
