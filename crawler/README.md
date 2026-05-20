# crawler 운영 메모

동의대학교 도메인 특화 RAG 적재 파이프라인의 크롤링, 파싱, 청킹, 임베딩, 검증 작업을 담당한다.

## 운영 표준 수동 실행

프로젝트 루트에서 Docker Compose로만 실행한다. 운영 수동 실행의 표준 경로는 `run_crawl_to_rag`이며, 수집, 청킹, 벡터 적재, RAG 적재 점검을 순서대로 수행한다.

```powershell
docker compose run --rm crawler python -m crawler.ops.supabase_smoke_check --ensure-tables
docker compose run --rm crawler python -m crawler.run.run_crawl_to_rag --fail-on-partial
```

증분 운영 실행은 다음 옵션을 기본으로 둔다.

```powershell
docker compose run --rm crawler python -m crawler.run.run_crawl_to_rag --since-date 2025-12-01 --pages 10 --detail-workers 3 --fail-on-partial
```

특정 사유로 단계를 나누어 실행해야 할 때만 아래 명령을 사용한다.

```powershell
docker compose run --rm crawler python -m crawler.run.run_static_discovery --closed-loop-discovery --max-pages 200 --max-depth 2
docker compose run --rm crawler python -m crawler.run.run_full_pipeline --closed-loop-discovery --incremental --since-date 2025-12-01 --pages 10 --compress-raw-html --detail-workers 3
docker compose run --rm crawler python -m crawler.run.run_ingestion_pipeline
docker compose run --rm crawler python -m crawler.run.run_vector_ingestion --batch-size 32
docker compose run --rm crawler python -m crawler.run.run_rag_load_check --fail-on-partial
```

운영 기본 원칙:

- DB/RLS 상태 확인은 첫 실행 또는 스키마 변경 뒤 `supabase_smoke_check --ensure-tables`로 확인한다.
- 전체 수동 실행은 `run_crawl_to_rag --fail-on-partial`을 우선한다.
- 단계별 실행이 필요하면 `static_discovery -> full_pipeline -> ingestion_pipeline -> vector_ingestion -> rag_load_check` 순서를 유지한다.
- `--allow-insecure-ssl`은 SSL 인증서 문제로 실패한 DEU 구형 호스트를 재시도할 때만 붙인다.
- `run_retry_failed_documents`는 기본값이 dry-run이다. 실제 재처리는 반드시 `--execute`를 붙여 수행한다.
- 운영 재처리는 `crawl_logs` 직접 조회보다 `--from-retry-queue`를 우선 사용해 `crawler_retry_queue`의 `task_type`, `attempts`, `last_error`, `dead_letter` 상태를 남긴다.

## 주요 진입점

| 파일 | 역할 |
| --- | --- |
| `crawler/run/run_full_pipeline.py` | 정적 페이지와 게시판 수집을 수행하는 전체 파이프라인 진입점 |
| `crawler/run/run_rag_load_check.py` | Supabase에 적재된 RAG 데이터가 검색 가능한 형태인지 최소 SQL로 점검 |
| `crawler/run/run_retry_failed_documents.py` | `crawler_retry_queue` 또는 `crawl_logs`의 실패 이력을 기준으로 task_type별 재처리 |
| `crawler/run/run_static_discovery.py` | 정적 페이지를 제한 탐색하고 게시판형 URL은 후보 manifest로만 기록 |
| `crawler/ops/supabase_smoke_check.py` | Supabase 상태 테이블 존재/RLS/쓰기 권한 smoke check |
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

Seed에는 다음 운영 정책 값을 둘 수 있다.

| 필드 | 의미 |
| --- | --- |
| `crawl_enabled` | `False`이면 실행 대상에서 제외 |
| `priority` | 수집 우선순위. 공식 핵심 데이터는 `P0` |
| `source_group` | discovery로 파생된 URL이 상속할 상위 출처 그룹 |
| `discover_board_candidates` | 정적 페이지 내부 게시판형 URL을 후보로 기록할지 여부 |

게시판 seed는 기존 `crawler/config/seeds.py`를 계속 우선한다. 운영에서 discovery 결과까지 닫힌 루프로 연결하려면 `run_static_discovery --closed-loop-discovery`로 후보를 `crawler_dynamic_seeds`에 저장/승격하고, `run_full_pipeline --closed-loop-discovery`로 promoted seed를 함께 사용한다. 사람이 검토하는 흐름은 그대로 유지할 수 있으며, 승격 대상만 미리 보려면 `run_static_discovery --promote-discovery-results --dry-run-promotion-preview`를 사용한다.

## 첨부파일 파싱 정책

첨부파일은 가능한 경우 `document_assets`에 메타데이터를 저장하고, 검색 가능한 텍스트가 있으면 `document_contents.asset_id`로 연결한다. 운영 전체 파이프라인은 정적 페이지 첨부 다운로드가 기본 활성화되어 있다. 빠른 호환성 검증에서는 `--no-download-attachments`로 끌 수 있다. `run_rag_load_check`는 다음 값을 구분해서 표시한다.

| 항목 | 의미 |
| --- | --- |
| 전체 첨부파일 수 | `document_assets`의 전체 행 수 |
| 파싱 시도 첨부파일 수 | `parser_type`이 기록된 첨부 수 |
| 검색 가능 첨부파일 수 | `document_contents`에 연결된 비어 있지 않은 첨부 텍스트 수 |
| 구형 Office 첨부 수 | `.doc`, `.xls`, `.ppt` 또는 `unsupported_legacy_office`로 분류된 첨부 수 |

구형 Office 바이너리 포맷(`.doc`, `.xls`, `.ppt`)은 현재 안정적으로 파싱된다고 가정하지 않는다. 운영 리포트에서 발견되면 LibreOffice 변환 또는 별도 추출기를 붙이는 작업을 우선 검토한다.

## 실패 재처리

최근 실패 이력은 `crawl_logs`에서 참고할 수 있지만, 운영 복구 절차는 `crawler_retry_queue`를 기준으로 한다. `run_rag_load_check --create-retry-queue`는 데이터 공백을 감지해 bounded retry queue를 생성하고, `run_retry_failed_documents --from-retry-queue`는 이 queue의 대기 항목만 재처리한다.

표준 복구 순서:

1. RAG 적재 상태를 점검하고 누락 항목을 queue로 만든다.
2. queue 대상 dry-run으로 재처리 범위와 `task_type`을 확인한다.
3. 필요한 경우 `--stage`와 `--limit`으로 범위를 좁혀 `--execute`를 실행한다.
4. 재처리 뒤 다시 RAG 적재 상태를 점검한다.
5. `dead_letter`가 남으면 `last_error`, `attempts`, 원본 URL/doc_id를 보고 코드, seed, SSL, 파일 파싱 문제 중 하나로 분류해 별도 조치한다.

```powershell
docker compose run --rm crawler python -m crawler.run.run_rag_load_check --create-retry-queue
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --limit 20
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --limit 20 --execute
docker compose run --rm crawler python -m crawler.run.run_rag_load_check --fail-on-partial
```

단계별로 좁혀 복구할 때는 다음 명령을 사용한다.

```powershell
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --stage vector_ingestion --limit 20
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --stage vector_ingestion --limit 20 --execute
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --stage attachment_download --limit 20 --execute
docker compose run --rm crawler python -m crawler.run.run_retry_failed_documents --from-retry-queue --stage static_page --limit 20 --allow-insecure-ssl --execute
```

`run_rag_load_check --create-retry-queue`는 데이터 공백을 다음 task_type으로 넣는다.

| task_type | 재처리 방식 |
| --- | --- |
| `static_page` | URL과 source_type으로 정적 페이지를 다시 수집/저장, 첨부 다운로드 포함 |
| `board_list` | 게시판 목록 1페이지 단위 재수집 |
| `board_detail` | 게시판 상세 페이지 재수집 |
| `attachment_download` | 첨부 파일 다운로드 재시도 |
| `file_parse` | 다운로드된 첨부 파일 텍스트 추출 재시도 |
| `chunking` | curated JSON에서 chunk 파일 재생성 |
| `vector_ingestion` | 로컬 chunk JSON을 우선 사용하고, 없으면 DB의 `chunks`에서 chunk 파일 복구 후 임베딩 재시도 |

알 수 없는 task_type은 `failed_unknown_task_type`으로 기록된다. 실패가 반복되어 `max_attempts`를 넘으면 `dead_letter` 상태로 남겨 사람이 원인을 본다. `--allow-insecure-ssl`은 SSL 인증서 문제로 실패한 정적 페이지를 재시도할 때만 사용한다.

## Supabase 상태 테이블 / RLS

상태 기반 운영은 `crawler_documents`, `crawler_dynamic_seeds`, `crawler_retry_queue`를 사용한다. 마이그레이션 예시는 `crawler/supabase_migrations/20260514_crawler_state_runtime.sql`에 있으며 idempotent하게 작성되어 있다.

```powershell
docker compose run --rm crawler python -m crawler.ops.supabase_smoke_check --ensure-tables
```

smoke check는 테이블 존재 여부, RLS 활성 여부, insert/select/update/delete 권한을 검증한다. 전제는 crawler 전용 DB connection 또는 service role처럼 서버 측 비공개 연결을 쓰는 것이다. REST/Data API에서 anon/authenticated 역할로 이 테이블을 열 policy는 기본 제공하지 않는다. 공개 API 접근이 필요해질 때만 별도 policy를 검토한다.

## 운영 권장 옵션

| 옵션 | 권장 |
| --- | --- |
| `run_static_discovery --closed-loop-discovery` | discovery 후보를 dynamic seed로 승격할 때 사용 |
| `run_full_pipeline --closed-loop-discovery` | 기존 seed와 promoted dynamic seed를 함께 수집 |
| `run_full_pipeline --download-attachments` | 기본값. 정적 페이지 PDF/HWP 누락 방지 |
| `run_full_pipeline --compress-raw-html` | 운영 저장소 용량 절감을 위해 권장 |
| `run_full_pipeline --raw-json-html-metadata-only` | raw JSON 호환성이 필요한 소비자가 없는 경우에만 사용 |
| `run_rag_load_check --create-retry-queue` | RAG 공백을 bounded retry queue로 생성 |

live 네트워크 검증은 운영자가 명시적으로 실행하는 smoke 경로로만 수행한다. 기본 CI/fixture 테스트에서는 실제 네트워크를 호출하지 않는다.

```powershell
docker compose run --rm crawler python -m crawler.ops.live_fetch_smoke --url https://www.deu.ac.kr --execute-live
```

Live DEU integration smoke는 실제 동의대학교 계열 샘플 URL 4개를 고정해 HTML 추출, 첨부 다운로드,
확장자 보정, 파서 실행, binary marker 차단, noise 제거, chunk 대상 여부를 JSON report로 기록한다.
기본 CI에서는 실행되지 않으며 운영자가 명시적으로 켠다.

```powershell
docker compose run --rm -e CRAWLER_RUN_LIVE_INTEGRATION=1 crawler pytest -m integration
docker compose run --rm crawler python -m crawler.ops.live_deu_integration_smoke --execute-live --report-path reports/live_deu_integration_smoke.json
```

## 테스트

로컬 Python 직접 실행 대신 Docker Compose 환경에서 pytest를 실행한다.

```powershell
docker compose run --rm crawler pytest
```

현재 fixture 테스트는 게시판 목록/상세 extractor, 첨부 라우터, 텍스트 품질, 청킹/파서를 중심으로 구성되어 있다. 신규 크롤러를 추가할 때는 최소한 목록 fixture 1개와 상세 fixture 1개를 테스트에 추가한다.
