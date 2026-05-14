# crawler/run/run_full_pipeline.py

import argparse
import json
import os
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.utils.content_hash import build_content_hash
from crawler.config.seeds import iter_enabled_seeds
from crawler.config.domains import ALLOWED_HOSTS
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.storage.manifest_writer import ManifestWriter
from crawler.storage.document_store import DocumentStore
from crawler.schemas.document_models import CuratedDocument
from crawler.ingestion.document_version_manager import DocumentVersionManager
from crawler.normalize.text_cleaner import TextCleaner
from crawler.state.crawler_state_store import CrawlerStateStore
from crawler.paths import (
    CURATED_DOC_DIR,
    DATA_DIR,
    LOG_DIR,
    MANIFEST_DIR,
    RAW_ATTACH_DIR,
    RAW_DOC_DIR,
    RAW_HTML_DIR,
    ensure_dirs,
)

BASE_DIR = DATA_DIR

ensure_dirs(RAW_HTML_DIR, RAW_DOC_DIR, RAW_ATTACH_DIR, CURATED_DOC_DIR, LOG_DIR)

text_cleaner = TextCleaner()
manifest_writer = ManifestWriter()
document_store = DocumentStore()
version_manager = DocumentVersionManager(curated_base_dir=str(CURATED_DOC_DIR))
pgv_loader = None
RUNTIME = {
    "enable_image_ocr": False,
    "timeout": (5, 30),
    "sleep_seconds": 0.0,
    "download_static_attachments": True,
}


def get_pgv_loader():
    global pgv_loader
    if pgv_loader is None:
        from crawler.ingestion.pgvector_loader import PGVectorLoader

        pgv_loader = PGVectorLoader()
    return pgv_loader


def record_crawl_job_error(**kwargs) -> None:
    try:
        get_pgv_loader().insert_crawl_job_error(**kwargs)
    except Exception as exc:
        log_error(f"[CRAWL JOB LOG ERROR] stage={kwargs.get('stage')} error={exc}")


def enqueue_retry_queue_error(
    *,
    task_type: str,
    reason: str,
    doc_id: str | None = None,
    url: str | None = None,
    source_type: str | None = None,
    page_kind: str | None = None,
    file_path: str | None = None,
    payload: dict | None = None,
) -> None:
    try:
        state_store = CrawlerStateStore()
        try:
            state_store.ensure_tables()
            state_store.enqueue_retry(
                stage=task_type,
                task_type=task_type,
                reason=reason,
                doc_id=doc_id,
                url=url,
                source_type=source_type,
                page_kind=page_kind,
                file_path=file_path,
                context=payload or {},
                payload=payload or {},
            )
        finally:
            state_store.close()
    except Exception as exc:
        log_error(f"[RETRY QUEUE ERROR] task_type={task_type} doc_id={doc_id} url={url} error={exc}")


def record_document_state(**kwargs) -> None:
    try:
        state_store = CrawlerStateStore()
        try:
            state_store.ensure_tables()
            state_store.upsert_document_state(**kwargs)
        finally:
            state_store.close()
    except Exception as exc:
        log_error(f"[STATE WRITE ERROR] url={kwargs.get('url')} status={kwargs.get('status')} error={exc}")

def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "crawl_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def existing_raw_document(source_type: str, doc_id: str) -> dict | None:
    path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    if not path.exists():
        return None
    try:
        data = load_json(path)
        return data if isinstance(data, dict) else None
    except Exception as exc:
        log_error(f"[RAW CACHE READ ERROR] doc_id={doc_id} path={path.as_posix()} error={exc}")
        return None


def reusable_attachment(existing_raw: dict | None, file_url: str) -> dict | None:
    if not existing_raw:
        return None
    for item in existing_raw.get("downloaded_attachments", []) or []:
        if item.get("file_url") != file_url:
            continue
        saved_path = item.get("saved_path")
        if saved_path and Path(saved_path).exists() and item.get("attachment_text") is not None:
            return item
    return None


def merge_attachment_texts(downloaded_attachments: list[dict]) -> str | None:
    texts = []

    for item in downloaded_attachments:
        attachment_text = item.get("attachment_text")
        file_name = item.get("file_name")
        if attachment_text:
            texts.append(f"[ATTACHMENT: {file_name}]\n{attachment_text}")

    merged = "\n\n".join(texts).strip()
    return merged if merged else None


def merge_image_texts(image_texts: list[dict]) -> str | None:
    texts = []

    for item in image_texts or []:
        image_text = item.get("image_text")
        image_url = item.get("image_url")
        if image_text:
            texts.append(f"[IMAGE: {image_url}]\n{image_text}")

    merged = "\n\n".join(texts).strip()
    return merged if merged else None


def build_curated_document(raw_doc: dict, version: int) -> dict:
    attachment_text = merge_attachment_texts(raw_doc.get("downloaded_attachments", []))
    image_text = merge_image_texts(raw_doc.get("image_texts", []))

    curated_doc = CuratedDocument(
        doc_id=raw_doc["doc_id"],
        source_type=raw_doc["source_type"],
        page_kind=raw_doc["page_kind"],
        department=raw_doc["department"],
        title=raw_doc["title"],
        source_url=raw_doc["source_url"],
        published_at=raw_doc["published_at"],
        updated_at=raw_doc["updated_at"],
        raw_text=raw_doc["raw_text"],
        normalize=text_cleaner.build_clean_text(
            raw_text=raw_doc.get("raw_text", ""),
            table_text=raw_doc.get("table_text"),
        ),
        table_text=raw_doc["table_text"],
        attachment_text=attachment_text,
        image_text=image_text,
        version=version,
        collected_at=raw_doc["collected_at"],
        content_hash=raw_doc["content_hash"],
    )

    return curated_doc.model_dump()


def save_document_bundle(raw_doc: dict, download_attachments: bool = False) -> None:
    source_type = raw_doc["source_type"]
    doc_id = raw_doc["doc_id"]

    raw_to_save, raw_path, _html_path = document_store.prepare_raw_document(raw_doc)

    existing_raw = existing_raw_document(source_type, doc_id)
    existing_curated = version_manager.load_existing_document(source_type, doc_id)
    image_text = merge_image_texts(raw_to_save.get("image_texts", []))
    unchanged_without_attachment_work = (
        download_attachments
        and existing_raw is not None
        and existing_curated is not None
        and existing_curated.get("raw_text") == raw_to_save.get("raw_text")
        and existing_curated.get("table_text") == raw_to_save.get("table_text")
        and existing_curated.get("image_text") == image_text
    )

    downloaded_attachments = []
    if unchanged_without_attachment_work:
        downloaded_attachments = existing_raw.get("downloaded_attachments", []) or []
        raw_to_save["attachments"] = existing_raw.get("attachments", raw_to_save.get("attachments", []))
        print(f"[ATTACH SKIP] doc_id={doc_id} reason=unchanged_document reused={len(downloaded_attachments)}")
    elif download_attachments and raw_to_save.get("attachments"):
        from crawler.extractors.attachment_downloader import AttachmentDownloader
        from crawler.parsers.file_text_router import FileTextRouter

        downloader = AttachmentDownloader(timeout=RUNTIME["timeout"])
        file_router = FileTextRouter()

        for att in raw_to_save["attachments"]:
            cached = reusable_attachment(existing_raw, att.get("file_url"))
            if cached:
                downloaded_attachments.append(cached)
                print(f"[ATTACH CACHE HIT] doc_id={doc_id} file_url={att.get('file_url')}")
                continue

            try:
                downloaded = downloader.download(source_type, doc_id, att)

            except Exception as e:
                message = f"[ATTACH DOWNLOAD ERROR] doc_id={doc_id} file_url={att['file_url']} error={e}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="attachment_download",
                    message=message,
                    extra={"doc_id": doc_id, "file_url": att["file_url"]},
                )
                record_crawl_job_error(
                    run_type="full_pipeline",
                    stage="attachment_download",
                    error=e,
                    source_type=source_type,
                    doc_id=doc_id,
                    url=raw_to_save.get("source_url"),
                    file_url=att.get("file_url"),
                    context={
                        "file_name": att.get("file_name"),
                        "attachment_index": att.get("attachment_index"),
                    },
                )
                enqueue_retry_queue_error(
                    task_type="attachment_download",
                    reason="download_failed",
                    doc_id=doc_id,
                    url=att.get("file_url") or raw_to_save.get("source_url"),
                    source_type=source_type,
                    page_kind=raw_to_save.get("page_kind"),
                    payload={
                        "file_url": att.get("file_url"),
                        "file_name": att.get("file_name"),
                        "attachment_index": att.get("attachment_index"),
                        "source_url": raw_to_save.get("source_url"),
                    },
                )
                continue


            try:    
                parse_result = file_router.extract_text(downloaded["saved_path"])
                downloaded["parser_type"] = parse_result.get("parser_type")
                downloaded["attachment_text"] = parse_result.get("attachment_text")
                downloaded["page_count"] = parse_result.get("page_count")
                downloaded["pages"] = parse_result.get("pages")
                downloaded["note"] = parse_result.get("note")
                downloaded["raw_xml_files"] = parse_result.get("raw_xml_files", [])

                downloaded_attachments.append(downloaded)
                manifest_writer.write_file_parse_record(doc_id, downloaded, parse_result)

            except Exception as e:
                message = f"[PARSE ERROR] doc_id={doc_id} file_url={att['file_url']} error={e}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="parse",
                    message=message,
                    extra={"doc_id": doc_id, "file_url": att["file_url"]},
                )
                record_crawl_job_error(
                    run_type="full_pipeline",
                    stage="file_parse",
                    error=e,
                    source_type=source_type,
                    doc_id=doc_id,
                    url=raw_to_save.get("source_url"),
                    file_url=downloaded.get("file_url"),
                    file_path=downloaded.get("saved_path"),
                    context={
                        "file_name": downloaded.get("file_name"),
                        "file_ext": downloaded.get("file_ext"),
                        "file_size": downloaded.get("file_size"),
                        "attachment_index": downloaded.get("attachment_index"),
                    },
                )
                enqueue_retry_queue_error(
                    task_type="file_parse",
                    reason="parse_failed",
                    doc_id=doc_id,
                    url=downloaded.get("file_url") or raw_to_save.get("source_url"),
                    source_type=source_type,
                    page_kind=raw_to_save.get("page_kind"),
                    file_path=downloaded.get("saved_path"),
                    payload={
                        "file_url": downloaded.get("file_url"),
                        "file_name": downloaded.get("file_name"),
                        "file_ext": downloaded.get("file_ext"),
                        "attachment_index": downloaded.get("attachment_index"),
                        "saved_path": downloaded.get("saved_path"),
                    },
                )
                continue

    raw_to_save["downloaded_attachments"] = downloaded_attachments

    attachment_text = merge_attachment_texts(downloaded_attachments)
    raw_to_save["attachment_text"] = attachment_text
    raw_to_save["content_hash"] = build_content_hash(
        raw_text=raw_to_save.get("raw_text"),
        table_text=raw_to_save.get("table_text"),
        attachment_text=attachment_text,
        image_text=image_text,
    )

    candidate_curated = build_curated_document(raw_to_save, version=1)

    version_result = version_manager.apply_version(source_type, dict(candidate_curated))
    final_curated = version_result["document"]
    decision = version_result["decision"]
    final_curated["change_type"] = decision

    raw_to_save["version"] = final_curated["version"]

    document_store.save_json(raw_path, raw_to_save)
    document_store.save_curated_document(source_type, doc_id, final_curated)

    manifest_writer.write_document_record(raw_to_save)
    manifest_writer.append_jsonl("document_versioning.jsonl", {
        "doc_id": doc_id,
        "source_type": source_type,
        "decision": decision,
        "version": final_curated["version"],
        "source_url": final_curated.get("source_url"),
    })

    record_document_state(
        url=raw_to_save.get("source_url"),
        doc_id=doc_id,
        status="PARSED",
        final_url=raw_to_save.get("final_url"),
        source_type=source_type,
        page_kind=raw_to_save.get("page_kind"),
        checksum=raw_to_save.get("content_hash"),
        artifact_paths={
            "raw_json": raw_path.as_posix(),
            "curated_json": str((CURATED_DOC_DIR / source_type / f"{doc_id}.json").as_posix()),
            "raw_html": raw_to_save.get("raw_html_path") or raw_to_save.get("html_path"),
        },
        extractor_name=raw_to_save.get("extractor_name"),
        extractor_version=raw_to_save.get("extractor_version"),
    )

    print(f"[SAVE OK] doc_id={doc_id} decision={decision} version={final_curated['version']}")

    for att in raw_to_save["attachments"]:
        att_doc = {
            "doc_id": f"{doc_id}_att_{att['attachment_index']:03d}",
            "parent_doc_id": doc_id,
            "source_type": "attachment",
            "page_kind": "attachment",
            "title": att["file_name"],
            "source_url": att["file_url"],
            "file_name": att["file_name"],
            "attachment_index": att["attachment_index"],
        }
        att_path = RAW_ATTACH_DIR / source_type / f"{att_doc['doc_id']}.json"
        save_json(att_path, att_doc)
        manifest_writer.write_attachment_record(doc_id, att_doc)


def get_latest_published_at(source_type: str) -> str | None:
    try:
        loader = get_pgv_loader()
        with loader.conn.cursor() as cur:
            cur.execute(
                "SELECT max(published_at)::date::text FROM documents WHERE source_type = %s;",
                (source_type,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception as exc:
        log_error(f"[INCREMENTAL DATE ERROR] source={source_type} error={exc}")
        return None


def run_board_pipeline(
    source_type: str,
    list_url: str,
    pages: int = 10,
    parser_type: str = "default",
    since_date: str | None = None,
    max_detail_count: int | None = None,
) -> None:
    list_extractor = BoardListExtractor(timeout=RUNTIME["timeout"])

    if parser_type == "ipsi":
        detail_extractor = IpsiNoticeParser(
            enable_image_ocr=RUNTIME["enable_image_ocr"],
            timeout=RUNTIME["timeout"],
        )
    else:
        detail_extractor = BoardDetailExtractor(
            enable_image_ocr=RUNTIME["enable_image_ocr"],
            timeout=RUNTIME["timeout"],
        )

    stop_crawling = False
    processed_count = 0

    seen_doc_ids = set()

    for page_no in range(1, pages + 1):
        if stop_crawling:
            break
        try:
            list_result = list_extractor.extract_list(list_url, page_no, page_size=10)
            print(f"[LIST] source={source_type} page={page_no} count={list_result['count']}")

            manifest_path = MANIFEST_DIR / f"{source_type}_page_{page_no}.json"
            save_json(manifest_path, {
                "list_url": list_result["list_url"],
                "page_no": list_result["page_no"],
                "count": list_result["count"],
                "items": list_result["items"],
            })

            for item in list_result["items"]:
                try:
                    published_at = item.get("published_at_hint")
                    if since_date and published_at and published_at < since_date:
                        print(f"[STOP] {source_type} reached older post: {published_at} < {since_date}")
                        stop_crawling = True
                        break
                    if max_detail_count is not None and processed_count >= max_detail_count:
                        print(f"[STOP] {source_type} reached max_detail_count={max_detail_count}")
                        stop_crawling = True
                        break

                    raw_doc = detail_extractor.extract_detail(
                        source_type,
                        item["detail_url"],
                        title_hint=item.get("title_hint"),
                    )

                    if raw_doc["doc_id"] in seen_doc_ids:
                        continue

                    seen_doc_ids.add(raw_doc["doc_id"])
                    save_document_bundle(raw_doc, download_attachments=True)
                    processed_count += 1

                    print(f"[OK] saved {raw_doc['doc_id']}")
                    if RUNTIME["sleep_seconds"] > 0:
                        time.sleep(RUNTIME["sleep_seconds"])

                except Exception as e:
                    message = f"[DETAIL ERROR] source={source_type} url={item['detail_url']} error={e}"
                    log_error(message)
                    manifest_writer.write_error_record(
                        stage="board_detail",
                        message=message,
                        extra={"source_type": source_type, "url": item["detail_url"]},
                    )
                    record_crawl_job_error(
                        run_type="full_pipeline",
                        stage="board_detail",
                        error=e,
                        source_type=source_type,
                        doc_id=f"deu_{source_type}_{item.get('article_no')}" if item.get("article_no") else None,
                        url=item.get("detail_url"),
                        context={
                            "article_no": item.get("article_no"),
                            "title_hint": item.get("title_hint"),
                            "published_at_hint": item.get("published_at_hint"),
                            "row_text": item.get("row_text"),
                        },
                    )
                    enqueue_retry_queue_error(
                        task_type="board_detail",
                        reason="detail_fetch_or_parse_failed",
                        doc_id=f"deu_{source_type}_{item.get('article_no')}" if item.get("article_no") else None,
                        url=item.get("detail_url"),
                        source_type=source_type,
                        page_kind="board_detail",
                        payload={
                            "article_no": item.get("article_no"),
                            "title_hint": item.get("title_hint"),
                            "published_at_hint": item.get("published_at_hint"),
                            "row_text": item.get("row_text"),
                            "extraction_strategy": item.get("extraction_strategy"),
                        },
                    )

        except Exception as e:
            message = f"[LIST ERROR] source={source_type} page={page_no} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="board_list",
                message=message,
                extra={"source_type": source_type, "list_url": list_url, "page_no": page_no},
            )
            record_crawl_job_error(
                run_type="full_pipeline",
                stage="board_list",
                error=e,
                source_type=source_type,
                url=list_url,
                context={
                    "page_no": page_no,
                    "page_size": 10,
                    "list_url": list_url,
                },
            )
            enqueue_retry_queue_error(
                task_type="board_list",
                reason="list_fetch_or_parse_failed",
                url=list_url,
                source_type=source_type,
                page_kind="board_list",
                payload={
                    "page_no": page_no,
                    "page_size": 10,
                    "list_url": list_url,
                    "pages": 1,
                },
            )


def process_static_seed(
    item: dict,
    download_attachments: bool | None = None,
    raise_on_error: bool = False,
) -> None:
    extractor = StaticPageExtractor(
        allowed_hosts=ALLOWED_HOSTS,
        enable_image_ocr=RUNTIME["enable_image_ocr"],
        timeout=RUNTIME["timeout"],
    )
    try:
        raw_doc = extractor.extract_static_page(
            source_type=item["source_type"],
            page_url=item["url"],
        )
        should_download = (
            download_attachments
            if download_attachments is not None
            else bool(item.get("download_attachments", RUNTIME["download_static_attachments"]))
        )
        save_document_bundle(raw_doc, download_attachments=should_download)
        print(f"[STATIC OK] saved {raw_doc['doc_id']}")
    except Exception as e:
        message = f"[STATIC ERROR] source={item['source_type']} url={item['url']} error={e}"
        log_error(message)
        manifest_writer.write_error_record(
            stage="static_page",
            message=message,
            extra={"source_type": item["source_type"], "url": item["url"]},
        )
        record_crawl_job_error(
            run_type="full_pipeline",
            stage="static_page",
            error=e,
            source_type=item.get("source_type"),
            url=item.get("url"),
            context={
                "page_kind": item.get("page_kind"),
                "seed_name": item.get("name"),
            },
        )
        record_document_state(
            url=item.get("url"),
            status="FAILED",
            source_type=item.get("source_type"),
            page_kind=item.get("page_kind"),
            error=str(e),
            error_stage="static_page",
        )
        if raise_on_error:
            raise


def run_static_pipeline(static_urls: list[dict], workers: int = 1) -> None:
    if workers <= 1:
        for item in static_urls:
            process_static_seed(item)
            if RUNTIME["sleep_seconds"] > 0:
                time.sleep(RUNTIME["sleep_seconds"])
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_static_seed, item) for item in static_urls]
        for future in as_completed(futures):
            future.result()


def load_dynamic_board_seeds(min_confidence: float) -> list[dict]:
    state_store = CrawlerStateStore()
    try:
        state_store.ensure_tables()
        return state_store.list_promoted_dynamic_seeds(min_confidence)
    finally:
        state_store.close()


def merge_dynamic_board_seeds(board_seeds: list[dict], dynamic_board_seeds: list[dict]) -> list[dict]:
    existing_urls = {seed["url"] for seed in board_seeds}
    return [*board_seeds, *[seed for seed in dynamic_board_seeds if seed["url"] not in existing_urls]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DEU crawling pipeline.")
    parser.add_argument(
        "--static-seed-names",
        nargs="+",
        help="Run only the named static seeds from crawler.config.seeds.",
    )
    parser.add_argument(
        "--enable-image-ocr",
        action="store_true",
        help="Enable image OCR. Disabled by default for faster crawls.",
    )
    parser.add_argument(
        "--skip-image-ocr",
        action="store_true",
        help="Deprecated compatibility flag. Image OCR is skipped by default.",
    )
    parser.add_argument("--skip-pdf-ocr", action="store_true", help="Disable PDF OCR fallback.")
    parser.add_argument("--enable-pdf-ocr", action="store_true", help="Enable PDF OCR fallback.")
    parser.add_argument("--pdf-ocr-max-pages", type=int, default=5, help="Maximum PDF pages to OCR.")
    parser.add_argument("--pdf-ocr-first-pages", type=int, default=None, help="Only OCR the first N PDF pages.")
    parser.add_argument("--pages", type=int, default=10, help="Maximum board list pages per board seed.")
    parser.add_argument("--since-date", help="Only process board posts on or after YYYY-MM-DD.")
    parser.add_argument("--max-detail-count", type=int, default=None, help="Maximum board detail pages per board seed.")
    parser.add_argument("--incremental", action="store_true", help="Use latest DB published_at as since-date per source.")
    parser.add_argument(
        "--use-discovered-seeds",
        action="store_true",
        help="Include promoted dynamic board seeds from Postgres state tables.",
    )
    parser.add_argument(
        "--closed-loop-discovery",
        action="store_true",
        help="Enable promoted discovery seeds in the full pipeline. Alias for --use-discovered-seeds.",
    )
    parser.add_argument(
        "--min-discovery-confidence",
        type=float,
        default=0.8,
        help="Minimum confidence for dynamic board seeds when --use-discovered-seeds is set.",
    )
    parser.add_argument("--connect-timeout", type=float, default=5, help="HTTP connect timeout in seconds.")
    parser.add_argument("--read-timeout", type=float, default=30, help="HTTP read timeout in seconds.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Delay between successful requests.")#--
    attachment_group = parser.add_mutually_exclusive_group()
    attachment_group.add_argument(
        "--download-attachments",
        dest="download_attachments",
        action="store_true",
        default=True,
        help="Download and parse static-page attachments. Enabled by default for operational runs.",
    )
    attachment_group.add_argument(
        "--no-download-attachments",
        dest="download_attachments",
        action="store_false",
        help="Skip static-page attachment download for compatibility or fast local checks.",
    )
    parser.add_argument(
        "--compress-raw-html",
        action="store_true",
        help="Store raw HTML sidecar files as gzip while preserving raw JSON compatibility by default.",
    )
    parser.add_argument(
        "--raw-json-html-metadata-only",
        action="store_true",
        help="Store only raw HTML path/hash/size metadata in raw JSON. Use with care; changes raw JSON shape.",
    )
    parser.add_argument(
        "--allow-insecure-ssl",#--
        action="store_true",
        help="Allow configured legacy DEU hosts to retry static pages without SSL verification.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Static page worker count. Keep low for polite crawling.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    RUNTIME["enable_image_ocr"] = bool(args.enable_image_ocr and not args.skip_image_ocr)
    RUNTIME["timeout"] = (args.connect_timeout, args.read_timeout)
    RUNTIME["sleep_seconds"] = max(0.0, args.sleep)
    RUNTIME["download_static_attachments"] = bool(args.download_attachments)
    document_store.compress_raw_html = bool(args.compress_raw_html)
    document_store.raw_json_html_metadata_only = bool(args.raw_json_html_metadata_only)
    if args.allow_insecure_ssl:
        os.environ["CRAWLER_ALLOW_INSECURE_SSL"] = "1"
    os.environ["CRAWLER_SKIP_PDF_OCR"] = "0" if args.enable_pdf_ocr and not args.skip_pdf_ocr else "1"
    os.environ["CRAWLER_PDF_OCR_MAX_PAGES"] = "" if args.pdf_ocr_max_pages is None else str(args.pdf_ocr_max_pages)
    os.environ["CRAWLER_PDF_OCR_FIRST_PAGES"] = "" if args.pdf_ocr_first_pages is None else str(args.pdf_ocr_first_pages)

    board_seeds = []
    static_seeds = []

    for seed in iter_enabled_seeds():
        if seed["page_kind"] == "board_list":
            board_seeds.append(seed)
        elif seed["page_kind"] in {"seed", "static_page"}:
            static_seeds.append(seed)

    use_discovered_seeds = bool(args.use_discovered_seeds or args.closed_loop_discovery)
    if not use_discovered_seeds and os.getenv("CRAWLER_OPERATION_MODE") in {"prod", "production", "operating"}:
        print(
            "[WARN] operating mode without closed loop discovery: "
            "pass --closed-loop-discovery or --use-discovered-seeds to include promoted dynamic board seeds."
        )

    if use_discovered_seeds:
        dynamic_board_seeds = load_dynamic_board_seeds(args.min_discovery_confidence)
        merged_board_seeds = merge_dynamic_board_seeds(board_seeds, dynamic_board_seeds)
        added_count = len(merged_board_seeds) - len(board_seeds)
        board_seeds = merged_board_seeds
        print(
            "[DYNAMIC SEEDS] "
            f"loaded={len(dynamic_board_seeds)} added={added_count} "
            f"min_confidence={args.min_discovery_confidence}"
        )

    if args.static_seed_names:
        selected_names = set(args.static_seed_names)
        static_seeds = [seed for seed in static_seeds if seed.get("name") in selected_names]
        missing_names = sorted(selected_names - {seed.get("name") for seed in static_seeds})
        if missing_names:
            raise ValueError(f"unknown static seed names: {', '.join(missing_names)}")
        run_static_pipeline(static_seeds, workers=args.workers)
        return

    for seed in board_seeds:
        parser_type = "ipsi" if "ipsi" in seed["url"] else "default"
        since_date = args.since_date
        if args.incremental:
            latest = get_latest_published_at(seed["source_type"])
            since_date = max(filter(None, [since_date, latest]), default=None)
            print(f"[INCREMENTAL] source={seed['source_type']} since_date={since_date}")
        run_board_pipeline(
            source_type=seed["source_type"],
            list_url=seed["url"],
            pages=args.pages,
            parser_type=parser_type,
            since_date=since_date,
            max_detail_count=args.max_detail_count,
        )

    run_static_pipeline(static_seeds, workers=args.workers)


if __name__ == "__main__":
    main()
