from __future__ import annotations

import argparse
import os
import re
from urllib.parse import urlparse

from crawler.paths import CURATED_DOC_DIR, HF_CACHE_DIR

os.environ.setdefault("HF_HOME", str(HF_CACHE_DIR.resolve()))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str((HF_CACHE_DIR / "hub").resolve()))

from crawler.config.seeds import iter_enabled_seeds
from crawler.discovery.url_classifier import URLClassifier


PROFESSOR_PATH_RE = re.compile(r"/[^/?]+/sub02(?:_\d+)?\.do$")
CURRICULUM_PATH_RE = re.compile(r"/[^/?]+/sub03(?:_\d+)?\.do$")


def normalize_url(url: str) -> str:
    return url.strip().split("#", 1)[0]


def is_library_url(url: str) -> bool:
    return urlparse(url).netloc.lower() == "lib.deu.ac.kr"


def is_professor_list_url(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith(".deu.ac.kr"):
        return False
    if parsed.query:
        return False
    return bool(PROFESSOR_PATH_RE.search(parsed.path))


def is_curriculum_url(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith(".deu.ac.kr"):
        return False
    if parsed.query:
        return False
    return bool(CURRICULUM_PATH_RE.search(parsed.path))


def source_type_for_url(url: str, seed_source_type: str | None = None) -> str:
    if is_library_url(url):
        return "library"
    if seed_source_type:
        return seed_source_type
    return URLClassifier().infer_source_type(url)


def collect_profile_targets(profile: str) -> list[tuple[str, str]]:
    targets: dict[str, str] = {}
    for seed in iter_enabled_seeds():
        url = normalize_url(seed["url"])
        if not url:
            continue
        source_type = source_type_for_url(url, seed.get("source_type"))
        if profile in {"library", "library-professors"} and is_library_url(url):
            targets[url] = "library"
        if (
            profile in {"professors", "library-professors"}
            and source_type == "department"
            and is_professor_list_url(url)
        ):
            targets[url] = source_type
        if profile == "curriculum" and is_curriculum_url(url):
            targets[url] = source_type or "department"
    return sorted(targets.items())


def download_attachment_texts(raw_doc: dict, timeout: int = 30) -> str | None:
    """첨부파일을 다운로드하고 텍스트를 추출해 반환합니다."""
    from crawler.extractors.attachment_downloader import AttachmentDownloader
    from crawler.parsers.file_text_router import FileTextRouter

    attachments = raw_doc.get("attachments") or []
    if not attachments:
        return None

    downloader = AttachmentDownloader(timeout=timeout)
    router = FileTextRouter()
    texts = []
    for att in attachments:
        file_url = att.get("file_url")
        if not file_url:
            continue
        try:
            downloaded = downloader.download(raw_doc["source_type"], raw_doc["doc_id"], att)
            if not downloaded:
                continue
            saved_path = downloaded.get("saved_path")
            if not saved_path:
                continue
            result = router.extract_text(saved_path)
            text = result.get("attachment_text") or ""
            if text.strip():
                fname = att.get("file_name") or file_url.split("/")[-1]
                texts.append(f"[ATTACHMENT: {fname}]\n{text.strip()}")
                print(f"[ATTACH OK] doc_id={raw_doc['doc_id']} file={fname} text_len={len(text)}", flush=True)
        except Exception as exc:
            print(f"[ATTACH ERR] doc_id={raw_doc['doc_id']} url={file_url} err={exc}", flush=True)

    return "\n\n".join(texts) if texts else None


def ingest_targets(
    targets: list[tuple[str, str]],
    *,
    allow_insecure_ssl: bool,
    skip_vector: bool,
    limit: int | None,
    download_attachments: bool = False,
) -> None:
    from crawler.extractors.static_page_extractor import StaticPageExtractor
    from crawler.ingestion.chunker import DocumentChunker
    from crawler.run.run_single_file_pipeline import chunk_curated_file, vector_ingest_chunk_file
    from crawler.run.run_static_discovery import save_static_document

    if allow_insecure_ssl:
        os.environ["CRAWLER_ALLOW_INSECURE_SSL"] = "1"

    extractor = StaticPageExtractor()
    chunker = DocumentChunker(max_chars=900, overlap_chars=100)
    embed_worker = None
    loader = None
    if not skip_vector:
        from crawler.ingestion.embed_worker import EmbeddingWorker
        from crawler.ingestion.pgvector_loader import PGVectorLoader

        embed_worker = EmbeddingWorker()
        loader = PGVectorLoader(autocommit_writes=False)
        loader.ensure_tables()

    processed = 0
    failed = 0

    try:
        for url, source_type in targets[: limit or None]:
            try:
                print(f"[TARGET START] source={source_type} url={url}", flush=True)
                raw_doc = extractor.extract_static_page(source_type=source_type, page_url=url)

                if download_attachments:
                    att_text = download_attachment_texts(raw_doc)
                    if att_text:
                        raw_doc["attachment_text"] = att_text

                save_static_document(raw_doc)

                curated_file = CURATED_DOC_DIR / raw_doc["source_type"] / f"{raw_doc['doc_id']}.json"
                chunk_file = chunk_curated_file(curated_file, chunker=chunker)
                if chunk_file and not skip_vector:
                    vector_ingest_chunk_file(chunk_file, embed_worker=embed_worker, loader=loader)
                    loader.commit()

                processed += 1
                att_len = len(raw_doc.get("attachment_text") or "")
                print(
                    f"[TARGET OK] doc_id={raw_doc['doc_id']} "
                    f"title={raw_doc.get('title')} text_len={len(raw_doc.get('raw_text') or '')} att_len={att_len}",
                    flush=True,
                )
            except Exception as exc:
                failed += 1
                if loader:
                    loader.rollback()
                print(f"[TARGET ERROR] url={url} error={type(exc).__name__}: {exc}", flush=True)
    finally:
        if loader:
            loader.close()

    print(f"[DONE] processed={processed} failed={failed} selected={len(targets[: limit or None])}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Targeted static-page extraction/chunking/vector ingestion for known corpus gaps."
    )
    parser.add_argument(
        "--profile",
        choices=["library", "professors", "library-professors", "curriculum"],
        default="library-professors",
        help="Seed-derived target group to ingest.",
    )
    parser.add_argument("--url", action="append", default=[], help="Additional URL to ingest.")
    parser.add_argument("--source-type", help="Source type for --url values. Defaults to URL inference.")
    parser.add_argument("--allow-insecure-ssl", action="store_true", help="Enable lib.deu.ac.kr legacy TLS fallback.")
    parser.add_argument("--skip-vector", action="store_true", help="Only extract and chunk; do not upsert vectors.")
    parser.add_argument("--limit", type=int, help="Process at most N targets.")
    parser.add_argument("--download-attachments", action="store_true", help="PDF/HWP 첨부파일을 다운로드해 텍스트 추출합니다.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected targets without ingesting.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    targets = collect_profile_targets(args.profile)

    for url in args.url:
        normalized = normalize_url(url)
        if normalized:
            targets.append((normalized, source_type_for_url(normalized, args.source_type)))

    deduped = sorted(dict(targets).items())
    selected = deduped[: args.limit or None]

    if args.dry_run:
        print(f"[DRY RUN] targets={len(deduped)} selected={len(selected)}")
        for url, source_type in selected:
            print(f"{source_type}\t{url}")
        return

    download_attachments = args.download_attachments or (args.profile == "curriculum")
    ingest_targets(
        deduped,
        allow_insecure_ssl=args.allow_insecure_ssl,
        skip_vector=args.skip_vector,
        limit=args.limit,
        download_attachments=download_attachments,
    )


if __name__ == "__main__":
    main()
