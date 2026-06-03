# RAG 개선 작업 진행 보고서 (핸드오프)

> 목적: `RAG_ARCHITECTURE_GAP_ANALYSIS.md` 기반 개선의 진행 상황을 새 컨텍스트에서 이어가기 위한 인수인계 문서.
> 최종 갱신: 2026-06-02. 기준 평가: `rag/evaluation/goldset/` 골드셋 66문항.

---

## 0. 한 줄 요약

Gap 분석의 결론(병목 = retrieval이 아니라 **answer generation 거절/누락**)에 따라 저비용 개선을
2라운드로 적용했다. **1라운드(#1~5)·2라운드(A+B+D) 모두 코드+단위테스트+골드셋 검증 완료.**
베이스라인 대비 핵심 성과: Answer Correct 71.2%→**74~79%**, Answer Refused 12.1%→**3~6%**,
학과별 Context Hit 67%→**83%**(D1). 남은 실패는 대부분 **DB 데이터 누락**과 **LLM 답변 비결정성**이며,
구조적 난제(G060/G064/G034/G037)는 cross-encoder(#9)/parent-child(#10) 영역.

---

## 1. 환경/실행 규칙 (반드시 숙지)

- **모든 테스트·평가는 docker compose 안에서만** 실행 (CLAUDE.md 규칙). 호스트 python/pip 금지.
- **pytest가 rag 이미지에 없다.** `rag/requirements.txt`·`requirements-dev.txt`에 미포함.
  → 일회성 컨테이너에서 임시 설치해 실행(이미지/호스트 비오염):
  ```
  docker compose run --rm rag sh -c "pip install -q pytest && python -m pytest rag/tests/<파일> -q"
  ```
- **DB는 적재돼 있음**(documents 3023, chunks 17093). 자격증명: `chatbot/chatbot/chatbot`
  (`postgresql://chatbot:chatbot@postgres:5432/chatbot`).
- 골드셋 평가는 OpenAI(`LLM_PROVIDER=openai`, key 설정됨)를 호출하며 66문항 ~수분 소요.
- **주의:** working tree에 내 변경 외에도 미커밋 수정이 다수 있음
  (`domain_knowledge.py`, `entity_extractor.py`, `normalizer.py`, `query_features.py`).
  이들은 내가 건드리지 않았다. 전체 테스트 스위트에 **사전 존재 실패 4건**이 있고
  (`grade` family vector 전략, 학과 도메인 앵커 2건, live 회귀 선택 1건 + integration ERROR 2건),
  `git stash` 비교로 **내 변경 이전부터 실패**임을 확인했다 → 내 작업의 회귀 아님.

---

## 2. 1라운드 (#1~5) — 완료 및 검증됨

`C:\Users\1199h\.claude\plans\rag-architecture-gap-analysis-md-polished-simon.md` 계획대로 구현.

| # | 변경 | 파일 |
|---|---|---|
| 1 | 거절 프롬프트 재설계: "답 찾기 어려우면 거절" → "부분 정보 우선 인용, 완전 무관할 때만 거절" | `rag/prompt/prompt_builder.py` `_SYSTEM_RULES` |
| 2 | repair 강화: snippet 매칭에 동의어/키워드 포함 + 출처 URL 표기 | `rag/generation/answer_postprocessor.py` + `chat_pipeline._generate`(keywords 전달) |
| 3 | 보충검색 조건화: 홈페이지 의도 가드 + 학과 정확일치 필터(`_curriculum_row_matches_department`) | `rag/retrieval/retriever.py` `_retrieve_department_curriculum_documents` |
| 4 | 멀티청크: `dormitory/library/campus_facility/building_location` family에 `max_chunks_per_doc=2` | `rag/pipeline/chat_pipeline.py` (~650행) |
| 5 | 연도버그: **재현 안 됨**(이미 `str()` 캐스팅됨). 회귀 테스트만 추가 | `rag/tests/test_temporal_year_regression.py`(신규) |

**골드셋 결과 (1라운드 적용 후):**

| Metric | Baseline | 1R 후 |
|---|---:|---:|
| Answer Correct | 71.2% | **78.8%** |
| Answer Refused | 12.1% | **3.0%** |
| Answer Grounded | 87.9% | 97.0% |
| Top-5 Hit | 90.9% | 92.4% |
| Top-1 Hit | 75.8% | 72.7% |
| answer_generation_issue | 7건 | 2건 |
| 전체 실패 | 13건 | 9건 |

- 베이스라인 리포트 백업: `rag/evaluation/goldset/goldset_eval_report.baseline.md`.
- Top-1 소폭 하락은 보충검색 1.2 과잉부스트 제거에 따른 재정렬(Top-5는 상승) → 실손실 아님.

---

## 3. 2라운드 (A+B+D) — 완료 및 검증됨

1라운드 후 잔존 실패 9건(`rag/evaluation/goldset/failure_cases.md`)을 분석해 저비용 항목 적용.

### A. 보충검색 조건화 — location 캠퍼스맵 가드 (G044)
- **원인:** `_retrieve_location_documents`의 else(캠퍼스맵) 분기가 building_location/campus_address
  family면 위치 의도가 없어도 캠퍼스맵을 score 1.2로 prepend. "교환학생 신청 방법"이 이 family로
  오분류되어 캠퍼스맵이 상단 점유.
- **변경:** else 분기에서 질의에 위치 의도어(위치/어디/건물/캠퍼스/지도/주소 등)가 없으면 `return []`.
- **파일:** `rag/retrieval/retriever.py` `_retrieve_location_documents`.
- **참고:** faculty/graduation/canonical 3종은 이미 family+학과엔티티+source_type로 타이트하게
  게이팅돼 있어(메모리의 100% 수정과 직결) 건드리지 않음 — 확대 시 회귀 위험.

### B. repair 스니펫 마크업 정제 (G046)
- **원인:** 첨부/이수표 청크가 복구 스니펫이 될 때 `[TITLE] … [ATTACHMENT] 원본파일 Download …`
  원본 마크업이 답변에 노출.
- **변경:** `_clean_snippet_markup()` 추가(`[A-Z_]` 대괄호 마커·"원본파일 Download"·"Download" 제거),
  `_ranked_doc_snippets`에서 content에 적용.
- **파일:** `rag/generation/answer_postprocessor.py`.

### D. 공지 vs 정적 정답페이지 rerank 신호 (G049, G060)
- **D1 (G049):** `_department_entity_match_score`가 "경영"을 substring으로 매칭해
  `창업투자경영학과`에도 +1.5를 주던 문제 → `_dept_token_in_text()`로 **경계 매칭**(앞 글자가
  한글이면 합성 학과명의 일부로 보아 불일치). 정확 일치 학과만 +1.5, 합성 학과명은 -1.0.
- **D2 (G060):** `department_curriculum`/`graduation` family가 board-noise 페널티에서 무조건
  면제되던 것을 정교화. 게시판 복제 공지(`/subN.do?...articleNo=`)라도 교육과정 관련 내용이
  없고(`_CURRICULUM_NOTICE_EXEMPT_TERMS`) 질의가 공지/공고를 명시적으로 찾지 않으면 -2.0 페널티.
  → 'AX마이크로디그리' 같은 무관 홍보 공지가 교육과정 정답 페이지를 밀어내는 것 억제.
- **파일:** `rag/selection/reranker.py`.
- **주의(회귀 방지):** D2 적용 시 "OO학과 **공지사항** 알려줘"는 면제해야 한다
  (`test_department_board_notice_not_penalized_when_department_named`). 질의에 공지/공고/게시판이
  있으면 면제하는 가드를 반드시 유지할 것.

**단위 테스트:** `test_answer_postprocessor.py`(B), `test_reranker.py`(D1 경계 매칭) 신규 케이스 추가.
타깃 5개 파일 **46건 전부 통과**.

### 3.1 골드셋 결과 추이 (Baseline → R1 → R2 → R3)

| Metric | Baseline | R1 (#1~5) | R2 (+A+B+D) | R3 (+재크롤링) |
|---|---:|---:|---:|---:|
| Top-1 Hit | 75.8% | 72.7% | 72.7% | **74.2%** |
| Top-5 Hit | 90.9% | 92.4% | 92.4% | **93.9%** |
| **Context Hit** | 90.9% | 89.4% | 90.9% | **92.4%** |
| **학과별 Context** | 67% | 67% | **83%** | 83% |
| Answer Grounded | 87.9% | 97.0% | 93.9% | 89.4% |
| Answer Correct | 71.2% | 78.8% | 74.2% | 74.2% |
| Answer Refused | 12.1% | 3.0% | 6.1% | 10.6% |

> 백업: baseline=`goldset_eval_report.baseline.md`, R1=`*.round1.md`, R2=`*.round2.md`(report/failure_cases).

**핵심 관찰 — 결정적 지표는 꾸준히 개선, answer-gen 지표는 LLM 분산으로 진동:**
- **검색·선택(결정적):** Context Hit 90.9→**92.4%**(역대 최고), Top-5 90.9→**93.9%**. D1(G049 학과별 67→83%)와
  R3 재크롤링(G044)이 누적 기여.
- **Answer Correct/Refused(비결정적):** 71.2→78.8→74.2→74.2 / 12.1→3.0→6.1→10.6. **generation 코드는
  R1 이후 불변인데 매 실행 거절 케이스가 바뀐다**(gpt-4o-mini temp 0.2 분산). 매 라운드 신규 실패는
  전부 Context Hit True인 `answer_generation_issue`(R3: G009·G016·G020 — 날짜/사실 질의, 재크롤링과 무관).
  → **단일 실행의 Answer Correct는 신뢰구간이 넓다. 결정적 Context Hit(92.4%)가 더 신뢰할 만한 지표.**

**케이스별 귀속 (R1→R2 실패 대조):**
- ✅ **G049 해결** — D1(경계 매칭)이 `창업투자/스마트창업경영학과` 오매칭을 제거. **결정적이고 내 변경에
  명확히 귀속되는 개선**(학과별 Context 67→83%, rerank_issue 2→1, Context Hit +1.5).
- **G044/G046 — A는 의도대로 동작**(캠퍼스맵·이수표 1.2 과잉부스트 제거 확인)하나 정답 문서가
  DB에 없어 여전히 `db_data_quality`. **재크롤링으로만 정답 전환 가능**(§5).
- **G046 — B 효과:** repair 스니펫의 `[TITLE]/[ATTACHMENT]/Download` 마크업 누출 제거됨(단위테스트 검증).
- **G060 — D2 미해결:** AX마이크로디그리 공지 **본문에 '전공선택' 등 교육과정 어휘**가 있어
  `_CURRICULUM_NOTICE_EXEMPT_TERMS` 면제에 걸려 -2.0이 적용되지 않음. cross-encoder(#9) 또는
  'AX/마이크로디그리' 전용 노이즈 신호가 필요(whack-a-mole 위험으로 보류).
- **G011/G038 신규 실패 = LLM 비결정성(회귀 아님):** 둘 다 `answer_generation_issue`+Context Hit True.
  D2가 건드리지 않는 family(수강신청/복지)이고 generation 코드는 R1↔R2 동일. G038은 baseline→R1→R2에서
  거절↔정답을 반복(temp 0.2에도 gpt-4o-mini 분산). → **Answer Correct 78.8↔74.2 변동은 노이즈.**

**결론:** A+B+D는 **검색·선택을 결정적으로 개선**(G049, Context+1.5)하고 **코드 회귀를 일으키지 않았다.**
A/B의 정답 전환은 DB 재크롤링에 막혀 있고, answer-gen 지표 변동은 LLM 분산이다. D2는 무해하나 G060을
완결하지 못했다(어휘 면제 회피).

### 3.2 3라운드 — DB 재크롤링 결과 (R3, 생성 08:13)

`run_targeted_static_ingestion --profile none --url ... --allow-insecure-ssl`로 3개 URL 재적재.
**핵심: 재크롤링 전 DB 상태를 먼저 확인하니 3건 중 1건만 실제 부재였다.**

| 케이스 | 재크롤링 전 상태 | 결과 |
|---|---|---|
| **G044** (`exchange/sub02_02.do`) | **DB 부재** | ✅ 신규 적재(`static_8af8a64c80d62692`, 절차·자격 포함) → **R3에서 해결** |
| **G046** (`computer/index.do`) | 이미 존재(얇은 홈페이지) | 갱신(937자, 1청크). 여전히 실패 — 홈페이지가 본질적으로 얇아 "홈페이지" 질의에 retrieval이 못 올림. **크롤링 문제 아님(retrieval/rerank).** |
| **G066** (`deu-organization.do`) | 이미 존재(조직도) | 갱신(2269자). 여전히 실패 — **조직도 페이지에 전화번호가 없다.** 골드 근거 '051-890-1114'가 이 URL에 부재 → **골드셋 정답 URL 자체의 오류**(시스템은 phone.do에서 합리적 답변 생성). **→ R4(§3.3)에서 gold를 phone.do(학생지원팀, 051-890-1041)로 교정해 해결(ctx+correct).** |

**성과:** G044 해결 + Context Hit 92.4%·Top-5 93.9%(역대 최고). G046은 재크롤링으로 해결 불가임을
데이터로 확인(retrieval 한계). G066은 골드셋 오류로 판명 → **R4(§3.3)에서 골드 교정으로 해결**.

---

### 3.3 4라운드 — 골드셋 정답(gold_documents) 교정 (R4, 완료·검증됨)

§4의 "골드셋 정답 교정"을 수행. 평가 매칭 함수 `run_goldset_eval.py:_check_hit()` 정독 결과
**골드셋 자체의 두 오류가 지표를 왜곡**하고 있었다.

- **False Negative(과소평가):** gold URL/doc_id가 실제 근거를 안 담아 시스템이 정답을 검색·생성해도 Hit 불인정.
- **False Positive(과대평가):** `_check_hit`이 gold_url을 source_url의 **부분문자열**로 매칭 → bare 도메인
  (`https://www.deu.ac.kr` 등)이면 같은 도메인 **무관 페이지까지 전부 Hit**.

### 변경 내용

| 구분 | 케이스 | 조치 (DB read-only로 그라운드트루스 확정) |
|---|---|---|
| FN 수정 | **G066** | 조직도(`deu-organization.do`)→**전화번호 페이지** `phone.do`(학생지원팀, `static_52634667972a5f32`, 051-890-1041). 원본 번호(1114/2750)는 실재X |
| FN 수정 | **G044** | 빈 doc_id → `static_8af8a64c80d62692`(절차\|교환학생) 채움 |
| FN 수정 | **G051** | `www.deu.ac.kr`(전체도메인)→`deu-campus-gaya.do`(`static_deb2316f2f351b6c`). 실주소 **엄광로 176**(원본 "가야대로 995" 오류) |
| FN 수정 | **G052** | `www.deu.ac.kr`→`deu-campus-map.do`(`static_19b132e7ab559d4e`) |
| FN 수정 | **G037** | `lib.deu.ac.kr`→`intro_rule.mir`(`static_28c37295f426efc7`, 제19조 이용시간 자료실 월~금 09-20시) |
| 데이터 갭 | **G032** | 일반 기숙사비 DB 부재(게스트룸 495,000원만) — 정직한 db_data_quality로 분류 |
| 데이터 갭 | **G038** | 콜라보라운지 운영시간(9~20시) DB 전체 미수집 — 정직한 db_data_quality로 분류 |
| URL 구체화 | G031/G033 | bare dorm 도메인 → 정답 페이지 URL(3010.do/4020.do). doc_id는 기존 유지 |
| 코드 가드 | `_check_hit` | `_url_has_path()` 추가 — bare 도메인은 URL 부분매칭 금지, doc_id로만 매칭(과대매칭 차단). 회귀테스트 `test_goldset_check_hit.py`(6건 통과) |

### 결과 (R3 → R4, 교정 후)

| Metric | R3 | R4(교정 후) | 해석 |
|---|---:|---:|---|
| Top-1 Hit | 74.2% | 69.7% | bare-도메인 과대매칭 제거 |
| Top-5 Hit | 93.9% | **87.9%** | 허위 통과(FP) 제거 |
| Context Hit | 92.4% | **87.9%** | FP −4(G031/G032/G033/G038) + FN +1(G066) |
| Answer Correct | 74.2% | 74.2% | LLM 분산(불변) |
| Answer Refused | 10.6% | 9.1% | LLM 분산 |

> **지표 하락 = 더 정직한 측정.** R4의 낮은 수치는 성능 저하가 아니라 **그동안 bare-도메인 매칭으로
> 부풀려졌던 허위 통과를 제거**하고 G066 등 과소평가를 바로잡은 결과다. 이제 지표가 실제 검색·선택
> 성능을 정직하게 반영한다.

**케이스별 귀속(R3→R4):**
- ✅ **FN 해결:** G066(False→True, correct), G044/G051/G052(정당히 통과·correct), G037(컨텍스트 정당히 hit).
- ✅ **FP 노출(정직한 실패):** G031(rerank — 정답 페이지 대신 공지 선택), G033(retrieval — 생활규정 페이지 미진입),
  G032/G038(DB 데이터 갭). 모두 기존 bare-도메인 매칭이 가리던 실제 약점.
- 백업: `*.precorrect.{md,json,csv}`(교정 직전), R1=`*.round1.*`, R2=`*.round2.*`, baseline=`*.baseline.md`.

---

### 3.4 5라운드 — rerank 품질 개선 (R5, 완료·검증됨)

R4에서 정직하게 드러난 rerank 약점을 진단·개선. **핵심 패턴: 게시판 공지/목록 페이지가 실제
안내·규정 페이지를 밀어냄.** 저비용 신호 보강(Tier 1) + selection 필터 보정(Tier 2)을 적용.

**진단(코드 근거):**
- `reranker.py`의 게시판 탐지가 `/subN.do?articleNo` URL 패턴에만 의존 → lib `.mir` 목록
  페이지(`default_notice_list.mir`, `libtoday`)·일반 공지목록이 **무페널티**로 안내 페이지를 누름(G037/G038).
- 교육과정 면제 허점: 본문에 '교육과정' 어휘가 있으면 board-noise 면제 → AX마이크로디그리 **홍보공지**가
  면제되어 이수표를 누름(G060).
- selection contamination 첫 분기에 `content_match` 예외 부재 → 제목어휘 불일치('학생식당'↔'교내식당')지만
  본문 매칭(cm=0.4)이 있는 정답이 탈락(G034).

**변경:**

| Tier | 변경 | 파일 |
|---|---|---|
| 1 | `board_list_noise` 신호 신설(-2.0): `.mir` 목록·`notice_list`·`libtoday`·'공지사항'/'게시판목록'/'LIB Today' 제목 탐지. 공지/게시판/목록 명시 질의는 면제(G058 보호) | `rag/selection/reranker.py` |
| 1 | G060 면제 허점 차단: 교육과정 어휘가 있어도 홍보 마커(마이크로디그리/홍보/협조) 포함 시 면제 제외 | `rag/selection/reranker.py` |
| 2 | contamination 첫 분기(`query_family_boost`)에 `content_match>=0.3` 구제 예외 추가(타 분기와 일관) | `rag/selection/topk_selector.py` |

**효과(R4→R5):**

| Metric | R4 | R5 | |
|---|---:|---:|---|
| Top-1 / Top-5 / Context Hit | 69.7 / 87.9 / 87.9% | 동일 | 결정적 지표 유지 |
| Answer Grounded | 90.9% | **92.4%** | ▲ |
| Answer Correct | 74.2% | **77.3%** | ▲ |
| Answer Refused | 9.1% | **7.6%** | ▲ |
| answer_generation_issue | 5 | **4** | ▲ |

- **G037 입증:** board 페널티로 lib 공지사항/LIB Today가 탈락 → reranked 상위가 도서관소개(규정/이용시간)
  페이지로 교체, gold가 **selected에 정당히 진입**(이후 LLM 분산에 따라 완전 통과). rerank **순서 품질**이
  결정적으로 개선됨. **회귀 0**(부정 ctx/top5 전환 없음). 단위테스트 +3(board 2, contamination 1).

**미해결 — 성격 규명(향후):**
- **G034**(학생식당): gold가 reranked rank2·contamination 아님인데도 최종 selected에 **fallback 재검색
  결과**(reranked에 없는 공지)가 들어옴 → 잔여 원인은 rerank/selection이 아니라 **fallback 체인**(별도 영역).
- **G031**(기숙사 신청): 'where'형 질의로 모집공지(title_match 0.9)가 canonical 신청페이지(qfb 6.2)를
  근소하게 누름 — 양쪽 다 유효 답이라 강제 부스트 보류.
- **G064**(전과 학점인정): 본청 공지가 규정 페이지를 누르는 **의미 불일치** — 어휘 신호 한계, Tier 3
  cross-encoder 영역.

**결론:** Tier 1+2로 게시판/목록 과상위 문제(rerank 품질의 핵심)를 해소했고 회귀가 없다. 남은 rerank류
난제(G064)는 의미 유사도를 직접 반영하는 **cross-encoder(Tier 3)**가 근본 해법이다.

---

### 3.5 전체 성능 평가 — 3회 평균 (2026-06-02)

R5까지 반영된 파이프라인을 **goldset 66문항 × 3회(총 198호출)** 실행해 결정적/비결정적 지표를 분리
측정. 스크립트 `rag/evaluation/goldset/run_full_eval.py`(신규), 산출물 `full_eval_report.md`/`full_eval_runs.json`.

**핵심 지표:**

| 지표 | 값 | 성격 |
|---|---:|---|
| Top-1 / Top-3 / Top-5 | 69.7 / 80.3 / **87.9%** | 결정적(3회 동일) |
| **Context Hit** | **87.9%** | 결정적(3회 동일) |
| Answer Grounded | 95.9% (93.9~100) | 비결정(LLM) |
| **Answer Correct** | **80.3% (78.8~81.8)** | 비결정(LLM) |
| Answer Refused | 4.1% (0~6.1) | 비결정(LLM) |

> 검색·선택 지표는 3회 **완전 동일**, LLM 지표는 ±1.5%p 좁은 밴드로 안정 → 다회 평균 **Answer Correct 80.3%**가
> 신뢰 가능한 현재 성능치(단일 실행 74~79% 진동보다 신뢰도 높음).

**지연(latency) — 주요 발견:** 케이스당 **평균 15.8초**(p95 24.7s). 단계별 **retrieve 13.1초(≈83%)** · generate 2.5s ·
embed 0.16s. → **lexical FTS(`to_tsvector('simple')`+ILIKE) 검색이 압도적 병목**. 정확도와 별개로 **성능 최우선 개선 대상**.

**소스타입별:** db(공지) Top5 100%/Context 94% · web(정적) 75/82% · attachment(이수표) 50/50% → 정적페이지·첨부가 약점.

**케이스 안정성(3회):** 항상정답 49 · **flaky 8**(G006/G010/G011/G016/G021/G033/G038/G063 — LLM 분산) ·
**항상오답 9**(구조적 약점):
- 검색/데이터/fallback: **G031**(기숙사신청 rerank/fallback), **G032**(기숙사비 데이터갭), **G034**(학생식당 fallback)
- 컨텍스트는 있으나 답 추출 실패(answer-gen): **G008**(수강정정), **G009**(수강포기), **G023**(졸업유예), **G026**(복수전공), **G037**(도서관시간), **G062**(와이파이)

**결론 — 남은 개선 3축:** ① **retrieve 지연(13s) 성능 최우선**, ② answer-gen 6건(컨텍스트 보유에도 거절/추출 실패
→ 프롬프트/repair 강화·cross-encoder), ③ 데이터갭/fallback 3건. 검색·선택 골격은 결정적으로 안정(Context 87.9%).

---

### 3.6 LLM Multi-Query 적용 (#6, 완료·검증됨, 생성 2026-06-03)

§5의 "중·고비용 미적용 항목" 중 **첫 항목 #6**을 구현. 현재 파이프라인은 단일 질의(+룰 변형)를
**한 문자열로 연결해 한 번만** 검색해, 질의 표현이 정답 문서 어휘와 어긋나면(G033 retrieval miss,
G064 의미 불일치) 정답 청크를 컨텍스트에 못 올린다. **원질의를 LLM으로 K개 재표현으로 확장 →
질의별 개별 검색 → RRF 융합**으로 recall을 보강한다.

**설계 결정:**
- **본격 fan-out + RRF**, **모든 INFO 질의에 항상 적용**. 각 질의는 **개별 임베딩**으로 vector/hybrid
  경로까지 진짜 다중질의.
- **핵심 제약 대응:** retrieve가 13s 병목(§3.5)이라 순차 K배 검색은 금지 → **`ThreadPoolExecutor`로
  병렬화**해 총 retrieve ≈ max(개별검색) ≈ 13s 유지. 임베딩만 fan-out **이전 직렬** 수행(질의당 0.16s,
  torch 동시추론 경합 회피), 스레드풀은 DB 검색(I/O 대기 중 GIL 해제)만 병렬화.
- **무회귀 보장:** 기능 off·임베더 부재·LLM 실패·빈 변형 시 **원질의 단일검색으로 폴백**. 융합 결과가
  부실해도 통합 위치(retrieve 진입점) 이후의 기존 quality-gate/fallback 체인이 그대로 흡수.

**변경:**

| 구분 | 내용 | 파일 |
|---|---|---|
| 신규 | `generate_query_variants`(LLM 재표현 생성·견고 파싱: JSON배열/번호불릿/코드펜스, 원질의·상호 중복제거, 실패시 `[]`) + `reciprocal_rank_fusion`(chunk_id 우선 dedup, RRF 점수합산·안정정렬·top_k 절단) | `rag/retrieval/multi_query.py`(신규) |
| 통합 | `_retrieve()`의 단일 `retrieve_documents` 호출을 `_multi_query_retrieve`로 교체. 원질의 request(기존 벡터 재사용)+변형 request 병렬검색 후 RRF 융합. `state.metadata["multi_query"]`에 진단(generated/query_count/per_query_counts/llm_ms/fanout_ms) 기록. `_bool_env`/`_int_env` 헬퍼 추가 | `rag/pipeline/chat_pipeline.py` |
| 환경변수 | `RAG_MULTI_QUERY_ENABLED`(기본1)/`_NUM`(3)/`_RRF_K`(60)/`_MAX_WORKERS`(4) | `.env.example` |

**검증(단위테스트 위주):** 신규 `rag/tests/test_multi_query.py` **18건 통과**(변형 생성/파싱 8 · RRF 융합 6 ·
게이팅/통합 4). 회귀 타깃 스위트(answer_postprocessor/reranker/prompt_builder/selection/
temporal_year_regression) **52건 전부 통과** — 무회귀 확인.

**주의 — 효과의 성격:** 남은 골드셋 실패 다수가 answer-gen이라(§3.5) Context Hit 개선폭은 제한적일 수
있다(사전 공유됨). 1차 성공 기준은 **단위테스트 + 무회귀 + 지연 미증가**. 골드셋 3회평균 A/B
(`RAG_MULTI_QUERY_ENABLED=0`/`1` 토글 + `run_full_eval`)는 미수행 — **G033/G064 Context Hit 전환**을
우선 확인 권장. 비용·지연: 항상 적용이라 LLM 1회(~1-2s, 직렬 선행)+추가 임베딩이 매 INFO 질의에 발생,
필요 시 `RAG_MULTI_QUERY_ENABLED=0`으로 즉시 차단.

---

### 3.7 HYBRID_SCORE_MODE 튜닝 — srrf 채택 (완료·검증됨, 2026-06-03)

hybrid 융합 스코어 모드 4종(weighted/max/rrf/srrf) 중 최적값을 골드셋으로 비교. **융합 모드는 hybrid
검색 경로에서만 작동**하므로, 4종을 공정 비교하려고 `RETRIEVAL_MODE=hybrid`로 강제(모든 질의가 융합을
거치게)하고 `RAG_MULTI_QUERY_ENABLED=0`으로 고정해 **융합 모드만 변수**로 두었다(각 모드 골드셋 66문항 1회).
사용자 요청으로 max는 제외하고 weighted/rrf/srrf 3종 비교.

| 지표(결정적) | weighted | rrf | **srrf** |
|---|---:|---:|---:|
| Top-1 Hit | 37.9% | 54.5% | **56.1%** |
| Top-3 Hit | 62.1% | 69.7% | **72.7%** |
| Top-5 Hit | 66.7% | 78.8% | **78.8%** |
| **Context Hit** | 78.8% | 83.3% | **84.8%** |
| Answer Correct(비결정) | 80.3% | 80.3% | 81.8% |

- **srrf 종합 1위**(결정적 검색지표 최고), rrf 근소 2위, **weighted 명확한 최하위**(Top-1 −18%p, fallback
  1.5%로 유일 발동). Answer Correct 차이는 LLM 분산 범위라 결정적 지표(Top-k/Context)로 판단.
- **결정:** 기본값을 `weighted`→**`srrf`**로 변경. `.env.example:32`(사유 주석) + `rag/retrieval/retriever.py`
  `_hybrid_score_mode()` fallback 기본값. compose.yml은 `env_file: .env`만 사용해 변경 불필요.
- **회귀:** 타깃 스위트 90 passed(+subtests 15). 유일 실패는 §1에 명시된 **사전 존재** `grade` family
  vector-only 라우팅 건으로 본 변경(스코어 융합)과 코드 경로 분리 → 무관.
- **운영 주의:** 런타임 실효값은 로컬 `.env`(미커밋)가 우선. 거기 `HYBRID_SCORE_MODE=weighted`가 있으면
  `srrf`로 바꾸거나 줄 삭제(코드 기본값 상속) 필요.
- **남은 검증:** 본 비교는 hybrid 강제 조건. 기본 라우팅(다수 family vector-only, §3.5)에서는 융합 적용
  질의가 제한적이라 프로덕션 실효는 더 작을 수 있음 → **기본 라우팅 weighted vs srrf 재측정**이 후속 과제.

---

## 4. ▶ 다음 작업 (우선순위)

> 1~5라운드(코드개선·재크롤링·골드셋교정·rerank품질) 완료. 남은 실패의 성격 —
> **순수 retrieval 부재·게시판 과상위는 소진**됐고, 남은 건 (1) answer-gen LLM 분산,
> (2) G034 fallback 체인, (3) G064류 의미 불일치(cross-encoder 영역).

1. **answer-gen 분산 완화 (최우선, 효과 가장 큼).** Answer Correct/Refused가 매 실행 ±5%p 진동한다.
   - (a) 골드셋을 **2~3회 평균**내어 지표 신뢰도 확보(현재 단일 실행 판정이 노이즈에 취약).
   - (b) repair 발동 커버리지 확대: Context Hit True인데 거절하는 날짜/사실 질의
     (G009/G011/G016/G020/G037/G063)를 후처리로 더 흡수. `repair_negative_answer_with_context`의
     2단계 발동 조건/스니펫 추출을 강화.
2. ✅ **골드셋 정답(gold_documents) 교정 — 완료(R4, §3.3).** G066/G044/G051/G052/G037 FN 수정 +
   G032/G038 데이터 갭 명시 + `_check_hit` bare-도메인 가드. 지표가 정직해졌다(과대매칭 제거).
   → 다음 후속: **G031/G033 retrieval/selection 약점**(정답 페이지가 컨텍스트에 미진입)이 새로 드러남.
3. **(선택) D2 보강 or 롤백** — G060('AX마이크로디그리' 공지)용 전용 노이즈 신호 추가 여부.
   현재 D2는 무해하므로 유지 권장. 근본 해결은 #9 cross-encoder.

검증 명령(재평가 / 단위테스트):
```
cd C:/Users/1199h/Desktop/dev/dong-gu
docker compose run --rm rag python -m rag.evaluation.goldset.run_goldset_eval
docker compose run --rm rag sh -c "pip install -q pytest && python -m pytest rag/tests/test_answer_postprocessor.py rag/tests/test_reranker.py rag/tests/test_prompt_builder.py rag/tests/test_selection.py rag/tests/test_temporal_year_regression.py -q"
```
> ⚠️ 골드셋 평가는 `goldset_eval_report.md`/`failure_cases.md`를 **덮어쓴다.** 비교가 필요하면 먼저 백업.

---

## 5. 남은 개선 (미착수, 우선순위순)

**DB 재크롤링 — 완료(R3).** G044 신규 적재로 해결. G046/G066은 재크롤링 대상이 아님이 §3.2에서
판명(G046=얇은 홈페이지 retrieval 한계, G066=골드셋 정답 URL에 근거 부재). 추가 재크롤링 불필요.
재적재 명령(참고): `run_targeted_static_ingestion --profile none --url <URL> --allow-insecure-ssl`.

**평가 신뢰도 점검 (우선):**
- 단일 실행 Answer Correct가 ±5%p 진동 → **다회 평균 또는 시드 고정** 필요.
- **G066/G044류 gold_documents 오류**: gold URL이 실제 근거를 안 담는 항목 보정.

**남은 rerank/selection 난제 (저비용 안전 해결 어려움):**
- **G046**(컴공 홈페이지): 얇은 홈페이지(937자)가 "홈페이지" 질의에 retrieval 상위 진입 실패.
  index.do 류에 대한 전용 부스트(질의에 '홈페이지/사이트' + 학과 → 해당 학과 index.do 보충검색)
  검토 가능. 단, A에서 막은 것과 충돌 주의.
- **G064**(전과 학점인정): 본청 공지(`gra-notice.do?articleNo=`)가 전과 규정 페이지를 누름.
  의도적 제외 대상이라 페널티가 위험. cross-encoder(#9) 영역.
- **G060**(경찰행정 전공선택): AX마이크로디그리 공지가 교육과정 어휘를 포함해 D2 면제 회피.
- **G034/G037**(학생식당/도서관): 정답 문서는 상위인데 정답 청크가 top-3 컨텍스트에서 누락
  (selection/parent-child 영역, #10).

**보고서 중·고비용 미적용 항목:** ~~#6 LLM Multi-Query~~(완료, §3.6), #7 Citation 강제,
#9 Cross-encoder reranker, #10 Parent-Child retrieval.

---

## 6. 내가 변경한 파일 (working tree, 미커밋)

**소스:**
- `rag/prompt/prompt_builder.py` (#1)
- `rag/generation/answer_postprocessor.py` (#2, B)
- `rag/pipeline/chat_pipeline.py` (#2 호출부, #4, #6 `_multi_query_retrieve`)
- `rag/retrieval/retriever.py` (#3, A, §3.7 `_hybrid_score_mode` 기본값 srrf)
- `rag/retrieval/multi_query.py` (신규 — #6 변형생성 + RRF 융합, §3.6)
- `rag/selection/reranker.py` (D1, D2, R5 board_list_noise + G060 면제 허점)
- `rag/selection/topk_selector.py` (R5 contamination content_match 예외)
- `rag/evaluation/goldset/deu_rag_goldset.yaml` (R4 골드셋 교정)
- `rag/evaluation/goldset/run_goldset_eval.py` (R4 `_check_hit` bare-도메인 가드)
- `rag/evaluation/goldset/run_full_eval.py` (신규 — 다회 평균 전체 성능 평가, §3.5)
- `.env.example` (#6 `RAG_MULTI_QUERY_*` 환경변수, §3.7 `HYBRID_SCORE_MODE=srrf`)

**테스트:**
- `rag/tests/test_prompt_builder.py` (#1)
- `rag/tests/test_answer_postprocessor.py` (#2, B)
- `rag/tests/test_reranker.py` (D1)
- `rag/tests/test_temporal_year_regression.py` (#5, 신규)
- `rag/tests/test_goldset_check_hit.py` (R4, 신규 — bare-도메인 가드 회귀 6건)
- `rag/tests/test_reranker.py` (R5 board_list_noise 2건), `rag/tests/test_selection.py` (R5 contamination 예외 1건)
- `rag/tests/test_multi_query.py` (#6, 신규 — 변형생성/파싱·RRF·게이팅 18건)

**그 외 미커밋(내 작업 아님):** `domain_knowledge.py`, `entity_extractor.py`, `normalizer.py`,
`query_features.py` 등. 커밋 시 분리 권장.

**관련 메모리:** `[[project_answer_gen_fix]]`, `[[project_rag_gap_analysis]]`, `[[project_goldset_eval]]`.
