# crawler 운영 메모

동의대학교 도메인 특화 RAG 적재 파이프라인의 크롤링, 파싱, 청킹, 임베딩, 검증 작업을 담당한다.

## 빠른 실행

프로젝트 루트에서 Docker 환경으로 실행한다.

```powershell
docker compose run --rm crawler python -m crawler.run.run_full_pipeline
docker compose run --rm crawler python -m crawler.run.run_rag_load_check
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --execute
docker compose run --rm crawler python -m unittest discover tests
```

`run_retry_failed_documents`는 기본값이 dry-run이다. 실제 재처리는 `--execute`를 붙여야 수행된다.

## 주요 진입점

| 파일 | 역할 |
| --- | --- |
| `crawler/run/run_full_pipeline.py` | 정적 페이지와 게시판 수집을 수행하는 전체 파이프라인 진입점 |
| `crawler/run/run_rag_load_check.py` | Supabase에 적재된 RAG 데이터가 검색 가능한 형태인지 최소 SQL로 점검 |
| `crawler/run/run_retry_failed_documents.py` | `crawl_logs`의 실패 이력을 기준으로 정적 페이지와 벡터 적재 실패 건 재처리 |
| `crawler/extractors/board_list_extractor.py` | 게시판 목록 페이지에서 상세 URL 후보를 추출 |
| `crawler/extractors/board_detail_extractor.py` | 게시판 상세 페이지에서 본문, 표, 첨부 정보를 추출 |
| `crawler/parser/file_text_router.py` | 첨부파일 확장자별 텍스트 추출 라우팅 |
| `crawler/parser/text_quality.py` | 추출 텍스트의 검색 가능 품질 판정 |

## source_type / page_kind 정책

`source_type`은 문서의 출처 계열을 나타낸다. RAG 필터링, 실패 재처리, 결과 리포트에서 공통 키로 사용되므로 새 소스를 추가할 때 기존 값을 재활용하거나 명확한 신규 값을 추가해야 한다.

| source_type | 의미 | 비고 |
| --- | --- | --- |
| `admission` | 입학 관련 정적 페이지/첨부 | 정적 페이지 실패 재처리 대상 |
| `has` | 보건/행정 계열 정적 페이지 | 정적 페이지 실패 재처리 대상 |
| `library` | 중앙도서관 정적 페이지 | SSL 설정 영향을 받을 수 있음 |
| `board` 계열 값 | 게시판 목록/상세 기반 문서 | URL 또는 source_type에 `board`가 포함되면 게시판 샘플로 집계됨 |

`page_kind`는 같은 `source_type` 안에서 페이지 성격을 구분하는 보조 값이다. 신규 크롤러를 추가할 때는 다음 원칙을 따른다.

| page_kind | 사용 기준 |
| --- | --- |
| `static_page` | 메뉴/안내/학과 소개처럼 단일 URL 본문을 저장하는 경우 |
| `board_list` | 게시판 목록에서 상세 URL 후보를 찾는 경우 |
| `board_detail` | 게시판 상세 본문과 첨부파일을 저장하는 경우 |
| `attachment` | 첨부파일 자체의 텍스트 추출 결과를 저장하는 경우 |

새 소스 추가 시 `source_type`은 DB 조회와 재처리 단위가 되므로 짧고 안정적인 영문 식별자를 사용한다. `page_kind`는 처리 단계의 성격을 드러내는 값으로 유지한다.

## 첨부파일 파싱 정책

첨부파일은 가능한 경우 `document_assets`에 메타데이터를 저장하고, 검색 가능한 텍스트가 있으면 `document_contents.asset_id`로 연결한다. `run_rag_load_check`는 다음 값을 구분해서 표시한다.

| 항목 | 의미 |
| --- | --- |
| 전체 첨부파일 수 | `document_assets`의 전체 행 수 |
| 파싱 시도 첨부파일 수 | `parser_type`이 기록된 첨부 수 |
| 검색 가능 첨부파일 수 | `document_contents`에 연결된 비어 있지 않은 첨부 텍스트 수 |
| 구형 Office 첨부 수 | `.doc`, `.xls`, `.ppt` 또는 `unsupported_legacy_office`로 분류된 첨부 수 |

구형 Office 바이너리 포맷(`.doc`, `.xls`, `.ppt`)은 현재 안정적으로 파싱된다고 가정하지 않는다. 운영 리포트에서 발견되면 LibreOffice 변환 또는 별도 추출기를 붙이는 작업을 우선 검토한다.

## 실패 재처리

최근 실패 이력은 `crawl_logs`에서 확인한다. 재처리 스크립트는 기본적으로 다음 stage만 대상으로 삼는다.

| stage | 재처리 방식 |
| --- | --- |
| `static_page` | 실패 로그의 URL과 source_type으로 정적 페이지를 다시 수집/저장 |
| `vector_ingestion` | `CHUNK_DIR/{source_type}/{doc_id}.json`을 찾아 임베딩과 pgvector 적재 재시도 |

예시:

```powershell
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --stage vector_ingestion --execute
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --stage static_page --allow-insecure-ssl --execute
```

`--allow-insecure-ssl`은 SSL 인증서 문제로 실패한 정적 페이지를 재시도할 때만 사용한다.

## 테스트

로컬 Python 직접 실행 대신 Docker 환경에서 테스트한다.

```powershell
docker compose run --rm crawler python -m unittest discover tests
```

현재 fixture 테스트는 게시판 목록/상세 extractor, 첨부 라우터, 텍스트 품질, 청킹/파서를 중심으로 구성되어 있다. 신규 크롤러를 추가할 때는 최소한 목록 fixture 1개와 상세 fixture 1개를 테스트에 추가한다.
