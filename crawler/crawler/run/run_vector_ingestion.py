# crawler/run/run_vector_ingestion.py

import os
from pathlib import Path

os.environ.setdefault("HF_HOME", str(Path("crawler/.hf_cache").resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(Path("crawler/.hf_cache/hub").resolve()))

import json


from crawler.ingestion.embed_worker import EmbeddingWorker
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.storage.manifest_writer import ManifestWriter

RAW_DIR = Path("crawler/data/raw/documents")
CURATED_DIR = Path("crawler/data/curated/documents")
CHUNK_DIR = Path("crawler/data/rag_ready/chunks")
LOG_DIR = Path("crawler/data/logs")

LOG_DIR.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()


def load_json(path: Path):          # chunk JSON 파일을 읽는 함수
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "vector_ingestion_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def collect_chunk_files() -> list[Path]:        # vector ingestion 대상이 되는 chunk 파일들을 전부 모으는 함수
    paths = []
    if not CHUNK_DIR.exists():
        return paths

    for source_type_dir in CHUNK_DIR.iterdir():     # CHUNK_DIR = rag_ready/chunks 아래의 하위 폴더들을 순회
        if not source_type_dir.is_dir():
            continue

        for file_path in source_type_dir.glob("*.json"):    # 각 폴더 안에 JSON파일 탐색
            paths.append(file_path)

    return sorted(paths)


def main():     # 메인 함수
    chunk_files = collect_chunk_files()     # 현재 적재할 chunk 파일이 몇 개인지 확인
    print(f"[INFO] chunk files found: {len(chunk_files)}")

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader()
    loader.ensure_tables()

    try:
        for chunk_file in chunk_files:      # chunk 파일 하나씩
            try:
                chunks = load_json(chunk_file)      # chunk 파일을 리스트로 들고옴
                if not chunks:
                    continue
                
                source_type = chunks[0]["source_type"]
                doc_id = chunks[0]["doc_id"]

                curated_path = CURATED_DIR / source_type / f"{doc_id}.json"
                raw_path = RAW_DIR / source_type / f"{doc_id}.json"

                if not curated_path.exists():
                    raise FileNotFoundError(f"curated document not found: {curated_path}")

                curated_doc = load_json(curated_path)

                raw_doc = {}
                if raw_path.exists():
                    raw_doc = load_json(raw_path)

                version = curated_doc.get("version", 1)

                loader.upsert_document(curated_doc)

                change_type = curated_doc.get("change_type") or curated_doc.get("decision", "unknown")
                if change_type in ("new", "updated"):
                    loader.insert_document_version(curated_doc, change_type)

                # raw_doc에만 downloaded_attachments, image_texts가 있으므로 합쳐서 assets 저장
                asset_source_doc = {
                    **curated_doc,
                    "downloaded_attachments": raw_doc.get("downloaded_attachments", []),
                    "image_texts": raw_doc.get("image_texts", []),
                }

                loader.upsert_assets(asset_source_doc)      # 첨부 assets DB 저장

                loader.upsert_chunks(chunks, version)   # chunk 메타를 DB 저장

                embedded_chunks = embed_worker.embed_chunks(chunks) # 임베딩 생성
                loader.upsert_embeddings(embedded_chunks)           # 임베딩 벡터를 DB에 저장    

                manifest_writer.append_jsonl("vector_ingestion.jsonl", {
                    "chunk_file": chunk_file.as_posix(),
                    "source_type": source_type,
                    "doc_id": doc_id,
                    "chunk_count": len(chunks),
                    "embedding_model": embedded_chunks[0].get("embedding_model") if embedded_chunks else None,
                })

                print(
                    f"[VECTOR OK] doc_id={chunks[0].get('doc_id')} "
                    f"chunks={len(chunks)}"
                )

            except Exception as e:      # 실패 시 다음 파일로 
                loader.conn.rollback()

                message = f"[VECTOR ERROR] file={chunk_file.as_posix()} error={e}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="vector_ingestion",
                    message=message,
                    extra={"file_path": chunk_file.as_posix()},
                )

    finally:
        loader.close()


if __name__ == "__main__":
    main()
