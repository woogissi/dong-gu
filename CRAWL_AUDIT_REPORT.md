# 크롤링 결과 품질 점검 보고서

**작성일**: 2026-05-28  
**분석 대상**: `crawler/crawler/data/curated/` (2,555개), `crawler/crawler/data/rag_ready/chunks/` (2,466개)  
**DB 적재 현황**: documents 378개, chunks 3,223개, embeddings 3,218개

---

## 1. 전체 상태 요약

| 항목 | 수치 |
|------|------|
| curated 문서 총 수 | 2,555개 |
| chunk 파일 총 수 | 2,466개 |
| DB 적재 문서 수 | 378개 |
| DB 미적재 curated 파일 | 약 2,177개 (85.2%) |
| normalize 100자 미만 문서 | 453개 (17.7%) |
| 완전 빈 문서 (모든 컨텐츠 없음) | 89개 (3.5%) |
| attachment_text 추출 성공 | 518개 (20.3%) |
| FAILED 상태 문서 | 28개 |
| DISCOVERED 미처리 | 70개 |
| PARSED 미청킹 | 274개 |
| file_parse ValueError | 331건 |
| binary_marker_detected 차단 | 97건 |

### 데이터 파이프라인 상태 분포 (crawler_documents)
```
CHUNKED:    2,128개  (수집→파싱→청킹 완료)
INDEXED:      333개  (벡터 적재 완료)
PARSED:       274개  (파싱 완료, 청킹 대기)
DISCOVERED:    70개  (발견만, 수집 미착수)
FAILED:        28개  (수집/파싱 실패)
```

---

## 2. 발견된 문제 목록 (우선순위별)

### [P0] 문제 1 — DB 미적재 curated 파일 대량 존재

**증상**: curated 파일 2,555개 중 DB에 적재된 문서는 378개(14.8%)에 불과함. 나머지 2,177개는 청킹까지 완료된 상태이나 DB에 올라가지 않음.

**재현**: 
- curated 파일: `crawler/crawler/data/curated/documents/` 하위 2,555개
- DB `documents` 테이블: 378개 (`SELECT COUNT(*) FROM documents;` → 378)
- CHUNKED 상태(crawler_documents): 2,128개이나 documents 테이블에는 378개만 존재

**원인**: `run_vector_ingestion.py`가 부분적으로만 실행되었거나, `crawler_documents` 테이블의 CHUNKED 상태와 실제 벡터 DB 적재가 별개 단계로 동작하기 때문. 즉 청킹은 로컬 파일로 완료되었으나 `pgvector_loader.py`의 `upsert_document()` / `upsert_chunks()` 단계가 아직 실행되지 않음.

**영향 범위**: 전체 source_type 중 다수. 특히 notice(48개), scholarship(91개), academic_notice(39개), department(965개) 등 RAG 핵심 데이터 대부분이 미적재.

**수정 방향**: `run_vector_ingestion.py`를 Docker 환경에서 전체 소스타입 대상으로 실행하여 curated → DB 적재 완료 필요.

---

### [P0] 문제 2 — academic_calendar (학사일정) source_type 오분류

**증상**: seeds.py에 `deu_schedule_list`가 `source_type: academic_calendar`로 정의되어 있으나, 실제 수집된 파일은 `it_service` 디렉토리에 저장됨. curated/academic_calendar/ 디렉토리 자체가 없음.

**재현**:
- seeds.py: `"deu_schedule_list"`, `url: "https://www.deu.ac.kr/www/scheduleList.do"`, `source_type: "academic_calendar"`
- DB 조회: `SELECT url, status, source_type FROM crawler_documents WHERE url LIKE '%scheduleList%';`
  - 결과: `https://www.deu.ac.kr/www/scheduleList.do` → status=`CHUNKED`, source_type=`it_service`
- 실제 curated 파일: `crawler/crawler/data/curated/documents/it_service/` 에 `scheduleList.do` 파일 존재 (normalize 3,895자로 내용은 정상)

**원인**: `crawler_state_store.py` 또는 크롤 파이프라인에서 URL을 처리할 때 seeds.py의 `source_type` 값이 아닌 URL 기반으로 source_type을 재결정하는 로직이 개입하여 `it_service`로 잘못 분류됨.

**영향 범위**: 학사일정 데이터 1개 문서. RAG에서 "학사일정", "개강일", "수강신청" 등 질의 시 academic_calendar source_type으로 필터링하면 검색 누락 발생.

**수정 방향**: 수집 파이프라인에서 seeds.py의 `source_type`을 우선 사용하도록 수정. 또는 `scheduleList.do` URL에 대한 source_type 재분류 규칙 추가.

---

### [P1] 문제 3 — normalize 필드에 이전글/다음글 제목 유입 (크로스 오염)

**증상**: 게시판 상세(board_detail) 문서의 normalize 필드 끝부분에 해당 문서의 내용이 아닌 이전 게시글 또는 다음 게시글의 제목이 append됨.

**재현**:
- `crawler/crawler/data/curated/documents/notice/deu_notice_79942.json`
  - title: "[후원의 집] 밝은세상안과 1~2월 우대 혜택 안내"
  - normalize 끝 3줄: `- 서울/부산점 위치 [3학년 필독] 26년 취업 준비, 3분이면 끝! 경품 추첨 [후원의 집] 하늘안과 1~2월 우대 혜택 안내`
- notice 48개 중 31개(64.6%)에서 동일 패턴 탐지

**원인**: `static_page_extractor.py`의 `find_content_node()` 및 `clean_static_text()`가 게시판 상세 페이지의 "이전글/다음글" 네비게이션 블록을 본문으로 오인하여 포함시킴. `STATIC_NOISE_SELECTORS`에 이전글/다음글 컨테이너 selector가 누락된 것으로 추정. 또는 board_detail 페이지에서 네비게이션 링크 텍스트(제목)가 본문 DOM 안에 위치하여 필터링되지 않음.

**영향 범위**: notice, academic_notice, scholarship, department 등 board_detail 타입 전반. 공통 패턴으로 상당수 문서에 영향.

**수정 방향**: 
1. `static_page_extractor.py`의 `STATIC_NOISE_SELECTORS`에 `.prev-next`, `.board-navi`, `.view-nav` 등 이전글/다음글 블록 selector 추가.
2. board_detail extractor 또는 curate 단계에서 normalize 끝의 다른 게시글 제목 패턴(`\[.*\]$`, 짧은 1줄 제목) 제거 후처리 추가.

---

### [P1] 문제 4 — 완전 빈 문서 89개 (본문 없는 수집 결과 저장)

**증상**: normalize, structured_sections, table_text, attachment_text 4가지 컨텐츠 필드가 모두 비어있는 문서가 89개 존재.

**재현**:
- `crawler/crawler/data/curated/documents/department/static_083728d7df8bcee1.json` → url: `http://cinema.deu.ac.kr/`, 전 필드 공백
- `crawler/crawler/data/curated/documents/department/static_095795ee7972e599.json` → url: `https://swcc.deu.ac.kr/computer/sub05_01.do`, quality_filter.raw_text_length_before=0
- 빈 문서 분포: department(56개), admission(7개), lifelong(6개), institution(5개) 등

**원인**:
1. **장학안내 페이지 패턴** (`sub05_01.do`): 학과별 장학안내 페이지가 JavaScript 동적 렌더링으로 내용을 로드하여 정적 크롤러가 빈 HTML을 수신. `quality_filter.raw_text_length_before=0`이 확인됨.
2. **경로 인코딩 문제** (`cinema.deu.ac.kr/`): 메인 페이지 접근 시 charset 문제로 텍스트 추출 실패. title에 깨진 문자(`ëìëíêµ`) 존재.
3. **VR 투어 페이지** (`vrtour/tour.html`): HTML 기반 3D 뷰어로 텍스트 컨텐츠 없음.

**영향 범위**: curated 전체의 3.5%(89개). 이 중 56개가 department. 빈 chunk를 생성하지 않으므로 직접적 RAG 오염은 없으나 수집 실패가 보고되지 않아 파악이 어려움.

**수정 방향**:
1. 청킹/적재 파이프라인에서 빈 문서를 명시적으로 `SKIP` 또는 `FAILED` 상태로 기록하여 추적 가능하게 처리.
2. JavaScript 렌더링이 필요한 페이지(`sub05_01.do` 패턴) 식별 후 Playwright/Selenium 사용 또는 수집 제외 목록 관리.

---

### [P1] 문제 5 — file_parse 실패 331건 (첨부파일 텍스트 추출 실패)

**증상**: DB `crawl_logs` 기준 stage=`file_parse`, error_type=`ValueError` 오류가 331건. 주요 원인: `too_short,low_text_per_page`, `parser_empty_text`, `low_meaningful_char_ratio`.

**재현**: 
```sql
SELECT source_type, stage, error_type, COUNT(*) as cnt 
FROM crawl_logs 
WHERE stage='file_parse' AND error_type='ValueError' 
GROUP BY source_type, stage, error_type 
ORDER BY cnt DESC;
```
- department: 76건
- scholarship: 41건
- job: 20건
- education: 17건
- foundation: 14건

**원인**:
1. **스캔 PDF**: 이미지로 스캔된 PDF는 `PDFParser`로 텍스트 추출이 불가능하여 `too_short`, `low_text_per_page` 발생. OCR 미적용 상태.
2. **HWP 파서 제한**: `hwp_parser.py`가 일부 HWP 형식에서 텍스트 추출 실패 → `parser_empty_text`.
3. **저품질 첨부파일**: 단순 이미지나 표지만 있는 PDF에서 `low_meaningful_char_ratio` 발생.

**영향 범위**: scholarship(41건), job(20건) 등 학생이 자주 조회하는 장학금/취업 공고의 상세 내용이 RAG에서 누락.

**수정 방향**:
1. `PDFParser`에 OCR 옵션 추가 (pytesseract 또는 Azure OCR). `file_text_router.py`에 스캔 PDF 감지 후 OCR 라우팅 분기 추가.
2. `parser_empty_text` 상태인 파일을 주기적으로 재시도하는 `retry` 큐 활용.

---

### [P2] 문제 6 — FAILED 28건 중 PDF/바이너리 파일을 static_page로 오분류 처리

**증상**: `www.deu.ac.kr/cms/etcResourceDown.do` 및 `etcResourceOpen.do` URL들이 `page_kind=static_page`로 등록되어 수집을 시도하다 `non-html static response: content_type=application/pdf` 오류 발생.

**재현**: DB 조회 결과
- `https://www.deu.ac.kr/cms/etcResourceDown.do?site=...` (safety, it_service, institution 등) 총 14건
- `https://www.deu.ac.kr/cms/etcResourceOpen.do?site=...` (disability_support, it_service) 다수
- 오류: `non-html static response: url=... content_type=application/pdf`

**원인**: `extract_internal_links()` 또는 `extract_navigation_links()`가 `etcResourceDown.do`, `etcResourceOpen.do` URL을 PDF 파일 링크임을 인식하지 못하고 내부 링크로 수집. `_doc_seed_page_kind()` 함수도 이 패턴을 `attachment`가 아닌 `static_page`로 분류.

**영향 범위**: safety(7건), it_service(4건), institution(1건), disability_support(1건). 주로 동의대학교 CMS 시스템의 파일 링크들.

**수정 방향**: 
1. `seeds.py`의 `_doc_seed_page_kind()` 함수에 `etcResourceDown`, `etcResourceOpen` 패턴 추가하여 `attachment`로 분류.
2. `static_page_extractor.py`의 `extract_internal_links()`에서 CMS 다운로드 URL 패턴 필터링 추가.

---

### [P2] 문제 7 — teacher source_type board_list 30건 404 오류

**증상**: `deuhome.deu.ac.kr/teacher/sub02_05.do`에 대한 게시판 목록 요청이 모두 404.

**재현**: 
```
DB: stage=board_list, source_type=teacher, error_type=HTTPError 30건
URL 패턴: https://deuhome.deu.ac.kr/teacher/sub02_05.do?article.offset=N&articleLimit=10&mode=list
```

**원인**: `sub02_05.do` 페이지가 더 이상 존재하지 않거나 URL 구조가 변경됨. seeds.py의 `_DOC_SEED_URLS`에 포함된 `https://deuhome.deu.ac.kr/teacher/sub02_05.do`가 유효하지 않은 URL.

**영향 범위**: teacher source_type 전체 41개 중 일부. 교원 관련 게시판 글 수집 실패.

**수정 방향**: seeds.py에서 `teacher/sub02_05.do` 항목 제거 또는 올바른 URL로 교체. 주기적인 seed URL 유효성 검사 추가.

---

### [P2] 문제 8 — seeds.py에 정의된 source_type 7개가 curated에 완전 누락

**증상**: seeds.py에 정의된 source_type 중 아래 7개에 대응하는 curated 파일이 없음:
`academic`, `facility`, `newsletter`, `academic_calendar`, `fund`, `language`, `culture_innovation`

**재현**:
- `crawler/crawler/data/curated/documents/` 하위 디렉토리에 해당 source_type 없음
- seeds.py에 `academic` (대학 학부 정보), `facility` (시설정보), `newsletter`, `fund` (기금) 등 정의됨

**원인**:
1. `academic_calendar`: source_type 오분류로 `it_service`에 저장됨 (문제 2 참조)
2. `facility`, `newsletter`, `fund` 등: 수집은 되었으나 다른 source_type으로 분류되거나, 크롤 파이프라인에서 아직 처리되지 않은 DISCOVERED 상태일 가능성.
3. `language`: `language_intro`는 존재하지만 `language`는 누락 — deuhome.deu.ac.kr/language/ 페이지들이 미수집이거나 다른 source_type으로 병합됨.

**영향 범위**: 중간 우선순위. 시설 정보, 뉴스레터, 기금 등 부가 정보 누락.

**수정 방향**: 각 source_type 별로 DB `crawler_documents` 테이블 확인하여 실제 수집 여부 파악 후 미수집 URL 재크롤 실행.

---

### [P3] 문제 9 — 핵심 source_type의 파일 수 절대적 부족

**증상**: 학생 질의 핵심 대상인 아래 source_type들의 수집 파일 수가 매우 부족:
- cafeteria: 1개 (교내식당 메뉴 정보 등 누락)
- shuttle: 2개 (셔틀버스 정보 부족)
- library: 9개 (도서관 전체 서비스 정보 미흡)
- notice: 48개 (총 게시글 대비 수집량 제한적)
- scholarship: 91개
- it_service: 3개

**재현**: 각 디렉토리 파일 수 집계 결과

**원인**: 각 board_list seed에서 수집 페이지 수(`page_size`, 페이지 범위) 제한 또는 게시판 목록 크롤 깊이 제한으로 인해 과거 게시글이 누락됨.

**영향 범위**: 학생 대상 주요 정보 질의 시 RAG 답변 품질 저하.

**수정 방향**: `run_crawl_to_rag.py` 실행 시 `--since-date` 범위 확대 또는 전체 페이지 수집 옵션 적용. cafeteria, shuttle 등 static_page 타입은 크롤 주기 점검.

---

### [P3] 문제 10 — admission 중복 청크 47건 cross-source dedup 차단

**증상**: admission source_type에서 content_quality_gate 단계에 `duplicate_blocked` 47건 발생. 동일한 입학 안내 페이지가 여러 URL(`menuord=5`, `menuord=6`, `menuUrl=...`)에서 동일 내용을 수집하여 cross-source dedup에 의해 청크 저장 차단.

**재현**: 
```sql
SELECT url, error_message FROM crawl_logs 
WHERE source_type='admission' AND stage='embedding_quality_gate' LIMIT 10;
```
- `https://ipsi.deu.ac.kr/submenu.do?menuord=6` → `duplicate_blocked`
- `http://ipsi.deu.ac.kr/submenu.do?menuord=6&` → 동일 내용 중복

**원인**: `ipsi.deu.ac.kr/submenu.do`가 URL 파라미터(menuord, menuUrl)에 따라 다른 페이지를 서빙하지만 일부 페이지는 동일 내용을 렌더링. 또한 http/https URL 정규화 미흡으로 같은 페이지가 중복 수집됨.

**영향 범위**: admission source_type 청크 47건 미저장. 실질적 데이터 손실은 적으나 불필요한 크롤 리소스 낭비.

**수정 방향**: 
1. `canonicalize_url()` 함수에서 http→https 정규화 및 빈 쿼리 파라미터(`?` 트레일링) 제거 강화.
2. 입학처 `submenu.do` 페이지에 대한 content hash 비교 후 중복 수집 스킵 처리.

---

## 3. 실제 누락 사례 (URL/path 포함)

### 사례 1 — 학사일정 source_type 오분류
- **파일**: `crawler/crawler/data/curated/documents/it_service/static_*.json` (source_url: `https://www.deu.ac.kr/www/scheduleList.do`)
- **문제**: source_type이 `academic_calendar` 아닌 `it_service`로 저장됨
- **RAG 영향**: "학사일정", "개강일", "수강신청 기간" 질의 시 `academic_calendar` 필터 적용 시 검색 누락

### 사례 2 — 이전글/다음글 제목 오염 (notice 64.6%)
- **파일**: `crawler/crawler/data/curated/documents/notice/deu_notice_79942.json`
- **normalize 끝 내용**: `[3학년 필독] 26년 취업 준비, 3분이면 끝! 경품 추첨 [후원의 집] 하늘안과 1~2월 우대 혜택 안내`
- **RAG 영향**: 청크에 다른 게시글 제목이 포함되어 관련성 없는 문서 검색 유발

### 사례 3 — 완전 빈 department 문서 대표 사례
- `static_083728d7df8bcee1.json` → `http://cinema.deu.ac.kr/` (JavaScript 렌더링 실패)
- `static_38563e74d717b080.json` → `https://www.deu.ac.kr/site/resource/www/vrtour/tour.html` (VR 뷰어, 인코딩 깨짐)
- `static_095795ee7972e599.json` → `https://swcc.deu.ac.kr/computer/sub05_01.do` (장학안내, raw_text_before=0)

### 사례 4 — CMS 파일 URL을 static_page로 오분류 처리 실패
- `https://www.deu.ac.kr/cms/etcResourceDown.do?site=%24cms%24O4o&key=...` (safety)
- `https://www.deu.ac.kr/cms/etcResourceOpen.do?site=%24cms%24O4o&key=...` (it_service)
- 오류: `non-html static response: content_type=application/pdf`

### 사례 5 — 스캔 PDF 텍스트 추출 실패 (scholarship 41건)
- `https://www.deu.ac.kr/www/deu-scholarship.do?mode=download&articleNo=*&attachNo=*`
- 오류: `too_short,low_text_per_page` — 장학금 공고 첨부파일 내용 RAG 미수록

---

## 4. RAG 영향 분석

### 고위험 영역
1. **학사일정 질의**: `scheduleList.do`가 `it_service`에 분류되어 academic_calendar 기반 필터링 시 누락. 학사일정, 수강신청, 개강일 등 핵심 질의 영향.

2. **notice/scholarship 게시글 크로스 오염**: 31개 notice 문서에 다른 게시글 제목이 섞여 RAG 검색 시 관련 없는 문서가 상위 랭킹 가능성 증가.

3. **장학금/취업 첨부파일 누락**: scholarship(41건), job(20건)의 첨부파일 텍스트가 미수록되어 장학금 신청 자격, 지원 금액 등 구체적 정보 답변 불가.

### 중위험 영역
4. **DB 미적재 2,177개**: curated까지 완료된 데이터 대부분이 RAG 검색에서 아예 제외됨. 현재 RAG DB에는 378개 문서(3,223 chunks)만 실제 검색 가능.

5. **cafeteria 1개, shuttle 2개**: 교내식당 운영시간, 셔틀버스 노선 질의에 대한 정보가 극히 제한적.

---

## 5. 수정 우선순위 제안

### 즉시 조치 (운영 영향도 높음)
1. **[P0] run_vector_ingestion.py 전체 실행**: 2,177개 curated 파일을 DB에 적재하여 실제 RAG 검색 가능 문서 수 증가 (`docker compose run --rm crawler python -m crawler.run.run_vector_ingestion`)
2. **[P0] 학사일정 source_type 수정**: `scheduleList.do` 파일의 source_type을 `academic_calendar`로 변경 후 재색인

### 단기 코드 수정 (1~2주)
3. **[P1] 이전글/다음글 노이즈 제거**: `static_page_extractor.py`의 `STATIC_NOISE_SELECTORS`에 게시판 네비게이션 블록 CSS 선택자 추가
4. **[P2] CMS 파일 URL 분류 수정**: `_doc_seed_page_kind()` 및 `extract_internal_links()`에 `etcResourceDown/Open.do` 패턴을 `attachment`로 분류하는 규칙 추가
5. **[P2] 유효하지 않은 seed URL 제거**: `teacher/sub02_05.do` 등 404 발생 URL 정리

### 중기 개선 (1개월)
6. **[P1] 스캔 PDF OCR 지원**: `file_text_router.py`에 텍스트 추출 실패 PDF에 대한 OCR 폴백 추가
7. **[P2] 빈 문서 추적 개선**: 파이프라인에서 완전 빈 문서를 `EMPTY_CONTENT` 상태로 명시 기록
8. **[P3] 핵심 source_type 수집 확대**: cafeteria, shuttle 등 페이지의 동적 컨텐츠 수집 방안 검토 (메뉴 데이터는 자주 변경되므로 주기적 재수집 필요)

---

## 부록 — 분석 방법론

- 코드 분석: `crawler/crawler/extractors/`, `ingestion/`, `parsers/`, `run/` 전체 검토
- 데이터 분석: PowerShell로 curated 2,555개, chunk 2,466개 전수 JSON 파싱
- DB 분석: Docker exec로 `donggu-postgres` 컨테이너의 chatbot DB 직접 조회
- 바이너리 오염: 전체 curated 파일 대상 `%PDF|endobj|HWP Document File` 패턴 검색 → 0건 (양호)
- HTTP 요청: 이번 분석에서는 실제 HTTP 요청 미수행 (로컬 파일 및 DB 기반 분석)
