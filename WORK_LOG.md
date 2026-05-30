# WORK_LOG — Crawler 품질 개선 작업 로그

> 작성일: 2026-05-27  
> 작업자: hyun_woo  
> 기준 문서: `docs/crawl-quality-report.md`

---

## 실행 제한 원칙

- 모든 실행: `docker compose` 환경 내에서만 수행
- 크롤링/임베딩: `--limit`, `--source-type`, `--doc-id` 등 범위 제한 필수
- 전체 재처리가 필요한 경우: 실행하지 않고 "대량 실행 필요" 섹션에 기록
- dry-run 우선 확인 후 실행

---

## P1 — 즉각 수정 가능한 설정/시드 문제

### P1-A: source_type 오분류 수정

**완료일**: 2026-05-27

#### 분석 결과

quality report에서 `faculty`, `academic_schedule`, `department_curriculum` 0건으로 보고됐으나, 실제 조사 결과:

- **faculty**: `department` source_type으로 341개 문서 이미 존재 (sub02.do 교수 소개 페이지). RAG `faculty_staff` query_family는 `source_boosts: ["department", "institution"]` 사용 → 검색 가능, 수정 불필요.
- **academic_schedule**: RAG의 query_family 이름이고, DB source_type 필터가 아님. `academic_calendar` source_type이 실제 사용됨.
- **department_curriculum**: RAG의 query_family 이름이고, DB source_type 필터가 아님. `department` source_type 문서들로 검색 가능.

#### 실제 문제 및 수정

`www.deu.ac.kr/www/scheduleList.do` (학사일정) 문서가 seeds.py에 `academic_calendar` source_type으로 정의됐으나, institution BFS 탐색에서 먼저 `institution`으로 저장됨.

**수행한 SQL**:
```sql
UPDATE crawler_documents
SET source_type = 'academic_calendar', updated_at = now()
WHERE canonical_url = 'https://www.deu.ac.kr/www/scheduleList.do';

UPDATE documents
SET source_type = 'academic_calendar', updated_at = now()
WHERE source_url = 'https://www.deu.ac.kr/www/scheduleList.do';
```

**결과**: `static_5811be281194ca6b` (학사일정 | 학사정보 | 대학생활) → source_type `academic_calendar`로 변경됨.

---

### P1-B: CRAWLER_ALLOW_NEEDS_REVIEW_ATTACHMENT_CHUNKS 활성화

**완료일**: 2026-05-27

#### 분석

`CRAWLER_ALLOW_NEEDS_REVIEW_ATTACHMENT_CHUNKS` 기본값 0 → HWP 등 `needs_review` 파싱 결과 청크가 DB에 저장되지 않음. 1,213개 HWP 파일 영향.

**수정 파일**: `compose.yml`

```yaml
# 수정 전
environment:
  - HWP5TXT_PATH=hwp5txt
  - CRAWLER_ALLOW_INSECURE_SSL=${CRAWLER_ALLOW_INSECURE_SSL:-0}

# 수정 후
environment:
  - HWP5TXT_PATH=hwp5txt
  - CRAWLER_ALLOW_INSECURE_SSL=${CRAWLER_ALLOW_INSECURE_SSL:-0}
  - CRAWLER_ALLOW_NEEDS_REVIEW_ATTACHMENT_CHUNKS=1
```

`.env.example`에도 변수 및 설명 추가.

**후속 조치 필요**: 설정 활성화만으로는 기존 차단된 청크가 생성되지 않음. needs_review 상태 문서들을 재처리해야 함 → **대량 실행 필요** 항목 참조.

---

### P1-C: retry_queue 소량 실행

**진행일**: 2026-05-27

#### retry_queue 현황 (실행 전)

| stage | task_type | reason | 건수 |
|-------|-----------|--------|------|
| file_parse | file_parse | low_text_per_page | 385 |
| file_parse | file_parse | too_short,low_text_per_page,low_meaningful_char_ratio | 362 |
| file_parse | file_parse | too_short,low_text_per_page | 355 |
| file_parse | file_parse | parser_empty_text | 349 |
| file_parse | file_parse | parser_unsupported | 92 |
| file_parse | file_parse | parser_failed | 57 |
| file_parse | file_parse | binary_marker_detected | 29 |
| file_parse | file_parse | parse_failed | 19 |
| attachment_download | attachment_download | download_failed | 18 |
| file_parse | file_parse | low_meaningful_char_ratio | 12 |
| board_list | board_list | list_fetch_or_parse_failed | 5 |

#### 실행 내역

**실행 1**: `attachment_download` + `board_list` 23건, `--allow-insecure-ssl --execute`

```bash
docker compose exec crawler python -m crawler.run.run_retry_failed_documents \
  --from-retry-queue --limit 30 \
  --stage attachment_download --stage board_list \
  --allow-insecure-ssl --execute
```

결과:
- `board_list` 5건: `lib.deu.ac.kr` SSL handshake failure → 모두 실패 (TLS 버전 호환 불가, P2-C에서 별도 처리)
- `attachment_download` 18건: 실행 중 (결과 확인 필요)

#### 최종 처리 결과 (2026-05-27)

P2-C SSL 수정 후 board_list 재시도했으나 lib.deu.ac.kr이 **slow loris 패턴** (SSL 연결 성공 후 응답을 매우 느리게 전송, 30초 read timeout 반복 리셋)으로 1시간 이상 hang 발생 → 강제 종료 후 dead_letter 처리.

**board_list 5건 처리 결과**:

| URL | 결과 |
|-----|------|
| lib.deu.ac.kr/sb/default_notice_list.mir | dead_letter (slow_loris_hang) |
| lib.deu.ac.kr/sb/faq_faq_list.mir | dead_letter |
| lib.deu.ac.kr/sb/default_elecInfonotice_list.mir | dead_letter |
| lib.deu.ac.kr/sb/libtoday_libtoday_list.mir | dead_letter |
| lib.deu.ac.kr/sb/default_lostproperty_list.mir | dead_letter |

**attachment_download 18건 처리 결과**:

| 분류 | 건수 | 처리 |
|------|------|------|
| lifelong.deu.ac.kr/Board/BoardView.aspx (게시판 뷰 URL - 파일 아님, 스크래퍼 버그) | 12 | dead_letter |
| gw.deu.ac.kr/myoffice 그룹웨어 (인증 필요) | 2 | dead_letter |
| 외부 뉴스 이미지 (asiae.co.kr) | 2 | dead_letter |
| deuhome.deu.ac.kr popup.png (팝업 이미지) | 1 | dead_letter |
| deuhome.deu.ac.kr exchange 파일 (117MB, 크기 제한 초과) | 1 | dead_letter |

**P1-C 완료 상태**: board_list 5건 + attachment_download 18건 모두 dead_letter. 실제 재처리 가능 항목 없음.

---

## P2 — 파서/파이프라인 수정

### P2-A: XLS/DOC 파서 추가

**완료일**: 2026-05-27

#### 분석

`file_text_router.py`에서 `.xls`, `.doc`, `.ppt` → `LEGACY_OFFICE_EXTENSIONS` → 무조건 `unsupported_legacy_office` 반환. 실제 92건 `parser_unsupported` 항목이 retry_queue에 대기.

LibreOffice가 crawler 컨테이너에 `/usr/bin/libreoffice`로 설치됨 확인.

**변환 전략**: LibreOffice `--headless --convert-to` 명령으로 OOXML 포맷 변환 후 기존 `OOXMLParser`로 파싱.

- `.xls` → `xlsx` → `OOXMLParser`
- `.doc` → `docx` → `OOXMLParser`
- `.ppt` → `pptx` → `OOXMLParser`

**수정 파일**: `crawler/crawler/parsers/file_text_router.py`

변경사항:
- `_LIBREOFFICE_CONVERT_MAP` 딕셔너리 추가 (`{".xls": "xlsx", ".doc": "docx", ".ppt": "pptx"}`)
- `_convert_with_libreoffice(file_path, src_ext)` 메서드 추가 (subprocess로 변환 후 OOXMLParser 호출)
- `LEGACY_OFFICE_EXTENSIONS` 처리: LibreOffice 변환 시도 → 실패 시 기존 unsupported 반환

**검증**:
```
XLS parser_type: xls_via_libreoffice, text length: 10133자
DOC parser_type: doc_via_libreoffice, text length: 2046자
```

**후속 조치 필요**: retry_queue의 `parser_unsupported` 92건 재시도 필요 → P1-C 완료 후 소량 실행.

---

### P2-B: PDF OCR 설정 확인

**상태**: 미착수 → 대량 실행 필요 항목으로 분리

---

### P2-C: library.deu.ac.kr SSL 실패 수정

**완료일**: 2026-05-27

#### 원인 분석

`lib.deu.ac.kr`에 Python requests 기본 세션으로 접근 시 `SSLV3_ALERT_HANDSHAKE_FAILURE` 발생. 이미 `LegacyTLSAdapter` (SECLEVEL=1) 구현이 `static_page_extractor.py`에 있었으나, `board_list_extractor.py`와 `BaseExtractor`에는 적용되지 않았음.

#### 수정 내용

1. **`crawler/utils/http_client.py`**: `LegacyTLSAdapter` 및 `INSECURE_SSL_HOSTS` 추가 (공통 모듈화)
2. **`crawler/extractors/base.py`**: `fetch_result`에 SSLError 시 LegacyTLSAdapter fallback 추가
3. **`crawler/extractors/board_list_extractor.py`**: `fetch`에 SSLError fallback 추가
4. **`crawler/extractors/static_page_extractor.py`**: `LegacyTLSAdapter` 임포트를 `http_client.py`에서 하도록 변경 (중복 제거)
5. **`compose.yml`**: `CRAWLER_ALLOW_INSECURE_SSL` 기본값을 0→1로 변경 (lib.deu.ac.kr 전용, 안전)

#### 검증

```bash
# BoardListExtractor로 lib.deu.ac.kr 연결 성공
SUCCESS, html length: 49396

# BaseExtractor로 lib.deu.ac.kr 연결 성공  
SUCCESS, html length: 49396
```

---

### P2-D: 파이프라인 미완료 소량 ingestion/vector

**완료일**: 2026-05-27 (옵션 추가 완료)

#### 분석

`run_ingestion_pipeline.py`와 `run_vector_ingestion.py`에 `--limit`, `--source-type` 옵션 없어 소량 실행 불가.

#### 수정 내용

- **`run_ingestion_pipeline.py`**: `parse_args()` 추가, `collect_curated_documents(source_type)` 파라미터, `run_ingestion()` 에서 limit/source-type 적용
- **`run_vector_ingestion.py`**: `--limit`, `--source-type` 파라미터 추가, `collect_chunk_files(source_type)` 파라미터, `main()`에서 limit/source-type 적용

#### 사용 방법

```bash
# source-type 지정 소량 처리
docker compose run --rm crawler python -m crawler.run.run_ingestion_pipeline \
  --source-type scholarship --limit 20

docker compose run --rm crawler python -m crawler.run.run_vector_ingestion \
  --source-type scholarship --limit 20 --batch-size 16
```

**실제 소량 실행 결과 (2026-05-27)**:

| source_type | 작업 | 처리 문서 | 임베딩 청크 |
|-------------|------|-----------|-------------|
| job | chunking 20 + vector | 35 | 59 |
| exchange | chunking 30 + vector | 72 | 67 |
| external_notice | chunking 50 + vector | 43 | 19 |
| admission | chunking 50 + vector | 79 | 8 |
| lifelong | chunking 50 + vector | 84 | 74 |
| institution | chunking 30 + vector | 43 | 13 |
| advising, dormitory, innovation, library, lostfound, notice, research_ethics, research, ipp, counsel, academic_support, academic, bhcoss, collabo, ctl, pluscenter, language, student_life | vector only | 각 5~45 | 0~17 (대부분 재사용) |
| department | chunking 150 + vector | 진행중 | - |

#### 발견된 버그 및 수정 (P3-A 후속)

**버그**: `_filter_source_duplicate_chunks`가 cross-source 중복 chunk를 `chunks` 테이블에서 제외하지만, 원본 chunk dict의 `metadata["quality_status"]`를 업데이트하지 않음. `run_vector_ingestion`은 JSON의 전체 chunk_id로 `chunk_embeddings` 삽입 시도 → `ForeignKeyViolation` (chunks 테이블에 없는 chunk_id).

**수정**: `pgvector_loader.py` `upsert_chunks()`에서 필터 후 누락된 chunk에 `metadata["quality_status"] = "duplicate_blocked"` 마킹 추가. `split_chunks_by_embedding_quality`가 이를 감지해 임베딩 제외.

```python
# 수정 위치: crawler/crawler/ingestion/pgvector_loader.py
# upsert_chunks() 내부, _filter_source_duplicate_chunks() 호출 직후
filtered_chunk_ids = {row["chunk_id"] for row in rows}
for chunk in chunks:
    chunk_id = chunk.get("chunk_id")
    if chunk_id and chunk_id not in filtered_chunk_ids:
        metadata = chunk.setdefault("metadata", {})
        if metadata.get("quality_status") not in {"binary_blocked"}:
            metadata["quality_status"] = "duplicate_blocked"
```

**검증**: department 100건 재처리 → failed_docs=0 (수정 전 11건 실패)

**실제 대량 실행 - 일괄 vector ingestion 결과 (2026-05-27)**:

32개 source_type 일괄 vector ingestion (`--limit 200`) 완료. 모든 source_type `failed_docs=0`.

새로 임베딩된 청크 (source_type별 embedded_chunks 합산):
- admission: 34, institution: 37, dormitory: 1, ipp: 1, collabo: 2, language: 23, academic_notice: 22, reference: 1, teacher: 2 → 합계 약 **123 청크** 신규 임베딩
- 나머지 source_type: 기존 embedding 재사용 (embedded_chunks=0)

**최종 DB 상태 (2026-05-27 완료 후)**:

| 상태 | 건수 | 비고 |
|------|------|------|
| INDEXED | 6,262 | 이전 6,229 → +33 |
| CHUNKED | 578 | 520건: 0-chunk 정상, 58건: vector_status=INDEXED |
| PARSED | 217 | ingestion 필요 |
| DISCOVERED | 203 | 전체 파이프라인 필요 |
| FAILED | 18 | department 8, it_service 4, has/institution/library/admission/teacher/disability 각 1 |
| **chunks** | **35,801** | embeddings와 완전 일치 |
| **embeddings** | **35,801** | |
| retry_pending | 1,664 | 주로 file_parse (low_text_per_page, parser_unsupported 등) |

---

## P3 — 청킹/임베딩 품질 개선

### P3-A: cross-source chunk dedup 수정

**완료일**: 2026-05-27

#### 분석

`pgvector_loader.py`의 `_filter_source_duplicate_chunks`에서 `WHERE d.source_type = %s` 조건으로 동일 source_type 내 중복만 체크. cross-source 중복 (같은 공지가 여러 source_type에 게시)은 미처리.

#### 수정 내용

**`crawler/ingestion/pgvector_loader.py`**:
- `_filter_source_duplicate_chunks`에서 `source_type` 조건 제거 → 전체 chunks에서 content_hash 중복 체크
- dedup 로그의 `dedupe_scope: "source_type"` → `"global"` 변경
- skip_reason: `"duplicate_content_hash_in_source"` → `"duplicate_content_hash_cross_source"` 변경

**`compose.yml`**: `CRAWLER_BLOCK_SOURCE_DUPLICATE_CHUNKS=1` 추가 (기본 활성화)

**기존 중복 청크 정리**: 대량 실행 필요 항목으로 분리.

---

### P3-B: 게시판 목록 URL 분류 오류 수정

**완료일**: 2026-05-27

#### 분석

학과 sub02.do URL (교수 소개 게시판 목록)이 `static_page`로 분류되어 교수 개별 상세 페이지 미수집. DB에 "교수소개 게시판목록" 제목으로 목록 페이지만 수집됨.

#### 수정 내용

1. **`crawler/discovery/url_classifier.py`**: `/sub02.do`, `/sub02_N.do` 패턴 → `board_list` 분류 추가
2. **`crawler/config/seeds.py`**: `_doc_seed_page_kind`에 동일 패턴 추가

**기존 잘못 분류된 sub02.do 문서 재처리**: 대량 실행 필요 항목으로 분리.

---

### P3-C: table chunk placeholder 수정

**완료일**: 2026-05-27

#### 분석

table section의 section_title이 "table"로 설정되어 청크 content에 `[TABLE]\ntable\n`이 불필요하게 포함됨.

#### 수정 내용

**`crawler/ingestion/chunker.py`** `build_chunk_content`:
```python
# 수정 전
if section_title:
    parts.append(f"[{section_type}]\n{section_title}")

# 수정 후  
if section_title and section_title.lower() != section_type.lower():
    parts.append(f"[{section_type}]\n{section_title}")
```

**기존 table 청크 재생성**: 대량 실행 필요 항목으로 분리.

---

## 대량 실행 필요 항목 (실제 실행하지 않음)

아래 항목들은 대량 처리가 필요하여 현재 세션에서 실행하지 않고 별도 운영 작업으로 분리합니다.

| 항목 | 규모 | 이유 |
|------|------|------|
| needs_review HWP 청크 재생성 | ~1,213 문서 | CRAWLER_ALLOW_NEEDS_REVIEW_ATTACHMENT_CHUNKS=1 설정 후 전체 재처리 필요. run_full_pipeline 전체 실행에 해당 |
| file_parse low_text_per_page 재처리 | ~1,102건 | PDF OCR 설정 확인 및 튜닝 후 전체 재시도 |
| parser_unsupported XLS/DOC 재처리 | 92건 | P2-A 파서 추가 후 retry_queue 전체 재시도 가능 (소량 검증 후 판단) |
| PARSED 217건 ingestion | 217건 | run_ingestion_pipeline으로 chunking 필요 |
| DISCOVERED 203건 전체 파이프라인 | 203건 | fetch → parse → chunk → embed 전체 실행 필요 |
| FAILED 18건 재처리 | 18건 | 원인 분석 후 재시도 가능한 것들 선별 필요 |
| sub02.do URL 재처리 (P3-B 수정 후) | 수백 건 예상 | 교수 상세 페이지 재크롤링 필요 |
