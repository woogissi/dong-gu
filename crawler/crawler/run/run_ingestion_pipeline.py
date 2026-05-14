# crawler/run/run_ingestion_pipeline.py

import json
from pathlib import Path

from crawler.ingestion.chunker import DocumentChunker
from crawler.storage.manifest_writer import ManifestWriter
from crawler.paths import CHUNK_DIR, CURATED_DOC_DIR, LOG_DIR, ensure_dirs
from crawler.utils.text_quality import document_quality_report, strip_nul_value


CURATED_DIR = CURATED_DOC_DIR

ensure_dirs(CHUNK_DIR, LOG_DIR)          # chunk 저장 폴더와 로그 폴더를 미리 만들어두는 코드

manifest_writer = ManifestWriter()
chunker = DocumentChunker(max_chars=900, overlap_chars=100)
pgv_loader = None


def get_pgv_loader():
    global pgv_loader
    if pgv_loader is None:
        from crawler.ingestion.pgvector_loader import PGVectorLoader

        pgv_loader = PGVectorLoader()
    return pgv_loader


def load_json(path: Path) -> dict:          # curated 문서 파일 하나를 dict로 읽어온다
    with open(path, "r", encoding="utf-8") as f:
        return strip_nul_value(json.load(f))


def save_json(path: Path, data: dict | list) -> None:       # chunk 리스트를 JSON으로 저장
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_error(message: str) -> None:        # 에러를 콘솔과 로그 파일에 동시에 남기는 함수
    print(message)
    with open(LOG_DIR / "ingestion_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def record_ingestion_error_to_db(
    error: Exception,
    path: Path,
    source_type: str | None,
    doc_id: str | None,
) -> None:
    try:
        get_pgv_loader().insert_crawl_job_error(
            run_type="ingestion_pipeline",
            stage="chunking",
            error=error,
            source_type=source_type,
            doc_id=doc_id,
            file_path=path.as_posix(),
            context={
                "curated_file": path.as_posix(),
            },
        )
    except Exception as logging_error:
        log_error(
            "[INGEST ERROR LOGGING FAILED] "
            f"file={path.as_posix()} error={logging_error}"
        )


def collect_curated_documents() -> list[Path]:      # chunking 대상이 될 curated 문서 파일들을 전부 모으는 함수
    doc_paths = []
    if not CURATED_DIR.exists():
        return doc_paths

    for source_type_dir in CURATED_DIR.iterdir():   # curated/documents 하위 폴더 탐색
        if not source_type_dir.is_dir():
            continue

        for file_path in source_type_dir.glob("*.json"):        # 각 source_type 폴더 안의 JSON 문서 탐색
            doc_paths.append(file_path)

    return sorted(doc_paths)        # 파일 경로를 정렬


def save_chunks(source_type: str, doc_id: str, chunks: list[dict]) -> None:     # chunk 리스트를 파일로 저장하는 함수
    chunk_path = CHUNK_DIR / source_type / f"{doc_id}.json"
    save_json(chunk_path, chunks)


def run_ingestion():                # 전체 ingestion 파이프라인 함수
    doc_paths = collect_curated_documents()         # chunking할 curated 문서 파일들을 모으고, 몇 개인지 출력
    print(f"[INFO] curated documents found: {len(doc_paths)}")

    for path in doc_paths:
        source_type = None
        doc_id = None
        try:
            doc = load_json(path)
            source_type = doc.get("source_type", "unknown")
            doc_id = doc["doc_id"]

            body = doc.get("normalize", "")
            attachment = doc.get("attachment_text", "")
            image = doc.get("image_text", "")

            has_body = body and body.strip()
            has_attachment = attachment and attachment.strip()
            has_image = image and image.strip()

            if not (has_body or has_attachment or has_image):
                manifest_writer.append_jsonl("chunking.jsonl", {
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "version": doc.get("version"),
                    "chunk_count": 0,
                    "source_url": doc.get("source_url"),
                    "status": "skipped",
                    "reason": "본문/첨부/이미지 텍스트 없음",
                })

                print(f"[INGEST SKIP] {doc_id} → 본문/첨부/이미지 없음")
                continue

            quality = document_quality_report(doc)
            if quality["is_binary_like"]:
                manifest_writer.append_jsonl("chunking.jsonl", {
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "version": doc.get("version"),
                    "chunk_count": 0,
                    "source_url": doc.get("source_url"),
                    "status": "skipped",
                    "reason": "binary_like_text",
                    "quality": quality,
                })
                print(f"[INGEST SKIP] {doc_id} binary_like_text fields={quality['bad_fields']}")
                continue

            chunks = chunker.chunk_document(doc)  # list로 청크 결과 받기
            save_chunks(source_type, doc_id, chunks)        # 결과 저장

            manifest_writer.append_jsonl("chunking.jsonl", {
                "doc_id": doc_id,
                "source_type": source_type,
                "version": doc["version"],
                "chunk_count": len(chunks),
                "source_url": doc.get("source_url"),
            })

            print(f"[INGEST OK] {doc_id} version={doc['version']} chunks={len(chunks)}")

        except Exception as e:
            message = f"[INGEST ERROR] file={path.as_posix()} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="ingestion",
                message=message,
                extra={"file_path": path.as_posix()},
            )
            record_ingestion_error_to_db(e, path, source_type, doc_id)


if __name__ == "__main__":
    run_ingestion()
