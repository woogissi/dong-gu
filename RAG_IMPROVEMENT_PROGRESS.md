# RAG 개선 작업 진행 보고서 (핸드오프)

> 목적: `RAG_ARCHITECTURE_GAP_ANALYSIS.md` 기반 개선의 진행 상황을 새 컨텍스트에서 이어가기 위한 인수인계 문서.
> 최종 갱신: 2026-06-02. 기준 평가: `rag/evaluation/goldset/` 골드셋 66문항.

---

## 0. 한 줄 요약

Gap 분석의 결론(병목 = retrieval이 아니라 **answer generation 거절/누락**)에 따라 저비용 개선을
2라운드로 적용했다. **1라운드(#1~5) 골드셋 검증 완료** — Answer Refused 12.1%→3.0%, Answer Correct
71.2%→78.8%. **2라운드(A+B+D)는 코드+단위테스트 완료, 골드셋 재평가만 남음(아래 §4가 다음 작업).**

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

## 3. 2라운드 (A+B+D) — 코드+단위테스트 완료, 골드셋 재평가 대기

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

---

## 4. ▶ 다음 작업 (즉시 할 일)

**2라운드 골드셋 재평가가 아직 안 돌았다. 이것이 첫 작업이다.**

```
# (현재 goldset_eval_report.md는 1라운드 결과 = 2라운드의 baseline)
cd C:/Users/1199h/Desktop/dev/dong-gu
cp rag/evaluation/goldset/goldset_eval_report.md rag/evaluation/goldset/goldset_eval_report.round1.md
docker compose run --rm rag python -m rag.evaluation.goldset.run_goldset_eval
```

확인 포인트(전후 비교):
- **개선 기대:** G044(캠퍼스맵 1.2 제거), G046(스니펫 마크업 제거), G049(경영학과 정확매칭 상위),
  G060(AX공지 페널티 → 교육과정 상위).
- **회귀 감시:** `failure_cases.md`에서 기존 통과 케이스(특히 학과별·교육과정·기숙사/도서관)가
  D1/D2로 깨지지 않았는지. 깨지면 D2(-2.0)부터 의심 — `_CURRICULUM_NOTICE_EXEMPT_TERMS` 확대 또는
  D2 롤백 고려.
- 지표: Top-1/Top-5/Context/Answer Correct/Refused.

검증 후 단위테스트 재확인:
```
docker compose run --rm rag sh -c "pip install -q pytest && python -m pytest rag/tests/test_answer_postprocessor.py rag/tests/test_reranker.py rag/tests/test_prompt_builder.py rag/tests/test_selection.py rag/tests/test_temporal_year_regression.py -q"
```

---

## 5. 남은 개선 (미착수, 우선순위순)

**별도 운영 단계 (코드 아님, 승인됨):**
- DB 누락 재크롤링 3건: **G044**(교환학생)·**G046**(컴공 홈 index.do)·**G066**(학생처/학생지원처).
  ```
  docker compose run --rm crawler python -m crawler.run.run_rag_load_check --create-retry-queue
  docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --limit 20 --execute
  ```
  ※ G046은 A로 1.2 부스트는 제거됐으나 정답 페이지가 DB에 없어 재크롤링 필요.

**평가 신뢰도 점검:**
- **G066/G044**는 답변이 실제로는 맞는 정보(phone.do 번호 등)를 냈는데 gold_document URL이 달라
  오답 판정. `deu_rag_goldset.yaml`의 gold_documents 보강 검토 → 지표 정확도 향상.

**남은 rerank 난제 (저비용으로 안전 해결 어려움):**
- **G064**(전과 학점인정): 본청 공지(`gra-notice.do?articleNo=`)가 전과 규정 페이지를 누름.
  이 공지들은 `_is_department_board_notice`에서 의도적으로 제외(정답인 경우 많음) → 페널티가
  위험. cross-encoder(#9) 영역.
- **G034/G037**(학생식당/도서관): 정답 문서는 상위인데 정답 청크가 top-3 컨텍스트에서 누락
  (selection/parent-child 영역, #10).

**보고서 중·고비용 미적용 항목:** #6 LLM Multi-Query, #7 Citation 강제, #9 Cross-encoder reranker,
#10 Parent-Child retrieval.

---

## 6. 내가 변경한 파일 (working tree, 미커밋)

**소스:**
- `rag/prompt/prompt_builder.py` (#1)
- `rag/generation/answer_postprocessor.py` (#2, B)
- `rag/pipeline/chat_pipeline.py` (#2 호출부, #4)
- `rag/retrieval/retriever.py` (#3, A)
- `rag/selection/reranker.py` (D1, D2)

**테스트:**
- `rag/tests/test_prompt_builder.py` (#1)
- `rag/tests/test_answer_postprocessor.py` (#2, B)
- `rag/tests/test_reranker.py` (D1)
- `rag/tests/test_temporal_year_regression.py` (#5, 신규)

**그 외 미커밋(내 작업 아님):** `domain_knowledge.py`, `entity_extractor.py`, `normalizer.py`,
`query_features.py` 등. 커밋 시 분리 권장.

**관련 메모리:** `[[project_answer_gen_fix]]`, `[[project_rag_gap_analysis]]`.
