# Top-K Hit Rate 향상 방안 분석

> 기준 데이터: `retrieval_eval_real_final.csv` (36개 질문)  
> 측정일: 2026-05-30

---

## 1. 현황 및 실패 패턴 분류

### 전체 지표

| 지표 | 수치 |
|---|---|
| Top-1 Hit | 52.8% (19/36) |
| Top-3 Hit | 63.9% (23/36) |
| Context Hit | 97.2% (35/36) |

**Context Hit 97.2% vs Top-3 Hit 63.9% — 33%p 갭이 핵심 문제.**  
문서는 top-20 안에 거의 다 들어오는데, top-3 안에 선택되지 못하는 구조적 원인이 있다.

---

### 전략별 성능 비교

| 전략 | 질문 수 | Top-1 | Top-3 |
|---|---|---|---|
| **vector** | 20 | **60.0%** | **70.0%** |
| hybrid | 16 | 43.8% | 56.2% |

vector가 hybrid보다 Top-1 +16.2%p, Top-3 +13.8%p 높다.  
→ **현재 어휘(BM25) 가중치 0.55가 오히려 랭킹을 해치는 카테고리가 존재한다.**

---

### 실패 패턴 3분류

| 유형 | 건수 | 설명 |
|---|---|---|
| **A. 랭킹 문제** | 4건 | Top-1 miss / Top-3 hit — 문서는 있는데 1위가 아님 |
| **B. 선택 문제** | 13건 | Top-3 miss / Context hit — top-20엔 있는데 top-3에 못 들어옴 |
| **C. DB 미수집** | 1건 | Context miss — 해당 문서 자체가 DB에 없음 |

---

#### 유형 A — 랭킹 문제 (4건)

| ID | 카테고리 | 질문 | 전략 |
|---|---|---|---|
| r021 | department_curriculum | 간호학과 2학년 1학기 전공필수 | vector |
| r022 | department_curriculum | 경찰행정학과 3학년 2학기 전공선택 | vector |
| r027 | dormitory | 기숙사 신청 어디서 해? | hybrid |
| r029 | career | 취업지원 프로그램 어디서 봐? | hybrid |

**공통 원인**: reranker가 학과명 개체를 1위 문서에서 정확히 매칭하지 못함.  
`r021`, `r022`는 간호학과·경찰행정학과 문서가 첨부파일(`section_type=attachment`)이라 `-0.8~-1.2` 페널티를 받아 2~3위로 밀림.

---

#### 유형 B — 선택 문제 (13건)

| ID | 카테고리 | 질문 | 전략 |
|---|---|---|---|
| r007 | academic_schedule | 여름계절학기 기간 | hybrid |
| r014 | scholarship | 국가장학금 신청 어디서 해? | hybrid |
| r015 | tuition | 등록금 고지서 어디서 봐? | hybrid |
| r016 | grade | 성적 확인 어디서 해? | hybrid |
| r017 | academic_admin | 학적 조회 어디서 해? | hybrid |
| r018 | graduation | 컴퓨터공학과 졸업학점 | vector |
| r019 | department_curriculum | 컴퓨터공학과 홈페이지 | vector |
| r020 | department_curriculum | 시각디자인과 2학년 1학기 전공필수 | vector |
| r024 | department_curriculum | 인공지능학과 4학년 1학기 전공선택 | vector |
| r025 | department_curriculum | 경영학과 1학년 2학기 전공필수 | vector |
| r028 | certificate | 재학증명서 발급 방법 | vector |
| r030 | academic_admin | 와이파이 사용 방법 | hybrid |
| r034 | dormitory | 기숙사 비용 | hybrid |

**공통 원인**:  
- `department_curriculum` 7건: 학과 커리큘럼 문서가 HWP/PDF 첨부파일 → attachment_noise_penalty 적용 → top-3 탈락  
- `"어디서"` 패턴 4건(r014/r015/r016/r017): 방법·절차 쿼리인데 BM25이 절차 설명이 없는 문서를 상위로 올림  
- `r007` 여름계절학기: "계절학기" 청크 분산, 현장실습 모집 문서가 상위를 차지

---

#### 유형 C — DB 미수집 (1건)

| ID | 카테고리 | 질문 | 비고 |
|---|---|---|---|
| r031 | welfare_facility | 정보관 학생식당 운영시간 | `topk_selector_issue`, fallback 발동 |

→ 정보공학관 학생식당 운영시간 정보가 크롤링 대상 URL에 미포함.  
크롤링 시드에 해당 URL 추가로 단독 해결 가능.

---

## 2. 근본 원인 분석

### 원인 1. `attachment_noise_penalty` 과도 적용 — 영향 ★★★★★

**위치**: `rag/selection/reranker.py:523-542`

```python
def _attachment_noise_penalty(...) -> float:
    section_type = _normalize_value(doc.metadata.get("section_type"))
    if section_type != "attachment":
        return 0.0
    ...
    if strong_term_match > 0.0:
        return -0.8      # ← 실제 정답 문서에도 이 페널티가 적용됨
    return -1.2
```

**문제**: `department_curriculum` 카테고리에서는 HWP/PDF 첨부파일이 교육과정의 **원본 소스**다.  
그런데 `section_type == "attachment"`라는 이유만으로 `-0.8`에서 `-1.2` 페널티가 붙어 정답 문서가 3위 밖으로 밀린다.

**영향 쿼리**: r018, r019, r020, r021, r022, r024, r025 (7건, Top-3 miss 13건의 53%)

---

### 원인 2. `department` 필터가 ranking_hint로 미전환 — 영향 ★★★★

**위치**: `rag/retrieval/search_strategy.py:16`

```python
HARD_FILTER_FIELDS: tuple[str, ...] = ()  # ← department가 hard filter 아님
```

쿼리 전처리 단계에서 `state.filters["department"] = ["간호학과"]`가 추출되지만,  
이것이 검색·랭킹 단계에서 **boost로 활용되지 않는다.**

학과명 개체가 ranking_hint로 전달되어 reranker의 `required_entity_match` 신호에 반영되어야 top-1 정확도가 올라간다.

---

### 원인 3. `hybrid` 전략에서 어휘 가중치 과잉 — 영향 ★★★

**위치**: `.env` `HYBRID_LEXICAL_WEIGHT=0.55`

"어디서 해?", "어디서 봐?" 같은 **방법·절차 쿼리**에서 BM25은 "어디서"라는 단어가 많이 포함된 안내성 메뉴 문서를 올린다.  
반면 vector 검색은 의미적 유사도로 실제 절차 문서를 올린다.

실측 결과: "어디서" 패턴 4건이 모두 `hybrid` 전략 → Top-3 miss

```
r014 국가장학금 신청 어디서 해?  → hybrid → Top-3 miss
r015 등록금 고지서 어디서 봐?    → hybrid → Top-3 miss
r016 성적 확인 어디서 해?        → hybrid → Top-3 miss
r017 학적 조회 어디서 해?        → hybrid → Top-3 miss
```

---

### 원인 4. `_DEPARTMENT_CURRICULUM_POSITIVE_TERMS` 학과명 미포함 — 영향 ★★★

**위치**: `rag/selection/reranker.py:188`

```python
_DEPARTMENT_CURRICULUM_POSITIVE_TERMS = {
    "교육과정", "이수표", "이수학점", "졸업기준", "졸업학점",
    "전공필수", "교양필수"   # ← 구체 학과명이 없음
}
```

"간호학과", "경찰행정학과", "시각디자인과" 등 구체 학과명이 positive_terms에 없어서  
학과명이 제목에 포함된 문서가 `verified_title_boost`를 받지 못한다.  
r023 게임공학과만 Top-1 hit인 이유: 게임공학과 커리큘럼 문서가 정적 페이지에도 존재해 section_type 페널티를 피함.

---

### 원인 5. `topk_selector`의 source_type 다양성 강제 — 영향 ★★

**위치**: `rag/selection/topk_selector.py:107-130`

```python
def _would_overfill_source_type(...) -> bool:
    ...
    same_type_count = sum(1 for selected_doc in selected if _source_type(selected_doc) == source_type)
    if same_type_count < 2:
        return False
    return any(...)  # 같은 source_type이 2개면 3번째를 막음
```

학과 커리큘럼처럼 **동일 source_type에서 여러 청크**가 필요한 경우에도  
다양성 강제로 인해 관련성 높은 3번째 청크가 탈락하고 다른 source_type의 덜 관련된 문서가 선택된다.

---

### 원인 6. `retrieved_count` 상한 (Top-K = 20) — 영향 ★

현재 `DEFAULT_TOP_K = 20`이고 Context Hit이 97.2%이므로 recall 자체는 충분하다.  
단, 20개 후보 내에서 reranking이 잘못되면 top-3 선택도 실패한다.  
Top-K를 30으로 늘리는 것은 recall을 소폭 개선하나, 근본 원인은 아니다.

---

## 3. 개선 방안 — 우선순위 순

### 방안 A. `attachment_noise_penalty` 카테고리별 면제 ★★★★★

**기대 효과**: Top-3 Hit +15~20%p (13건 중 7건 해결 가능)  
**구현 비용**: 낮음 (reranker.py 조건 추가)

```python
# reranker.py:523 _attachment_noise_penalty 수정
def _attachment_noise_penalty(
    doc: RetrievedDoc,
    strong_term_match: float,
    title_match: float,
    section_title_match: float,
    query_tokens: list[str],
    query_family: str = "",          # ← 추가
) -> float:
    section_type = _normalize_value(doc.metadata.get("section_type"))
    if section_type != "attachment":
        return 0.0
    if _is_explicit_notice_or_attachment_query(query_tokens):
        return 0.0

    # department_curriculum은 첨부파일이 원본 소스 → 페널티 면제
    if query_family in {"department_curriculum", "graduation"}:
        return 0.0

    direct_heading_match = title_match + section_title_match
    if direct_heading_match >= 0.9:
        return 0.0
    if direct_heading_match > 0.0 and strong_term_match >= 0.8:
        return -0.2
    if strong_term_match > 0.0:
        return -0.8
    return -1.2
```

`_score_doc`에서 `query_family`를 `_attachment_noise_penalty`로 전달하도록 추가.

---

### 방안 B. `department` 필터 → ranking_hint 전환 ★★★★

**기대 효과**: Top-1 Hit +8~12%p (학과명 쿼리 정확도 향상)  
**구현 비용**: 중간 (search_strategy.py + reranker.py 수정)

```python
# search_strategy.py _build_ranking_hints 수정
def _build_ranking_hints(..., query_features, ...):
    hints = {...}

    # department 필터를 ranking_hint로 전환
    dept = _first_value(soft_filters.get("department", []))
    if dept:
        hints["department_entity"] = dept   # ← reranker가 읽음

    return hints
```

```python
# reranker.py _score_doc 내 department entity boost 추가
dept_entity = str(ranking_hints.get("department_entity") or "")
department_entity_match = 0.0
if dept_entity and dept_entity.lower() in full_text:
    department_entity_match = 1.5   # 학과명 매칭 시 boost
elif dept_entity and dept_entity.lower() not in full_text:
    department_entity_match = -1.0  # 학과명 불일치 시 penalty
```

---

### 방안 C. 쿼리 패밀리별 hybrid/vector 전략 자동 선택 ★★★

**기대 효과**: Top-1 Hit +5~8%p (hybrid 하위 카테고리 개선)  
**구현 비용**: 낮음 (환경변수 또는 search_strategy.py 조건 추가)

현재 `RAG_VECTOR_ONLY_FAMILIES` 설정에 `academic_admin`, `grade`, `certificate`, `scholarship` 추가를 검토한다.

```python
# search_strategy.py 또는 pipeline 설정
# 추가 권장 vector-only families (실측 근거):
# - scholarship: hybrid Top-1 0% → vector-only 전환
# - grade, certificate, academic_admin: hybrid 4건 모두 Top-3 miss
# - tuition: hybrid 50% Top-1, vector로 전환 후 재측정 권장
RAG_VECTOR_ONLY_FAMILIES = [
    "department_curriculum",
    "building_location",
    "scholarship",        # 추가
    "grade",              # 추가
    "certificate",        # 추가
    "academic_admin",     # 추가 (단, 재측정 필요)
]
```

단, `academic_admin`은 36개 중 4건(50% Top-1)이라 전략 변경 전 A/B 테스트 필요.

---

### 방안 D. source_type 다양성 강제 완화 ★★

**기대 효과**: Top-3 Hit +3~5%p (동일 source의 다중 청크가 필요한 쿼리)  
**구현 비용**: 낮음

```python
# topk_selector.py:104
_DIVERSITY_EXEMPT_SOURCE_TYPES = {
    "static", "index", "menu",
    "department_curriculum",    # ← 추가: 학과 커리큘럼은 동일 소스 다중 청크 허용
    "academic_notice",          # ← 추가: 학사공지도 동일 문서 다중 청크 필요 가능
}
```

---

### 방안 E. `_DEPARTMENT_CURRICULUM_POSITIVE_TERMS` 동적 학과명 포함 ★★

**기대 효과**: Top-1 Hit +3~5%p  
**구현 비용**: 중간 (도메인 지식 업데이트 또는 동적 로딩)

```python
# reranker.py 또는 domain_knowledge.py
# 학과명 목록을 동적으로 로드하여 positive_terms에 추가
_DEPARTMENT_CURRICULUM_POSITIVE_TERMS = {
    "교육과정", "이수표", "이수학점", "졸업기준", "졸업학점",
    "전공필수", "교양필수",
    # 주요 학과명 추가 (최소 빈도 높은 것부터)
    "컴퓨터공학과", "간호학과", "경찰행정학과", "게임공학과",
    "인공지능학과", "경영학과", "시각디자인과",
}
```

장기적으로는 학과명 목록을 YAML 또는 DB에서 동적 로딩하는 구조가 유지보수에 유리하다.

---

### 방안 F. 크롤링 시드 보강 (welfare_facility) ★

**기대 효과**: Context Hit 100% 달성 (1건 해결)  
**구현 비용**: 매우 낮음

```python
# crawler/crawler/config/seeds.py 에 추가
# 정보공학관 학생식당 운영시간 URL 추가
"https://www.deu.ac.kr/.../cafeteria_schedule",
```

---

## 4. 개선 효과 시뮬레이션

개선 방안 A~C를 적용했을 때 예상 지표:

| 방안 | 조치 | Top-1 예상 | Top-3 예상 |
|---|---|---|---|
| 현재 | — | 52.8% | 63.9% |
| +A (attachment 페널티 면제) | reranker 조건 추가 | +10~15%p | +15~20%p |
| +B (department boost) | ranking_hint 전환 | +5~8%p | +5%p |
| +C (vector-only 확장) | 환경변수 수정 | +5%p | +5%p |
| **A+B+C 합산** | | **~73~80%** | **~85~92%** |

> ※ 시뮬레이션 수치는 실제 A/B 테스트로 검증 필요. 방안 간 중복 효과가 있을 수 있음.

---

## 5. 적용 우선순위 로드맵

```
Week 1 (빠른 효과, 리스크 낮음)
  ├── [F] 크롤링 시드 추가 (welfare_facility 1건 해결)
  └── [C] RAG_VECTOR_ONLY_FAMILIES 확장 (환경변수만)

Week 2 (핵심 개선)
  └── [A] attachment_noise_penalty 카테고리별 면제
           → evaluate_retrieval로 before/after 측정

Week 3 (랭킹 정확도)
  └── [B] department 필터 → ranking_hint 전환
           → department_curriculum Top-1 집중 측정

Week 4 (세부 튜닝)
  ├── [D] source_type 다양성 완화
  └── [E] POSITIVE_TERMS 학과명 추가
```

---

## 6. 측정 방법

각 방안 적용 후 아래 커맨드로 재측정:

```bash
# 전체 36개 평가
docker compose run --rm rag \
  python -m rag.evaluation.retrieval.evaluate_retrieval \
  --dataset datasets/real_queries.yaml --tag post_fix_A

# 카테고리 한정 (빠른 검증)
docker compose run --rm rag \
  python -m rag.evaluation.retrieval.evaluate_retrieval \
  --dataset datasets/real_queries.yaml \
  --limit 7   # department_curriculum 7개만
```

비교 지표: `top1_hit`, `top3_hit`, `selected_context_hit` 의 개선폭.  
회귀 지표: `irrelevant_document_included == 0` 유지, `answer_grounded_in_selected_context` 하락 없음.
