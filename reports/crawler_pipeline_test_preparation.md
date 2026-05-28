# Crawler Pipeline Test Preparation

Date: 2026-05-20

## Current Data Snapshot

- Local crawler artifact directories under `crawler/crawler/data` are currently empty.
- `.env` `DATABASE_URL` was used through the crawler container and connected to the Supabase Postgres database.
- Supabase table counts at inspection time:
  - `documents`: 3,235
  - `chunks`: 13,527
  - `document_assets`: 10,373
  - `document_contents`: 8,557
- Document coverage checks:
  - documents without chunks: 0
  - documents without contents: 0
- Document page kinds:
  - `static_page`: 2,575
  - `board_detail`: 660
- Chunk length risk buckets:
  - chunks shorter than 50 chars: 0
  - chunks from 50 to 120 chars: 348
  - chunks longer than 2,000 chars: 0
- Attachment extension pattern:
  - `.pdf`: 430
  - `.hwp`: 350
  - `.jpg`: 134
  - missing extension: 107
  - `.xlsx`: 27
  - `.zip`: 23
  - `.hwpx`: 20
- Quality risk signals:
  - attachment assets without extracted text content: 168
  - duplicate chunk hash groups: 599
  - chunk sections marked truncated: 0
  - escaped NUL contents: 0
  - replacement-character contents: 0
  - blank contents: 0
  - contents containing `%PDF` marker: 99

## Seed Pattern Summary

- Enabled seed count: 422
- Page kinds: `static_page` 394, `board_list` 28
- Priorities: `P0` 5, `P1` 42, `P2` 370, `P3` 5
- Top hosts: `www.deu.ac.kr` 101, `deuhome.deu.ac.kr` 71, `ipsi.deu.ac.kr` 28, `dorm.deu.ac.kr` 27, `ctl.deu.ac.kr` 14
- Direct download-like seed count: 12
- Duplicate enabled URLs found: 0

## Pipeline Test Plan

1. Seed loading: validate required fields, stable seed names, duplicate URL absence, board-list/download separation.
2. Fetch: keep network checks as smoke/manual tests; unit tests should mock `fetch_result`.
3. Link discovery: assert `.do?mode=view` and social links are not treated as attachments; assert download links are retained.
4. Static extraction: assert main-page UI preview blocks are removed while real intro/body sections remain.
5. Board list/detail: assert list pagination normalization, title/date hints, detail document IDs, metadata, and attachments.
6. Attachment download/parse: assert dynamic download routes infer extension from headers/name, retry partial streams, and preserve hash/parser metadata.
7. Normalization: assert NUL/binary-like text is rejected before chunking.
8. Chunking: assert body/table/attachment/image sections remain separate, small UI stubs are skipped, meaningful short contact/date chunks are kept.
9. DB/pgvector: assert chunk `content_id` maps to clean/table/attachment content and attachment hash wins over URL/name.
10. Final RAG validation: run SQL audits after crawl for empty documents, short chunks, duplicate hashes, binary markers, attachment parse failures, and high truncation counts.

## RAG Quality Risks

- Empty or near-empty documents creating useless chunks.
- Header/footer/menu/preview UI text dominating static pages.
- Board metadata such as previous/next/list labels leaking into body text.
- Download routes saved with `.do` or query-string names instead of real file extensions.
- Duplicate attachments from repeated labels or mirrored URLs.
- Attachment records present but no extracted text.
- Binary/PDF/HWP raw bytes entering `raw_text`, `normalize`, or `attachment_text`.
- Very long attachment sections truncated by chunk limits before meaningful headings/tables are split.
- Department home pages over-discovering sibling department links.
- Direct download seeds mixed into board-list flow.
- Supabase data currently has 168 attachment assets without extracted text content, concentrated in missing-extension assets and PDF files.
- Supabase data currently has 99 stored content rows containing a `%PDF` marker, including `raw`, `clean`, `table`, and `attachment` rows. These should be sampled because binary-like PDF bytes can poison retrieval.
- Duplicate chunk hashes include repeated menu/share/SNS-heavy snippets from fund, lifelong, dormitory, advising, and admission sources.

## Added Automated Tests

- `crawler/tests/test_discovery_policy.py`
  - Validates enabled seed identity, required fields, URL uniqueness, and board-list/download separation.
- `crawler/tests/test_pipeline_quality_contract.py`
  - Validates raw-to-curated attachment text/metadata preservation.
  - Validates curated-to-chunk separation of body and attachment RAG units.
  - Validates downloaded attachment dedupe by content hash.

## Manual Verification Checklist

- Pick one P0 board notice with an attachment and compare title, date, department, body, and attachment URLs against the live page.
- Pick one static main page and confirm preview UI, carousel controls, login/signup, SNS, and footer text are absent from `raw_text`.
- Pick one department curriculum page with a PDF/HWP download and confirm attachment text/table rows appear as attachment chunks.
- Pick one admission guide PDF/HWP pair and confirm both are either deduped intentionally or represented with distinct hashes.
- After a crawl, run SQL audits for:
  - documents with no `document_contents`
  - chunks shorter than 50 characters
  - repeated `content_hash` values
  - assets with no extracted text
  - `metadata->'section_truncated' = true`
  - NUL/replacement/binary marker patterns in stored content

## Commands Run

- `docker compose ps`
- `docker compose exec postgres psql -U chatbot -d chatbot -c "...table counts..."`
- `docker compose exec crawler python -c "...seed summary..."`
- `docker compose exec crawler python -m unittest discover -s tests -p "test_discovery_policy.py"`: 11 tests passed
- `docker compose exec crawler python -m unittest discover -s tests -p "test_pipeline_quality_contract.py"`: 3 tests passed
- `docker compose exec crawler python -m unittest discover -s tests -p "test_*.py"`: 98 tests passed
- Re-ran Supabase-backed checks using `.env` `DATABASE_URL`; crawler tests still passed: 98 tests passed
