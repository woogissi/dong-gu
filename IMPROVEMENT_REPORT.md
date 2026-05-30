# 동의대학교 RAG 시스템 — 크롤러/파서/청킹/검색 파이프라인 개선 엔지니어링 리포트

**작성일**: 2026-05-28  
**분석 기준**: CRAWL_AUDIT_REPORT.md + 실제 코드 전수 검토  
**대상 파이프라인**: crawler (수집→파싱→청킹→적재) + rag (검색→재랭킹)

---

## 분석 범위

| 파일 | 역할 |
|---|---|
| `crawler/crawler/config/seeds.py` | 시드 URL 목록 및 source_type/page_kind 결정 함수 |
| `crawler/crawler/config/domains.py` | 허용 호스트 / 다운로드 확장자 목록 |
| `crawler/crawler/discovery/url_classifier.py` | URL 기반 page_kind / source_type 분류 |
| `crawler/crawler/extractors/static_page_extractor.py` | 정적 페이지 추출기 (본문, 링크, 첨부파일) |
| `crawler/crawler/extractors/board_detail_extractor.py` | 게시글 상세 추출기 |
| `crawler/crawler/extractors/board_list_extractor.py` | 게시글 목록 추출기 |
| `crawler/crawler/ingestion/chunker.py` | 문서 청킹 로직 |
| `crawler/crawler/ingestion/pgvector_loader.py` | PostgreSQL/pgvector 적재 |
| `crawler/crawler/parsers/file_text_router.py` | 첨부파일 파서 라우터 |
| `crawler/crawler/run/run_ingestion_pipeline.py` | 청킹 파이프라인 실행기 |
| `crawler/crawler/run/run_vector_ingestion.py` | 벡터 적재 파이프라인 실행기 |
| `crawler/crawler/state/crawler_state_store.py` | 크롤 상태 저장소 |
| `rag/retrieval/retriever.py` | 검색기 (lexical/vector/hybrid) |
| `rag/retrieval/search_strategy.py` | 검색 요청 빌더 |
| `rag/retrieval/quality.py` | 검색 품질 게이트 |

---

# [P0-2] 학사일정 source_type 오분류

## 1. 문제 현상

`seeds.py`에 `"deu_schedule_list"` 항목이 `source_type: "academic_calendar"`, URL `https://www.deu.ac.kr/www/scheduleList.do`로 정의되어 있다. 그러나 실제 수집 결과 파일은 `curated/documents/it_service/` 디렉토리에 저장되었고, `crawler_documents` 테이블에도 `source_type=it_service`로 기록되어 있다. `curated/academic_calendar/` 디렉토리 자체가 존재하지 않는다.

## 2. 현재 원인 분석

원인은 `seeds.py`의 `_doc_seed_source_type()` 함수(1078-1119행)와 `url_classifier.py`의 `infer_source_type()` 함수(59-103행) 중 하나(또는 둘 다)가 seeds.py에 명시된 `source_type` 값을 무시하고 URL 패턴 기반으로 재분류하기 때문이다.

`_doc_seed_source_type()` 함수(seeds.py:1115-1119)는 `host == "www.deu.ac.kr"`인 경우 `"institution"`을 반환하고, 그 외 어떠한 패턴도 `scheduleList.do`를 `academic_calendar`로 매핑하지 않는다. 이 함수는 `_DOC_SEED_URLS` 목록에서 `_make_doc_seed(url)` 호출 시 사용되지만, `SEED_URLS` 목록에서 직접 정의된 시드(923-921행의 `deu_schedule_list`)의 source_type은 시드 딕셔너리 값 `"academic_calendar"`를 그대로 사용해야 한다.

문제의 실제 발생 지점은 크롤 파이프라인(코드 미확인 영역)에서 이미 수집된 URL을 재처리하거나 상태를 업데이트할 때 `crawler_state_store.py`의 `upsert_document_state()` 또는 `upsert_discovered_url()`가 `source_type`을 `COALESCE(EXCLUDED.source_type, crawler_documents.source_type)` 패턴으로 처리(559-565행)하는 중에, 어딘가에서 `url_classifier.py`의 `infer_source_type()`이 호출되어 URL 기반으로 `it_service`(없으면 `webpage`)를 덮어쓴 것으로 추정된다. `infer_source_type()`에 `scheduleList`를 처리하는 브랜치가 없으므로 최종적으로 `"webpage"` 또는 `"it_service"` 중 하나로 귀결된다.

또한 `_doc_seed_source_type()`가 `www.deu.ac.kr`에 대해 `"institution"` fallback을 반환하는데, CMS URL 패턴인 `deu-cloud.do`, `deu-heyyoung.do`, `deu-wifi.do` 등은 seeds.py에서 `it_service`로 명시되어 있고, `infer_source_type()` 역시 이 패턴들에 대한 명시적 처리가 없다. `scheduleList.do`가 `it_service`로 분류된 것은 파이프라인 어딘가에서 `url_classifier.infer_source_type()` 결과가 seeds.py 값을 덮어쓴 결과다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/config/seeds.py:1078-1119` — `_doc_seed_source_type()`: `scheduleList` URL 처리 케이스 없음
- `crawler/crawler/discovery/url_classifier.py:59-103` — `infer_source_type()`: `scheduleList` 처리 케이스 없음
- `crawler/crawler/state/crawler_state_store.py:469-577` — `upsert_document_state()`: source_type COALESCE 처리 (EXCLUDED 우선 → 기존 보존 방향이나 순서가 역전될 수 있음)
- `crawler/crawler/state/crawler_state_store.py:408-467` — `upsert_discovered_url()`: source_type을 `COALESCE(crawler_documents.source_type, EXCLUDED.source_type)` 기존값 우선으로 처리

## 4. RAG 품질 영향

`rag/retrieval/retriever.py`의 `_retrieve_canonical_documents_from_database_v4()`(1257-1427행)는 `academic_schedule` family 질의 시 `source_type IN ('institution', 'academic_notice', 'academic', 'academic_calendar', 'academic_support', 'notice')`로 필터링한다. `it_service`는 이 목록에 없으므로 학사일정 문서가 canonical supplement 검색에서 완전히 제외된다.

"이번 학기 개강일이 언제야?", "수강신청 기간 알려줘", "학사일정 보여줘" 등의 질의에서 `scheduleList.do`에서 수집된 3,895자 분량의 핵심 학사일정 데이터가 검색 결과에 포함되지 않는다.

## 5. 개선 방향

**방안 A (데이터 수정, 즉시 적용 가능)**: 이미 적재된 문서의 source_type을 직접 수정한다.
```sql
UPDATE documents SET source_type = 'academic_calendar' 
WHERE source_url LIKE '%scheduleList%';
UPDATE crawler_documents SET source_type = 'academic_calendar'
WHERE url LIKE '%scheduleList%';
```
이후 해당 문서의 청크도 source_type 재적재가 필요하다.

**방안 B (코드 수정)**: `url_classifier.py`의 `infer_source_type()`에 `scheduleList` 케이스를 추가한다.
```python
if "schedulelist" in lower:
    return "academic_calendar"
```
이 수정을 `_doc_seed_source_type()` 함수에도 동일하게 적용한다.

**추천안**: 방안 A를 즉시 실행하고, 방안 B를 코드에 반영하여 재발 방지한다.

## 6. 구현 전략

Step 1: DB에서 직접 source_type 수정 (방안 A 실행)  
Step 2: `url_classifier.py:infer_source_type()`에 `scheduleList` → `academic_calendar` 케이스 추가  
Step 3: `seeds.py:_doc_seed_source_type()`에도 동일 케이스 추가  
Step 4: 수정된 문서 1개에 대해 `run_vector_ingestion.py --source-type academic_calendar` 실행으로 재색인  
Step 5: `retriever.py`의 canonical supplement 검색 결과 확인 (학사일정 질의 테스트)

## 7. 예상 부작용 및 trade-off

- 방안 A는 DB를 직접 수정하므로 다음 크롤 실행 시 파이프라인이 다시 덮어쓸 위험이 있다. 반드시 방안 B와 함께 적용해야 한다.
- `infer_source_type()`에 규칙 추가는 다른 URL 패턴과 충돌 가능성이 낮다 (`scheduleList`는 고유한 패턴).
- 영향 문서 수가 1개이므로 재색인 부담은 무시할 수준이다.

## 8. 우선순위

**즉시** — RAG의 핵심 기능인 학사일정 질의가 완전히 실패하는 P0 이슈다.

## 9. 테스트 전략

- "이번 학기 수강신청 기간 알려줘", "개강일이 언제야", "학사일정 보여줘" 3종 질의로 retriever 출력 확인
- 수정 전: `scheduleList.do` 문서가 결과 없음 또는 하위 랭킹
- 수정 후: canonical supplement에 `academic_calendar` source_type으로 상위 포함 확인

## 10. 최종 권장안

DB 직접 수정(방안 A) → `url_classifier.py` 코드 수정(방안 B) → 증분 재색인 순서로 적용한다.

---

# [P1-3] 이전글/다음글 제목 유입 (notice 64.6%)

## 1. 문제 현상

`curated/documents/notice/deu_notice_79942.json`의 `normalize` 필드 끝부분에 `"[3학년 필독] 26년 취업 준비, 3분이면 끝! 경품 추첨 [후원의 집] 하늘안과 1~2월 우대 혜택 안내"` 등 해당 문서와 무관한 이전글/다음글 제목이 포함되어 있다. notice 48개 중 31개(64.6%)에서 동일 패턴이 확인된다.

## 2. 현재 원인 분석

`board_detail_extractor.py`의 `find_content_node()`(193-220행)는 아래 selector 목록을 순서대로 시도한다:
```python
".board_view .cont", ".board_view .content", ".board-view .cont",
".board-view .content", ".view_cont", ".view-content",
"#contents", "#content", ".content", "main", ".fr-view"
```

동의대학교 게시판 상세 페이지에서 이전글/다음글 네비게이션 블록이 `#contents` 또는 `.content` 등 본문 컨테이너 **안에** 위치하는 경우, 위 selector로 본문을 찾으면 이전글/다음글 링크와 그 제목 텍스트가 `content_node`에 포함된다. 이후 `normalize_multiline_text(content_node.get_text("\n", strip=True))`(368행)를 호출하면 해당 텍스트가 그대로 `raw_text`에 포함된다.

`remove_meta_from_content()`(321-351행)는 이전글/다음글 제거를 시도하지만, 패턴이 `r"이전글\s*[^\n]*다음글"`, `r"이전글"`, `r"다음글"` 세 가지(338-342행)다. 이 패턴은 "이전글" 텍스트 자체는 제거하지만, 링크 텍스트(다음 게시글 제목)가 `이전글` / `다음글` 이후 별도 줄에 위치하는 구조에서는 제목 텍스트가 남는다. 예를 들어 HTML 구조가 `<span>이전글</span><a href="...">다른 게시글 제목</a>` 형태라면 정규식이 "이전글"만 제거하고 링크 제목은 남긴다.

`static_page_extractor.py`의 `STATIC_NOISE_SELECTORS`(198-256행)에는 `.prev-next`, `.board-navi`, `.view-nav` 등 이전글/다음글 전용 CSS 선택자가 없다. `board_detail_extractor.py`에는 noise selector 제거 로직 자체가 없다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/extractors/board_detail_extractor.py:193-220` — `find_content_node()`: 이전글/다음글을 포함한 광범위한 컨테이너 선택
- `crawler/crawler/extractors/board_detail_extractor.py:321-351` — `remove_meta_from_content()`: 이전글/다음글 제목 텍스트 제거 실패
- `crawler/crawler/extractors/board_detail_extractor.py:364-370` — `build_raw_document()`: `content_node.get_text()` 호출 전 DOM 레벨 noise 제거 없음
- `crawler/crawler/ingestion/chunker.py:13-26` — `STUB_LINE_PATTERNS`: "이전글", "다음글" 단독 줄은 제거하지만 제목 텍스트는 청킹 단계에서 통과

## 4. RAG 품질 영향

notice 48개 중 31개(64.6%) 청크에 타 게시글 제목이 포함된다. "장학금 신청 방법" 게시글의 청크에 "[후원의 집] 하늘안과 1~2월 우대 혜택" 등의 텍스트가 포함되면 벡터 검색 시 의미적 오염이 발생한다. 예를 들어 "안과 혜택"으로 질의 시 장학금 게시글이 검색되거나, 반대로 실제 관련 게시글이 밀려날 수 있다.

## 5. 개선 방향

**방안 A (DOM 레벨 제거, 추천)**: `board_detail_extractor.py`에 noise selector 제거 단계 추가
```python
BOARD_DETAIL_NOISE_SELECTORS = [
    ".prev-next", ".board-navi", ".view-nav", ".btn-area",
    "[class*='prev']", "[class*='next']", ".b_prev", ".b_next",
    "dl.board-util", ".board-btn-wrap",
]
```
`find_content_node()` 반환 후 해당 selector에 해당하는 태그를 `decompose()`한다.

**방안 B (텍스트 레벨 개선)**: `remove_meta_from_content()`의 이전글/다음글 패턴을 다음 줄까지 포함하도록 강화
```python
r"이전글[^\n]*\n[^\n]*",  # 이전글 라벨 + 다음 줄(제목) 제거
r"다음글[^\n]*\n[^\n]*",
```

**방안 C (청킹 레벨 필터)**: `chunker.py`의 `is_stub_chunk()`에 이전/다음글 제목 패턴 추가

방안 A가 근본 원인을 제거하므로 가장 효과적이다. 방안 B를 보완적으로 적용한다.

## 6. 구현 전략

Step 1: 동의대학교 게시판 상세 페이지 HTML을 수집하여 이전글/다음글 블록의 실제 CSS 클래스 확인 (5개 샘플)  
Step 2: `board_detail_extractor.py`에 `BOARD_DETAIL_NOISE_SELECTORS` 상수 추가 및 `build_raw_document()` 내 `content_node` 반환 후 제거 로직 삽입  
Step 3: `remove_meta_from_content()`의 패턴을 방안 B 수준으로 강화  
Step 4: notice source_type 대상 증분 재수집 + 재청킹 실행  
Step 5: `deu_notice_79942.json` 포함 5개 파일로 텍스트 오염 여부 확인

## 7. 예상 부작용 및 trade-off

- DOM selector가 실제 사이트와 맞지 않으면 이전글/다음글을 제거하지 못하거나, 잘못된 selector가 본문 일부를 제거할 수 있다. 여러 게시판 페이지로 검증 필요.
- 방안 B의 정규식이 너무 광범위하면 본문의 정상적인 "이전글" 언급 텍스트까지 제거할 수 있다. 패턴을 충분히 좁혀야 한다.
- 재수집이 필요하므로 네트워크 요청이 발생한다. 단, 오염된 31개 문서 한정이다.

## 8. 우선순위

**단기** — 64.6% 오염율은 notice 카테고리 전체의 검색 품질에 직접 영향을 미친다.

## 9. 테스트 전략

- `deu_notice_79942.json` 수정 전후 `normalize` 필드 끝부분 diff 비교
- notice 5개 무작위 샘플에서 이전글/다음글 제목 포함 여부 확인
- "장학금 신청" 등 질의 시 검색 결과 상위 문서의 source_type 및 content 확인

## 10. 최종 권장안

`board_detail_extractor.py`에 `BOARD_DETAIL_NOISE_SELECTORS` 추가 → `build_raw_document()` 내 적용 → `remove_meta_from_content()` 패턴 강화 → notice 대상 증분 재수집 순으로 적용한다.

---

# [P1-4] 완전 빈 문서 89개

## 1. 문제 현상

`normalize`, `structured_sections`, `table_text`, `attachment_text` 4개 필드가 모두 비어 있는 curated 문서가 89개 존재한다. 대표 사례:
- `curated/documents/department/static_083728d7df8bcee1.json` → URL `http://cinema.deu.ac.kr/` (title 깨짐: `ëìëíêµ`)
- `curated/documents/department/static_095795ee7972e599.json` → URL `https://swcc.deu.ac.kr/computer/sub05_01.do` (`quality_filter.raw_text_length_before=0`)
- `curated/documents/department/static_38563e74d717b080.json` → URL `https://www.deu.ac.kr/site/resource/www/vrtour/tour.html`

## 2. 현재 원인 분석

**원인 1 — JavaScript 동적 렌더링 페이지** (`sub05_01.do` 계열): `static_page_extractor.py`의 `fetch_result()`(351-376행)는 `requests.Session.get()`으로 HTML을 가져온다. JavaScript로 컨텐츠를 로드하는 페이지는 빈 HTML 골격만 반환하여 `quality_filter.raw_text_length_before=0`이 기록된다. `find_content_node()`(430-462행)의 fallback 로직은 빈 `div`를 반환하게 되고, `extract_static_page()`(1032-1123행)는 이를 정상으로 처리하여 `StaticPageRawDocument`를 생성한다.

**원인 2 — Charset 오류** (`cinema.deu.ac.kr/`): `_response_text()`(338-349행)는 `res.text`를 반환하는데, requests가 charset을 잘못 감지하면 한국어가 깨진 문자열로 파싱된다. 이 경우 `is_binary_like_text()` 검사를 통과하더라도 추출된 텍스트가 의미 없는 문자열이 되고, `clean_static_text()`(464-512행)의 길이 검사(496행 `len < 40`)에서 필터링될 수 있으나 모든 경우를 잡지는 못한다.

**원인 3 — VR 뷰어/이미지 전용 페이지** (`tour.html`): HTML 구조가 존재하지만 텍스트 컨텐츠가 없는 페이지로, 추출 자체는 성공하지만 텍스트가 없다.

**공통 문제**: `extract_static_page()`가 빈 결과를 반환해도 이를 실패로 기록하지 않고 `StaticPageRawDocument`를 생성한다. `run_ingestion_pipeline.py`의 `run_ingestion()`(130행)은 `normalize`, `attachment_text`, `image_text` 3개 필드만 검사(150-154행)하여 빈 문서를 `"skipped"` 처리하지만, `structured_sections`만 있는 경우 등 일부 엣지 케이스를 놓칠 수 있다. 또한 curated 파일 자체가 이미 저장된 후 청킹 단계에서야 스킵되므로 파이프라인 수준에서 "수집은 성공했으나 내용 없음"이 명시적으로 추적되지 않는다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/extractors/static_page_extractor.py:338-349` — `_response_text()`: charset 오류 탐지 없음
- `crawler/crawler/extractors/static_page_extractor.py:430-462` — `find_content_node()`: 빈 결과에 대한 명시적 처리 없음
- `crawler/crawler/extractors/static_page_extractor.py:1032-1123` — `extract_static_page()`: 빈 결과를 정상 문서로 반환
- `crawler/crawler/run/run_ingestion_pipeline.py:146-165` — `run_ingestion()`: 빈 문서 스킵 로직은 있으나 상태를 `"EMPTY_CONTENT"`로 명시하지 않음

## 4. RAG 품질 영향

89개 빈 문서는 청킹 단계에서 스킵되므로 RAG 검색에서 직접적 오염은 없다. 그러나 빈 문서가 정상 상태(CHUNKED)가 아닌 스킵 상태로 기록되지 않으면 재크롤 우선순위 산정이 불가능하다. department 56개 빈 문서는 학과 정보 질의("소프트웨어학과 교수님 정보") 에 대한 RAG 답변 품질을 낮춘다. JavaScript 렌더링 페이지의 실제 컨텐츠가 누락되기 때문이다.

## 5. 개선 방향

**방안 A (상태 추적 개선, 우선)**: `run_ingestion_pipeline.py`에서 빈 문서 스킵 시 상태를 `"EMPTY_CONTENT"`로 `crawler_state_store.upsert_document_state()`에 기록한다. 이를 통해 재처리 대상을 파악할 수 있다.

**방안 B (수집 단계 early exit)**: `extract_static_page()`에서 추출 후 컨텐츠가 비어있으면 예외를 발생시켜 파이프라인이 이를 `FAILED` 또는 `EMPTY_CONTENT`로 기록하게 한다.

**방안 C (JavaScript 렌더링 대응)**: Playwright/Selenium을 사용하여 JS 렌더링 페이지를 수집하는 별도 경로를 추가한다. 단, 인프라 비용이 크므로 고빈도 질의 대상 페이지(`sub05_01.do` 패턴)만 선택적으로 적용한다.

**방안 D (수집 제외 목록)**: VR 뷰어, 이미지 갤러리 등 텍스트 없는 페이지 URL 패턴을 `seeds.py`에서 `crawl_enabled: False`로 설정한다.

## 6. 구현 전략

Step 1: `run_ingestion_pipeline.py:154-165`의 스킵 처리 블록에 `record_chunk_state(doc, "EMPTY_CONTENT")` 추가  
Step 2: seeds.py에서 VR 투어, 이미지 갤러리 URL 패턴을 `crawl_enabled: False`로 설정  
Step 3: `sub05_01.do` 계열 JavaScript 페이지를 식별하여 수집 제외 또는 별도 처리 목록으로 분류  
Step 4: Charset 오류 탐지를 위해 `_response_text()`에서 한글 비율이 0인 경우 경고 로그 추가

## 7. 예상 부작용 및 trade-off

- `EMPTY_CONTENT` 상태 추가는 기존 상태 전이 로직과 충돌하지 않으나, 모니터링 쿼리를 업데이트해야 한다.
- Playwright 도입은 Docker 이미지 크기와 실행 시간을 크게 증가시킨다.
- 수집 제외 목록 확대는 실제로 컨텐츠가 있는 페이지를 잘못 제외할 위험이 있다.

## 8. 우선순위

**단기** — 상태 추적 개선(방안 A)은 코드 변경 범위가 작고 즉각적 관찰 가능성을 높인다. 방안 D는 명확한 패턴이 있는 케이스(VR, 이미지)에 즉시 적용한다.

## 9. 테스트 전략

- `static_083728d7df8bcee1.json`, `static_095795ee7972e599.json` 두 파일로 빈 문서 상태가 `"EMPTY_CONTENT"`로 기록되는지 확인
- `crawler_documents` 테이블에서 `EMPTY_CONTENT` 상태 건수 조회로 89개 정상 기록 확인

## 10. 최종 권장안

방안 A(상태 추적) + 방안 D(명확한 VR/이미지 패턴 수집 제외) 즉시 적용. 방안 C(Playwright)는 중기 로드맵으로 분류한다.

---

# [P1-5] 첨부파일 텍스트 추출 실패 331건

## 1. 문제 현상

DB `crawl_logs` 기준 `stage=file_parse`, `error_type=ValueError` 오류가 331건이다. source_type별로는 department 76건, scholarship 41건, job 20건, education 17건, foundation 14건 등이다. 오류 메시지 패턴은 `too_short,low_text_per_page`, `parser_empty_text`, `low_meaningful_char_ratio`이다.

## 2. 현재 원인 분석

`file_text_router.py`의 `extract_text()`(35-115행)는 확장자별로 파서를 라우팅한다. 각 파서가 실패하면 `attachment_text=None`을 반환하거나 예외를 발생시킨다.

**스캔 PDF**: `.pdf` 분기(42-51행)에서 `PDFParser.extract_text()`를 호출한다. 이미지로 스캔된 PDF는 `pdfminer` 계열 파서로 텍스트를 추출할 수 없어 `too_short`, `low_text_per_page` 품질 오류가 발생한다. `FileTextRouter`에는 스캔 PDF 감지 후 OCR 폴백 경로가 없다.

**HWP 파서 한계**: `.hwp` 분기(63-71행)에서 `HWPParser.extract_text()`를 호출한다. HWP 형식의 복잡한 변형(컴파운드 도큐먼트, 구버전 형식)에서 `parser_empty_text`가 발생한다. HWP 파서가 내부적으로 어떤 라이브러리를 쓰는지 코드 확인이 필요하나, 결과적으로 파싱 실패 시 `None` 텍스트가 반환된다.

`pgvector_loader.py`의 `upsert_assets()`(452-709행)에서 `attachment_text`가 없거나 빈 문자열인 경우 `parse_status="parser_empty_text"`와 `needs_reprocess=True`(550-554행)를 기록한다. 그러나 이 상태가 자동 재처리로 이어지지는 않는다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/parsers/file_text_router.py:42-51` — `.pdf` 처리: 스캔 PDF OCR 폴백 없음
- `crawler/crawler/parsers/file_text_router.py:63-71` — `.hwp` 처리: 실패 시 대안 없음
- `crawler/crawler/ingestion/pgvector_loader.py:547-557` — 빈 텍스트 처리: `needs_reprocess=True` 기록하지만 자동 재시도 없음
- `crawler/crawler/ingestion/pgvector_loader.py:672-706` — 빈 텍스트 asset 처리: crawl_log에 기록

## 4. RAG 품질 영향

scholarship 41건은 장학금 공고 첨부파일(신청 자격, 금액, 기간 등 핵심 정보)이 RAG에 누락된다. "국가장학금 신청 자격이 뭐야", "장학금 금액 얼마야" 등의 질의에서 게시글 본문만으로 불완전한 답변이 생성된다. job 20건도 취업 공고 상세 내용 누락으로 "어떤 자격요건이 필요해" 등의 질의 실패를 유발한다.

## 5. 개선 방향

**방안 A (스캔 PDF OCR 폴백)**: `file_text_router.py`에 스캔 PDF 감지 로직 추가. PDF 파서가 `too_short` 또는 `low_text_per_page`를 반환하면 `pytesseract` 또는 AWS Textract/Azure Computer Vision으로 OCR 재시도한다.
```python
if ext == ".pdf":
    result = self.pdf_parser.extract_text(file_path)
    if result.get("quality_status") in {"too_short", "low_text_per_page"}:
        result = self.ocr_parser.extract_text(file_path)  # fallback
```

**방안 B (retry_queue 활용)**: `needs_reprocess=True` 상태인 파일을 `crawler_retry_queue`에 등록하여 주기적 재처리를 자동화한다. 이미 `crawler_state_store.py`에 `enqueue_retry()` 메서드(579-657행)가 존재하므로 파서 실패 시 호출하면 된다.

**방안 C (HWP → HWPX 변환)**: LibreOffice를 활용하여 HWP를 DOCX로 변환 후 `ooxml_parser`로 재시도한다. `_LIBREOFFICE_CONVERT_MAP`에 `.hwp` → `docx` 추가.

## 6. 구현 전략

Step 1: `file_text_router.py`에 스캔 PDF 감지 기준 정의 (`text_per_page < 50` 또는 `korean_ratio < 0.1`)  
Step 2: OCR 의존성 추가 (`pytesseract` + `pdf2image`) — Dockerfile 수정 필요  
Step 3: `file_text_router.py:42-51`에 OCR 폴백 분기 추가  
Step 4: 파서 실패(빈 텍스트 반환) 시 `crawler_state_store.enqueue_retry()` 호출 추가  
Step 5: HWP 파서 실패 시 `_convert_with_libreoffice()` 폴백 시도 (`_LIBREOFFICE_CONVERT_MAP`에 `.hwp` 추가)  
Step 6: `run_retry_failed_documents` 커맨드로 `needs_reprocess=True` 파일 일괄 재처리

## 7. 예상 부작용 및 trade-off

- OCR은 속도가 느리고(문서당 수 초~수십 초) 인프라 비용이 증가한다. 스캔 PDF는 소수이므로 병렬 처리 큐로 분리하는 것이 바람직하다.
- LibreOffice 변환은 이미 `.xls/.doc/.ppt`에 적용되어 있으므로 HWP 추가 시 기존 패턴을 따른다. 단, LibreOffice의 HWP 지원은 불완전할 수 있다.
- OCR 추가 시 Docker 이미지 크기가 크게 증가한다 (tesseract + 언어팩).

## 8. 우선순위

**단기** — scholarship, job 등 핵심 정보 카테고리에 직접 영향을 미친다.

## 9. 테스트 전략

- 알려진 스캔 PDF 파일 3종으로 OCR 폴백 후 텍스트 추출 성공 여부 확인
- HWP 실패 파일 샘플 5종에 LibreOffice 변환 폴백 적용 결과 확인
- "장학금 신청 자격" 질의 시 첨부파일 청크가 검색 결과에 포함되는지 확인

## 10. 최종 권장안

단기: 방안 B(retry_queue 자동화) 적용 → 기존 `needs_reprocess=True` 파일 재시도  
중기: 방안 A(스캔 PDF OCR) + 방안 C(HWP LibreOffice 폴백) 순으로 적용한다.

---

# [P2-6] CMS 파일 URL을 static_page로 오분류 → FAILED 14건

## 1. 문제 현상

`https://www.deu.ac.kr/cms/etcResourceDown.do?site=...` 및 `etcResourceOpen.do?site=...` 형태의 URL들이 `page_kind=static_page`로 분류되어 수집 시도 중 `non-html static response: content_type=application/pdf` 오류로 FAILED 상태가 된다. safety 7건, it_service 4건, institution 1건, disability_support 1건 등 총 14건이다.

## 2. 현재 원인 분석

`static_page_extractor.py`의 `extract_internal_links()`(900-928행)와 `extract_navigation_links()`(959-986행)은 페이지 내 링크를 수집하여 발견된 URL 목록을 반환한다. 이때 `etcResourceDown.do`, `etcResourceOpen.do` URL은 경로 확장자가 `.do`이므로 `extract_internal_links()` 내 `.do` 파일 제외 로직(920-921행 `_BINARY_EXTS`)에 포함되지 않는다. `mode=download` 파라미터가 없고 확장자가 `.do`이므로 첨부파일로 식별되지 않아 일반 링크로 반환된다.

`seeds.py`의 `_doc_seed_page_kind()`(1122-1162행)도 이 URL을 처리하지 않는다: `"download" in path`(1149행) 조건은 `etcResourceDown`의 경로에는 해당하지 않고, `query.get("mode", [""])[0] == "download"` 조건도 이 URL의 쿼리파라미터에는 없다. 결과적으로 `"static_page"`(1162행 default)를 반환한다.

이후 `static_page_extractor.py`의 `_response_text()`(338-344행)에서 `content_type=application/pdf`를 감지하여 `ValueError`를 발생시켜 FAILED가 된다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/extractors/static_page_extractor.py:900-928` — `extract_internal_links()`: `etcResourceDown/Open.do` 패턴 필터링 없음
- `crawler/crawler/config/seeds.py:1122-1162` — `_doc_seed_page_kind()`: CMS 다운로드 URL 패턴 누락
- `crawler/crawler/extractors/static_page_extractor.py:870-898` — `extract_attachments()`: `etcResourceDown.do`를 첨부파일로 인식하지 않음 (mode=download가 없으므로)
- `crawler/crawler/discovery/url_classifier.py:24-57` — `classify()`: `etcResourceDown` 패턴 처리 없음

## 4. RAG 품질 영향

safety, it_service 등 관련 PDF 파일 내용이 누락된다. FAILED 상태이므로 직접적 오염은 없으나, 안전 매뉴얼, IT 서비스 가이드 등 정보가 RAG에 미수록된다.

## 5. 개선 방향

**방안 A (URL 분류기 수정, 추천)**: `url_classifier.py`의 `classify()` 및 `seeds.py`의 `_doc_seed_page_kind()`에 CMS 다운로드 패턴 추가:
```python
if "etcResourceDown" in path or "etcResourceOpen" in path:
    return "attachment"
```

**방안 B (내부 링크 필터 추가)**: `static_page_extractor.py`의 `extract_internal_links()`에서 해당 패턴 URL을 제외:
```python
if "etcresourcedown" in parsed.path.lower() or "etcresourceopen" in parsed.path.lower():
    continue
```

방안 A와 방안 B를 동시에 적용하는 것이 완전한 해결책이다.

## 6. 구현 전략

Step 1: `url_classifier.py`의 `classify()` 메서드 상단에 CMS 다운로드 패턴 조건 추가  
Step 2: `seeds.py`의 `_doc_seed_page_kind()` 함수에 동일 패턴 추가  
Step 3: `static_page_extractor.py`의 `extract_internal_links()`에 해당 URL 필터 추가  
Step 4: FAILED 상태의 14건 URL을 `crawler_retry_queue`에서 제거 또는 `page_kind=attachment`로 상태 수정  
Step 5: 이후 크롤 실행 시 해당 URL이 FAILED가 되지 않는지 확인

## 7. 예상 부작용 및 trade-off

- `etcResourceDown/Open.do` URL을 `attachment`로 분류하면 해당 URL의 PDF/파일이 첨부파일 다운로드 및 파싱 파이프라인으로 전달된다. 파일 형식(PDF 등)에 따라 파서가 처리할 수 있어야 한다.
- 동의대 CMS가 향후 URL 패턴을 변경하면 이 규칙이 무효화될 수 있다.

## 8. 우선순위

**단기** — 코드 변경이 단순하고 FAILED 건수를 즉시 해소할 수 있다.

## 9. 테스트 전략

- `etcResourceDown.do` URL 2종에 대해 `url_classifier.classify()` 반환값이 `"attachment"`인지 확인
- `_doc_seed_page_kind()` 반환값 동일 확인
- 크롤 재실행 후 해당 URL의 `crawler_documents.status`가 FAILED가 아닌지 확인

## 10. 최종 권장안

`url_classifier.py` + `seeds.py` + `static_page_extractor.py` 3개 파일에 동일한 CMS URL 필터 패턴을 추가한다. 변경 후 FAILED 14건 URL의 재처리는 별도 배치로 수행한다.

---

# [P2-7] teacher/sub02_05.do 404 오류 30건

## 1. 문제 현상

`https://deuhome.deu.ac.kr/teacher/sub02_05.do`에 대한 게시판 목록 요청이 모두 404를 반환하여 `stage=board_list`, `error_type=HTTPError` 오류가 30건 발생한다. URL 패턴은 `https://deuhome.deu.ac.kr/teacher/sub02_05.do?article.offset=N&articleLimit=10&mode=list`이다.

## 2. 현재 원인 분석

`seeds.py`의 `_DOC_SEED_URLS` 목록(1175-1566행)에 `https://deuhome.deu.ac.kr/teacher/sub02_05.do`가 포함되어 있다(1187행). `_doc_seed_page_kind()` 함수(1122-1162행)는 `re.search(r"/sub02(_\d+)?\.do$", path)`(1160행) 패턴에 매칭되어 이 URL을 `"board_list"`로 분류한다.

`board_list_extractor.py`의 `extract_list()`(117-131행)는 `normalize_list_request()`로 페이지네이션 파라미터를 추가하여 HTTP GET을 수행한다. 서버가 `sub02_05.do`에 대해 404를 반환하므로 `res.raise_for_status()`(30행)에서 `HTTPError`가 발생한다. 이 오류가 30번 반복된 것은 페이지네이션 요청이 30회 시도되었기 때문이다.

`seeds.py`에 등록된 URL이 실제로 존재하지 않는 페이지를 가리키고 있다. 해당 URL(`teacher/sub02_05.do`)은 동의대 사이트 구조 변경으로 제거되었을 가능성이 높다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/config/seeds.py:1187` — `_DOC_SEED_URLS`: 유효하지 않은 URL 포함
- `crawler/crawler/config/seeds.py:1159-1161` — `_doc_seed_page_kind()`: `/sub02(_\d+)?\.do$` 패턴으로 board_list 분류
- `crawler/crawler/extractors/board_list_extractor.py:28-31` — `fetch()`: HTTPError 발생

## 4. RAG 품질 영향

teacher source_type의 해당 게시판 게시글 수집 실패. 교원 관련 특정 정보가 누락될 수 있으나, `sub02_05.do` 외의 teacher URL들은 정상 수집된다. 직접적 RAG 품질 저하보다는 불필요한 오류 발생과 리소스 낭비가 주된 영향이다.

## 5. 개선 방향

**방안 A (즉시)**: `seeds.py`의 `_DOC_SEED_URLS`에서 `https://deuhome.deu.ac.kr/teacher/sub02_05.do` 제거.

**방안 B (근본 해결)**: seed URL 유효성 자동 검사 스크립트를 CI 또는 정기 작업으로 추가하여 404 반환 URL을 조기에 탐지한다.

## 6. 구현 전략

Step 1: `seeds.py:1187`에서 해당 URL 라인 삭제  
Step 2: `crawler_documents` 테이블에서 해당 URL의 FAILED 레코드 삭제 또는 `crawl_enabled=False` 처리  
Step 3: 선택적으로 `deuhome.deu.ac.kr/teacher/` 하위 URL 전체에 대해 HTTP HEAD 요청으로 유효성 확인 스크립트 작성

## 7. 예상 부작용 및 trade-off

- URL 제거 시 해당 게시판에 실제 콘텐츠가 있었다면 누락된다. 그러나 404가 지속적으로 반환된다는 사실 자체가 URL이 비활성임을 증명한다.
- 유효성 검사 스크립트 추가는 크롤 실행 시간을 늘린다.

## 8. 우선순위

**즉시** — 단순 코드 1줄 삭제로 30건 오류를 즉시 해소한다.

## 9. 테스트 전략

- URL 삭제 후 크롤 실행 시 해당 URL 관련 오류가 더 이상 발생하지 않는지 확인
- `crawler_documents` 테이블에서 해당 URL 레코드가 없는지 확인

## 10. 최종 권장안

`seeds.py:1187`에서 `teacher/sub02_05.do` URL 즉시 삭제. 추가로 `teacher/sub02_*.do` URL 전체에 대해 HTTP 상태 코드를 일괄 확인한다.

---

# [P2-8] seeds.py 대비 7개 source_type curated 파일 완전 누락

## 1. 문제 현상

seeds.py에 정의된 source_type 중 `academic`, `facility`, `newsletter`, `academic_calendar`, `fund`, `language`, `culture_innovation` 7개에 해당하는 curated 파일이 `curated/documents/` 하위에 존재하지 않는다.

## 2. 현재 원인 분석

source_type별 누락 원인을 코드 레벨에서 추적한다.

**academic_calendar**: 문제 P0-2에서 분석한 대로 `it_service`로 오분류. `curated/academic_calendar/` 디렉토리 미생성.

**academic**: seeds.py에 `deu_college`(185-188행), `deu_graduate_school`(190-195행), `deu_rule`, `deu_curriculum`, `deu_explanation`, `deu_microdegree`, `deu_consortium`, `deu_college_engineering`, `deu_college_software`, `deu_college_healthcare`가 `source_type: "academic"`으로 정의되어 있다. 이 URL들이 실제로 수집되지 않았거나, `_doc_seed_source_type()`이 덮어썼을 가능성이 있다. `www.deu.ac.kr` 호스트 URL들은 `_doc_seed_source_type()`에서 `"institution"` fallback을 반환한다(1115-1116행). 단, 이 URL들은 `SEED_URLS`에 직접 정의되었으므로 seeds.py 값을 쓰는 게 맞다. 파이프라인 어딘가에서 재분류가 일어난 것으로 추정된다.

**facility**: `deu_facility_info`(515-518행)가 `source_type: "facility"`로 정의. URL은 `https://www.deu.ac.kr/www/deu-facility-info.do`. 수집 여부를 확인해야 하나 curated 파일이 없다면 수집 자체가 안 된 것.

**newsletter**: `deu_newsletter_list`(651-656행)가 `source_type: "newsletter"`, `page_kind: "board_list"`로 정의. 게시판 목록 수집 자체가 안 됐거나 board_list 수집 파이프라인에서 처리 안 됨.

**fund**: `deu_fund_home`(598-602행)이 `source_type: "fund"`, URL `https://deufund.deu.ac.kr/exchange/main.do`. `_DOC_SEED_URLS`에도 여러 deufund URL이 있으나, `_doc_seed_source_type()`에서 `"deufund" in host` 분기(1112행)가 `"fund"`를 반환한다. 그럼에도 curated 파일이 없다면 수집 자체가 안 됐거나 domain 접근 실패.

**language**: `deu_language_home`(574-578행)이 `source_type: "language"`, URL `https://deuhome.deu.ac.kr/language/index.do`. `_DOC_SEED_URLS`에 여러 language URL이 있다. `_doc_seed_source_type()`에서 `"language" in path` 케이스가 없으므로 `"department"` 또는 `"institution"` fallback으로 귀결될 수 있다.

**culture_innovation**: `deu_culture_innovation_home`(721-726행)이 `source_type: "culture_innovation"`, URL `https://vsc.deu.ac.kr/culture/index.do`. `vsc.deu.ac.kr` 호스트가 `ALLOWED_HOSTS`(domains.py:16-33행)에 없으므로 링크 수집에서 제외될 수 있다. 단, seed URL이므로 직접 수집은 가능하다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/config/seeds.py:1078-1119` — `_doc_seed_source_type()`: 다수 source_type 처리 케이스 누락
- `crawler/crawler/config/domains.py:16-33` — `ALLOWED_HOSTS`: `vsc.deu.ac.kr` 등 일부 호스트 누락
- `crawler/crawler/state/crawler_state_store.py:408-467` — `upsert_discovered_url()`: `source_type` COALESCE 로직이 파이프라인에서 원래 source_type을 덮어쓸 수 있음

## 4. RAG 품질 영향

academic: 학부/대학원 정보 누락으로 "XX대학 커리큘럼이 뭐야" 등 학사 구조 질의 실패.  
facility: 시설 안내 정보 누락으로 "어디서 자전거를 빌릴 수 있어" 등 시설 질의 실패.  
fund: 발전기금 관련 정보 누락 (학생 생활 영향 낮음).

## 5. 개선 방향

**방안 A**: `crawler_documents` 테이블에서 각 source_type에 해당하는 URL의 실제 status 확인 후 미수집 URL에 대해 크롤 실행.

**방안 B**: `_doc_seed_source_type()` 함수에 누락된 패턴 추가 (language, culture_innovation, facility 등).

**방안 C**: `ALLOWED_HOSTS`에 `vsc.deu.ac.kr` 등 누락된 호스트 추가.

## 6. 구현 전략

Step 1: DB에서 각 source_type URL의 `status`를 조회하여 DISCOVERED/미기록인 URL 목록 추출  
Step 2: 미수집 URL에 대해 `docker compose run --rm crawler python -m crawler.run.run_crawl_to_rag --source-type <type>` 실행  
Step 3: `_doc_seed_source_type()`에 `language`, `culture_innovation`, `facility` 패턴 추가  
Step 4: `domains.py`의 `ALLOWED_HOSTS`에 `vsc.deu.ac.kr` 추가  
Step 5: 재크롤 후 curated 디렉토리 생성 확인

## 7. 예상 부작용 및 trade-off

- 미수집 URL을 크롤하면 새로운 빈 문서 또는 접근 불가 URL이 추가될 수 있다.
- `ALLOWED_HOSTS` 확장은 외부 링크 수집 범위도 넓어질 수 있으므로 신중히 검토한다.

## 8. 우선순위

**단기** — academic과 facility는 학생 질의 핵심 영역. fund, newsletter는 중간 우선순위.

## 9. 테스트 전략

- 각 source_type 디렉토리 생성 확인
- "XX대학 커리큘럼 뭐야" 등 대표 질의 테스트

## 10. 최종 권장안

DB 상태 확인 후 미수집 URL 식별 → source_type별 크롤 실행 → `_doc_seed_source_type()` 보완 순으로 진행한다.

---

# [P3-9] 핵심 source_type 수집량 부족

## 1. 문제 현상

학생 질의 핵심 대상 source_type의 수집 파일 수가 극히 적다:
- cafeteria: 1개
- shuttle: 2개
- library: 9개
- notice: 48개
- it_service: 3개

## 2. 현재 원인 분석

**cafeteria / shuttle**: seeds.py에 각각 `deu_dining_hall`(498-501행), `deu_shuttle_bus`(491-494행), `deu_sbus`(965-971행) 시드가 있다. 모두 `page_kind: "static_page"`다. 정적 페이지는 단일 URL 1개를 수집하므로 cafeteria 1개, shuttle 2개가 이론적 최대치다. 메뉴 데이터가 동적으로 로드된다면 JS 렌더링 없이는 추출 불가.

**notice**: `deu_notice_list`(247-252행)가 `board_list`로 정의. `run_crawl_to_rag.py`(파일 미확인)의 `--pages` 인수나 `--since-date` 인수로 수집 범위가 제한된다. 기본 페이지 크기가 10이고 몇 페이지만 수집했다면 48개 수준이 된다. 실제 동의대 공지사항 게시판은 수천 건이 존재한다.

**library**: seeds.py에 `deu_library_home`, `deu_library_history`, `deu_library_rule`, `deu_library_notice_list`, `deu_library_faq_list`, `deu_library_*` 여러 시드가 있으나(467-880행 범위), `lib.deu.ac.kr` 도메인의 게시판 구조(`_list.mir` 패턴)를 `board_list_extractor.py`가 올바르게 처리하지 못했을 가능성이 있다. `.mir` URL에 대해 `normalize_list_request()`의 파라미터 형식이 `lib.deu.ac.kr` 게시판과 맞지 않을 수 있다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/config/seeds.py:498-501, 491-494` — cafeteria/shuttle 시드: static_page 1개씩만 정의
- 크롤 실행 커맨드의 `--pages`, `--since-date` 인수: notice 수집 범위 제한
- `crawler/crawler/extractors/board_list_extractor.py:44-60` — `normalize_list_request()`: `.mir` URL 게시판과의 파라미터 호환성 미확인

## 4. RAG 품질 영향

"오늘 학식 메뉴가 뭐야"는 cafeteria 1개 정적 페이지만으로는 날짜별 메뉴 정보를 답변하기 불가능하다. "셔틀버스 첫차가 몇 시야"는 shuttle 2개 문서가 노선/시간표 정보를 포함하는지 여부에 따라 답변 가능성이 결정된다. notice 48개는 수천 건 게시글 중 극히 일부로, 최근 공지 검색에서 실패 빈도가 높다.

## 5. 개선 방향

**cafeteria**: 동의대학교 학생식당 메뉴가 별도 시스템(앱, API)에서 제공된다면 해당 API 연동을 별도로 구현해야 한다. 그렇지 않다면 정적 페이지를 주기적으로 재수집하는 크론 작업을 추가한다.

**notice**: 크롤 실행 시 `--pages` 인수를 늘리거나 `--since-date`를 과거로 설정하여 더 많은 게시글을 수집한다. 초기 전체 수집 후 증분 업데이트로 전환하는 전략이 필요하다.

**library**: `lib.deu.ac.kr` 게시판의 실제 응답을 분석하여 `board_list_extractor.py`의 `parse_rows()`가 올바르게 동작하는지 확인한다.

## 6. 구현 전략

Step 1: notice 게시판에 대해 `--pages 50 --since-date 2024-01-01`로 크롤 실행하여 수집량 증가 확인  
Step 2: library 게시판 응답 HTML 분석 후 `board_list_extractor.parse_rows()`와 호환 여부 확인  
Step 3: cafeteria 메뉴 데이터 소스 확인 — 정적 페이지 업데이트 주기 확인 후 주기적 재수집 크론 추가  
Step 4: shuttle 정보는 2개 페이지의 텍스트 내용이 시간표를 포함하는지 확인

## 7. 예상 부작용 및 trade-off

- 수집 범위 확대는 크롤 실행 시간과 서버 부하를 증가시킨다. 동의대 서버 rate limit 준수 필요.
- 과거 게시글 대량 수집 시 관련성 낮은 문서도 함께 적재될 수 있다.

## 8. 우선순위

**중기** — 수집량 증가는 크롤 실행 파라미터 조정으로 가능하지만, cafeteria 메뉴 등 일부는 근본적 구조 문제다.

## 9. 테스트 전략

- `--pages 50` 적용 후 notice 수집 파일 수 확인
- library 게시판 URL 직접 접근하여 `board_list_extractor.extract_list()` 반환값 확인

## 10. 최종 권장안

notice: `--pages` 확대 → 즉시 실행. library: 게시판 파서 호환성 확인 후 수집 재실행. cafeteria: 메뉴 데이터 소스 확인 후 전략 결정.

---

# [P3-10] admission 중복 URL 47건 dedup 차단

## 1. 문제 현상

admission source_type에서 `embedding_quality_gate` 단계에 `duplicate_blocked` 47건이 발생한다. `http://ipsi.deu.ac.kr/submenu.do?menuord=6`과 `https://ipsi.deu.ac.kr/submenu.do?menuord=6`이 동일 내용으로 중복 수집되었고, 빈 쿼리파라미터(`?` 트레일링) 등의 변형도 중복으로 처리된다.

## 2. 현재 원인 분석

`static_page_extractor.py`의 `canonicalize_url()`(320-322행)은 URL에서 fragment(`#...`)만 제거한다:
```python
def canonicalize_url(self, url: str) -> str:
    url, _ = urldefrag(url)
    return url
```

http와 https를 동일하게 처리하지 않으므로 `http://ipsi.deu.ac.kr/...`과 `https://ipsi.deu.ac.kr/...`이 서로 다른 URL로 처리된다. 또한 `?menuord=6&`(빈 파라미터 트레일링)과 `?menuord=6`도 구분된다.

`crawler_state_store.py`의 `canonicalize_url()`(153-155행)도 동일하게 fragment만 제거한다.

seeds.py의 `deu_ipsi_menuord_6`(403-407행)과 `_DOC_SEED_URLS` 내 `ipsi.deu.ac.kr/submenu.do?menuord=6&`(트레일링 앰퍼샌드 포함 형태) 등이 동시에 시드로 등록되어 있을 가능성이 있다. 또한 동일 페이지가 `menuord` 파라미터와 `menuUrl` 파라미터 두 가지 방식으로 접근 가능한 경우 내용이 같더라도 다른 URL로 수집된다.

`pgvector_loader.py`의 `_filter_source_duplicate_chunks()`(766-816행)는 `CRAWLER_BLOCK_SOURCE_DUPLICATE_CHUNKS=1` 환경변수가 설정된 경우 cross-source dedup을 수행하여 동일 content_hash를 가진 청크를 차단한다. 이 기능이 활성화된 상태에서 중복 수집된 admission 문서의 청크가 `duplicate_blocked` 처리된다.

## 3. 코드 레벨 영향 범위

- `crawler/crawler/extractors/static_page_extractor.py:320-322` — `canonicalize_url()`: http/https 미정규화, 빈 파라미터 미제거
- `crawler/crawler/state/crawler_state_store.py:153-155` — `canonicalize_url()`: 동일 문제
- `crawler/crawler/config/seeds.py:303-407` — `SEED_URLS` 및 `_DOC_SEED_URLS`: admission 관련 중복 URL 등재 가능성
- `crawler/crawler/ingestion/pgvector_loader.py:766-816` — `_filter_source_duplicate_chunks()`: cross-source dedup으로 차단

## 4. RAG 품질 영향

47건 청크 차단으로 인한 실질적 데이터 손실은 없다 (동일 내용이 하나는 저장됨). 그러나 불필요한 크롤 리소스가 낭비되고, `duplicate_blocked` 로그가 쌓여 오류 파악을 어렵게 한다.

## 5. 개선 방향

**방안 A (URL 정규화 강화, 추천)**:
```python
def canonicalize_url(self, url: str) -> str:
    url, _ = urldefrag(url.strip())
    # http → https 정규화
    if url.startswith("http://"):
        url = "https://" + url[7:]
    # 빈 쿼리 파라미터 제거
    parsed = urlparse(url)
    if parsed.query:
        params = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if v]
        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(params), ""))
    elif parsed.query == "":
        url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return url
```
이 수정을 `static_page_extractor.py`와 `crawler_state_store.py` 두 곳에 적용한다.

**방안 B (seeds.py 정리)**: seeds.py에서 http/https 중복 URL, 빈 파라미터 트레일링 URL을 제거한다.

## 6. 구현 전략

Step 1: `static_page_extractor.py:320-322`의 `canonicalize_url()` 강화 (http→https, 빈 파라미터 제거)  
Step 2: `crawler_state_store.py:153-155`의 `canonicalize_url()` 동일하게 강화  
Step 3: seeds.py에서 http로 시작하는 admission URL 확인 후 https로 통일  
Step 4: 기존 `crawler_documents` 테이블에서 중복 URL 레코드 정리  
Step 5: 재크롤 시 중복 수집 여부 확인

## 7. 예상 부작용 및 trade-off

- http→https 강제 전환은 실제로 http만 지원하는 서버(예: 일부 구형 도메인)에서 연결 실패를 유발할 수 있다. 해당 호스트 목록을 예외 처리해야 한다.
- 빈 파라미터 제거로 인해 일부 서버가 파라미터 없는 URL에서 다른 페이지를 반환하는 경우가 있을 수 있다.
- `canonical_url UNIQUE` 제약 조건(crawler_state_store.py:20행)이 있으므로 정규화 강화 후 기존 레코드와 충돌할 수 있다. 마이그레이션이 필요하다.

## 8. 우선순위

**중기** — 데이터 손실이 없고 크롤 자원 낭비만의 문제이므로 즉시성은 낮다.

## 9. 테스트 전략

- `http://ipsi.deu.ac.kr/submenu.do?menuord=6`과 `https://ipsi.deu.ac.kr/submenu.do?menuord=6`에 대해 `canonicalize_url()` 반환값이 동일한지 확인
- `?menuord=6&`와 `?menuord=6`이 동일하게 정규화되는지 확인
- 재크롤 후 `duplicate_blocked` 카운트 감소 확인

## 10. 최종 권장안

`canonicalize_url()` 강화(방안 A)를 `static_page_extractor.py`와 `crawler_state_store.py` 두 곳에 동시 적용한다. seeds.py http URL 정리(방안 B)는 병행 적용한다.

---

## 발견된 추가 문제

### [보조-A] board_detail_extractor.py의 데드코드 — dedupe_attachments_by_url 이후 unreachable 코드

`board_detail_extractor.py:309-319행`에 `dedupe_attachments_by_url(results)` 반환 후 `return` 문(310행)이 있고, 그 아래에 `unique = []` 로 시작하는 수동 dedup 코드(311-319행)가 존재한다. 이 코드는 절대 실행되지 않는 데드코드다. 혼동을 방지하기 위해 311-319행을 삭제해야 한다.

### [보조-B] crawler_state_store.py의 upsert_document_state에서 source_type COALESCE 방향 오류

`upsert_document_state()`(469-577행)의 ON CONFLICT 절(564-565행)은 `source_type = COALESCE(EXCLUDED.source_type, crawler_documents.source_type)`으로 새 값을 우선한다. 반면 `upsert_discovered_url()`(408-467행, 452-453행)는 `source_type = COALESCE(crawler_documents.source_type, EXCLUDED.source_type)`으로 기존 값을 우선한다. 두 함수의 우선 방향이 다르기 때문에 파이프라인 실행 순서에 따라 source_type이 예상과 다르게 덮어쓰일 수 있다. 통일된 정책이 필요하다.

---

## 전체 적용 우선순위 일람표

| 우선순위 | 문제 | 작업 내용 | 예상 공수 |
|---|---|---|---|
| 즉시 | P0-2 학사일정 source_type | DB UPDATE + url_classifier.py 코드 수정 | 0.5일 |
| 즉시 | P2-7 teacher 404 URL | seeds.py 1줄 삭제 | 0.1일 |
| 단기 | P1-3 이전글/다음글 오염 | board_detail_extractor.py noise selector 추가 + 재수집 | 1-2일 |
| 단기 | P2-6 CMS URL 오분류 | url_classifier.py + seeds.py + static_page_extractor.py 패턴 추가 | 0.5일 |
| 단기 | P1-4 빈 문서 상태 추적 | run_ingestion_pipeline.py EMPTY_CONTENT 상태 기록 | 0.5일 |
| 단기 | P2-8 7개 source_type 누락 | DB 상태 확인 후 미수집 URL 크롤 실행 | 1일 |
| 단기 | 보조-A 데드코드 | board_detail_extractor.py 311-319행 삭제 | 0.1일 |
| 단기 | 보조-B COALESCE 방향 | upsert_document_state/upsert_discovered_url 정책 통일 | 0.5일 |
| 중기 | P1-5 첨부파일 추출 실패 | file_text_router.py OCR 폴백 + HWP LibreOffice 폴백 | 3-5일 |
| 중기 | P3-9 핵심 source_type 부족 | 크롤 실행 파라미터 확대 + library 파서 호환성 확인 | 1-2일 |
| 중기 | P3-10 admission URL 중복 | canonicalize_url() 강화 + seeds.py http URL 정리 | 1일 |
