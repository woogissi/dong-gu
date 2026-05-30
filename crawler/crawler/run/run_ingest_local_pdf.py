"""로컬 PDF 파일을 파싱하여 DB에 청크 적재 및 임베딩을 수행합니다.

사용 예:
    docker compose run --rm crawler python -m crawler.run.run_ingest_local_pdf \
        --pdf /app/파일명.pdf \
        --title "교육과정 편성 및 이수 규정" \
        --source-url "https://www.deu.ac.kr/regulation/curriculum" \
        --source-type regulation
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from crawler.paths import CURATED_DOC_DIR, HF_CACHE_DIR

os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR.resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str((HF_CACHE_DIR / "hub").resolve()))


def _doc_id_from_url(source_url: str) -> str:
    return "local_" + hashlib.sha1(source_url.encode()).hexdigest()[:16]


def _build_curated_doc(
    *,
    doc_id: str,
    title: str,
    source_url: str,
    source_type: str,
    full_text: str,
    page_count: int,
    pdf_path: str,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    content_hash = hashlib.sha256(full_text.encode()).hexdigest()
    return {
        "doc_id": doc_id,
        "source_type": source_type,
        "page_kind": "static",
        "department": None,
        "title": title,
        "source_url": source_url,
        "published_at": None,
        "updated_at": None,
        "raw_text": None,
        "normalize": full_text,
        "table_text": None,
        "attachment_text": None,
        "image_text": None,
        "structured_sections": [],
        "version": 1,
        "change_type": "new",
        "collected_at": now,
        "content_hash": content_hash,
        "metadata": {
            "pdf_path": pdf_path,
            "page_count": page_count,
            "ingested_from": "local_pdf",
        },
    }


def parse_pdf(pdf_path: str, force_ocr: bool = False) -> tuple[str, int]:
    """PDFParser로 전체 텍스트 추출. 실패 시 예외 전파.

    force_ocr=True 이면 텍스트 레이어 유무와 관계없이 전 페이지 OCR을 수행합니다.
    한국어 PDF에서 텍스트 레이어가 공백 없이 추출되는 경우에 사용합니다.
    """
    from crawler.parsers.pdf_parser import PDFParser
    import fitz

    if force_ocr:
        # 전 페이지 OCR: 텍스트 레이어를 무시하고 이미지 → OCR 방식으로 추출
        from crawler.ocr.korean_ocr import KoreanOCREngine
        import io
        from PIL import Image

        doc = fitz.open(pdf_path)
        ocr = KoreanOCREngine()
        parts = []
        page_count = len(doc)
        for page_index in range(page_count):
            page = doc.load_page(page_index)
            matrix = fitz.Matrix(2.5, 2.5)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            result = ocr.extract_text_from_image(img)
            text = result.text.strip() if result.text else ""
            if text:
                parts.append(text)
            print(f"[OCR] page {page_index+1}/{page_count} text_len={len(text)}", flush=True)
        doc.close()
        full_text = "\n\n".join(parts)
        print(f"[PDF PARSE OCR] pages={page_count} text_len={len(full_text)}")
        return full_text, page_count

    parser = PDFParser(skip_ocr=False, ocr_max_pages=10)
    result = parser.extract_text(pdf_path)
    text = result.get("text") or ""
    page_count = result.get("page_count", 0)

    print(f"[PDF PARSE] pages={page_count} text_len={len(text)} note={result.get('note','')}")
    return text, page_count


def ingest(
    *,
    pdf_path: str,
    title: str,
    source_url: str,
    source_type: str,
    skip_vector: bool,
    force_ocr: bool = False,
) -> None:
    from crawler.ingestion.chunker import DocumentChunker
    from crawler.run.run_single_file_pipeline import (
        chunk_curated_file,
        save_json,
        vector_ingest_chunk_file,
    )

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")

    print(f"[PDF] 파싱 시작: {path.name} (force_ocr={force_ocr})")
    full_text, page_count = parse_pdf(pdf_path, force_ocr=force_ocr)

    if not full_text.strip():
        raise ValueError("PDF에서 텍스트를 추출하지 못했습니다. OCR 설정을 확인하세요.")

    doc_id = _doc_id_from_url(source_url)
    curated_doc = _build_curated_doc(
        doc_id=doc_id,
        title=title,
        source_url=source_url,
        source_type=source_type,
        full_text=full_text,
        page_count=page_count,
        pdf_path=str(path),
    )

    curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"
    curated_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(curated_path, curated_doc)
    print(f"[CURATED] 저장: {curated_path}")

    chunker = DocumentChunker(max_chars=900, overlap_chars=100)
    chunk_file = chunk_curated_file(curated_path, chunker=chunker)

    if chunk_file is None:
        print("[WARN] 청크 생성 실패 또는 내용 없음.")
        return

    if skip_vector:
        print(f"[SKIP VECTOR] chunk_file={chunk_file}")
        return

    from crawler.ingestion.embed_worker import EmbeddingWorker
    from crawler.ingestion.pgvector_loader import PGVectorLoader

    embed_worker = EmbeddingWorker()
    loader = PGVectorLoader(autocommit_writes=False)
    loader.ensure_tables()
    try:
        vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
        loader.commit()
        print(f"[DONE] doc_id={doc_id} source_type={source_type} title={title}")
    except Exception:
        loader.rollback()
        raise
    finally:
        loader.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 PDF 파일을 파싱하여 DB에 적재합니다.")
    parser.add_argument("--pdf", required=True, help="컨테이너 내 PDF 파일 경로 (예: /app/파일명.pdf)")
    parser.add_argument("--title", required=True, help="문서 제목")
    parser.add_argument(
        "--source-url",
        required=True,
        help="문서의 원본 URL 또는 고유 식별자 (예: https://www.deu.ac.kr/reg/curriculum)",
    )
    parser.add_argument(
        "--source-type",
        default="regulation",
        help="문서 종류 (기본값: regulation)",
    )
    parser.add_argument(
        "--skip-vector",
        action="store_true",
        help="청크 생성만 하고 임베딩/DB 적재는 건너뜁니다.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="텍스트 레이어를 무시하고 전 페이지 OCR을 수행합니다. 한국어 PDF에서 공백 없이 추출될 때 사용합니다.",
    )
    args = parser.parse_args()

    ingest(
        pdf_path=args.pdf,
        title=args.title,
        source_url=args.source_url,
        source_type=args.source_type,
        skip_vector=args.skip_vector,
        force_ocr=args.force_ocr,
    )


if __name__ == "__main__":
    main()
