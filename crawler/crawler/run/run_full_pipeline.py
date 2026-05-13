# crawler/run/run_full_pipeline.py

import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from crawler.utils.content_hash import build_content_hash
from crawler.config.seeds import SEED_URLS
from crawler.config.domains import ALLOWED_HOSTS
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.storage.manifest_writer import ManifestWriter
from crawler.schemas.document_models import CuratedDocument
from crawler.ingestion.document_version_manager import DocumentVersionManager
from crawler.normalize.text_cleaner import TextCleaner

BASE_DIR = Path("crawler/data")
RAW_HTML_DIR = BASE_DIR / "raw" / "html"
RAW_DOC_DIR = BASE_DIR / "raw" / "documents"
RAW_ATTACH_DIR = BASE_DIR / "raw" / "attachments"
CURATED_DOC_DIR = BASE_DIR / "curated" / "documents"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_HTML_DIR, RAW_DOC_DIR, RAW_ATTACH_DIR, CURATED_DOC_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

text_cleaner = TextCleaner()
manifest_writer = ManifestWriter()
version_manager = DocumentVersionManager(curated_base_dir=str(CURATED_DOC_DIR))
pgv_loader = None
RUNTIME = {
    "enable_image_ocr": False,
    "timeout": (5, 30),
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

def save_json(path: Path, data: dict | list) -> None:               # JSON ??μ슜 ?좏떥 ?⑥닔
    path.parent.mkdir(parents=True, exist_ok=True)                  # 遺紐??대뜑 ?놁쑝硫??앹꽦
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")       # JSON pretty format, UTF-8 ?쒓? ??源⑥?寃????

def load_json(path: Path) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_text(path: Path, text: str) -> None:           # HTML ?먮Ц 媛숈? ?띿뒪???뚯씪 ??μ슜 ?⑥닔
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def log_error(message: str) -> None:                    # ?먮윭 濡쒓렇瑜?肄섏넄?먮룄 李띻퀬 ?뚯씪?먮룄 ?④린???⑥닔
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


def merge_attachment_texts(downloaded_attachments: list[dict]) -> str | None:       # 泥⑤??뚯씪?ㅼ뿉??戮묒? ?띿뒪?몃? 臾몄꽌 蹂몃Ц???⑹튌 ???덈뒗 ?섎굹??臾몄옄?대줈 留뚮뱶???⑥닔
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


def build_curated_document(raw_doc: dict, version: int) -> dict:                                  # raw 臾몄꽌瑜?curated 臾몄꽌濡?諛붽씀???⑥닔
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


def save_document_bundle(raw_doc: dict, download_attachments: bool = False) -> None:        # ?듭떖 ?⑥닔
    source_type = raw_doc["source_type"]
    doc_id = raw_doc["doc_id"]

    html_path = RAW_HTML_DIR / source_type / f"{doc_id}.html"
    raw_path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"

    save_text(html_path, raw_doc["html"])           # ?먮낯 html ???

    raw_to_save = dict(raw_doc)                     # raw_doc 蹂듭궗(?먮Ц ?먯떎 諛⑹?)
    raw_to_save["html_path"] = str(html_path.as_posix())
    raw_to_save.pop("html", None)

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
    elif download_attachments and raw_to_save.get("attachments"):     # 泥⑤? ?ㅼ슫濡쒕뱶媛 耳쒖졇 ?덇퀬, ?ㅼ젣 泥⑤?媛 ?덉쑝硫?        from crawler.extractors.attachment_downloader import AttachmentDownloader
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

            except Exception as e:              # ?뱀젙 泥⑤?媛 源⑥졇??怨꾩냽 ???
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
                continue


            try:    
                parse_result = file_router.extract_text(downloaded["saved_path"])       # ?뚯씪 寃쎈줈瑜??뚯씪 遺꾧린 router???섍?
                downloaded["parser_type"] = parse_result.get("parser_type")             # 寃곌낵 諛쏄린
                downloaded["attachment_text"] = parse_result.get("attachment_text")
                downloaded["page_count"] = parse_result.get("page_count")
                downloaded["pages"] = parse_result.get("pages")
                downloaded["note"] = parse_result.get("note")
                downloaded["raw_xml_files"] = parse_result.get("raw_xml_files", [])

                downloaded_attachments.append(downloaded)
                manifest_writer.write_file_parse_record(doc_id, downloaded, parse_result)

            except Exception as e:              # ?뱀젙 泥⑤?媛 源⑥졇??怨꾩냽 ???
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

    # 癒쇱? "??curated ?꾨낫"瑜?硫붾え由ъ뿉??留뚮뱺??
    candidate_curated = build_curated_document(raw_to_save, version=1)

    # ????꾩뿉 湲곗〈 curated? 鍮꾧탳
    version_result = version_manager.apply_version(source_type, dict(candidate_curated))
    final_curated = version_result["document"]
    decision = version_result["decision"]
    final_curated["change_type"] = decision

    # 鍮꾧탳 寃곌낵 version??raw?먮룄 留욎떠以?
    raw_to_save["version"] = final_curated["version"]

    save_json(raw_path, raw_to_save)
    save_json(curated_path, final_curated)

    manifest_writer.write_document_record(raw_to_save)
    manifest_writer.append_jsonl("document_versioning.jsonl", {
        "doc_id": doc_id,
        "source_type": source_type,
        "decision": decision,
        "version": final_curated["version"],
        "source_url": final_curated.get("source_url"),
    })

    print(f"[SAVE OK] doc_id={doc_id} decision={decision} version={final_curated['version']}")

    for att in raw_to_save["attachments"]:              # 泥⑤? 硫뷀?瑜?蹂꾨룄 attachment 臾몄꽌濡쒕룄 ???
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
) -> None:      # 寃뚯떆?먰삎 seed瑜?泥섎━?섎뒗 ?ㅽ뻾 ?⑥닔
    list_extractor = BoardListExtractor(timeout=RUNTIME["timeout"])

    if parser_type == "ipsi":           # ?낇븰泥섎㈃ ?꾩슜 ?뚯꽌, ?꾨땲硫??쇰컲 ?뚯꽌 ?ъ슜
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

    for page_no in range(1, pages + 1):     # 吏?뺥븳 page留뚰겮 ?먯깋
        if stop_crawling:
            break
        try:
            list_result = list_extractor.extract_list(list_url, page_no, page_size=10)      # 紐⑸줉 ?섏씠吏 HTML???쎄퀬, ?곸꽭 URL 紐⑸줉 異붿텧
            print(f"[LIST] source={source_type} page={page_no} count={list_result['count']}")

            manifest_path = Path("crawler/data/manifest") / f"{source_type}_page_{page_no}.json"
            save_json(manifest_path, {
                "list_url": list_result["list_url"],
                "page_no": list_result["page_no"],
                "count": list_result["count"],
                "items": list_result["items"],
            })

            for item in list_result["items"]:           # 紐⑸줉?먯꽌 ?섏삩 媛??곸꽭 URL???섎굹??泥섎━
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

        except Exception as e:              # 紐⑸줉 ?섏씠吏 ?먯껜媛 ?ㅽ뙣?섎㈃ 洹??섏씠吏??嫄대꼫?
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


def process_static_seed(item: dict) -> None:
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
        save_document_bundle(raw_doc, download_attachments=False)
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


def run_static_pipeline(static_urls: list[dict], workers: int = 1) -> None:           # ?뺤쟻 ?섏씠吏 seed 泥섎━ ?⑥닔
    if workers <= 1:
        for item in static_urls:
            process_static_seed(item)
        return

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_static_seed, item) for item in static_urls]
        for future in as_completed(futures):
            future.result()


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
    parser.add_argument("--connect-timeout", type=float, default=5, help="HTTP connect timeout in seconds.")
    parser.add_argument("--read-timeout", type=float, default=30, help="HTTP read timeout in seconds.")
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
    os.environ["CRAWLER_SKIP_PDF_OCR"] = "0" if args.enable_pdf_ocr and not args.skip_pdf_ocr else "1"
    os.environ["CRAWLER_PDF_OCR_MAX_PAGES"] = "" if args.pdf_ocr_max_pages is None else str(args.pdf_ocr_max_pages)
    os.environ["CRAWLER_PDF_OCR_FIRST_PAGES"] = "" if args.pdf_ocr_first_pages is None else str(args.pdf_ocr_first_pages)

    board_seeds = []
    static_seeds = []

    for seed in SEED_URLS:
        if seed["page_kind"] == "board_list":
            board_seeds.append(seed)
        elif seed["page_kind"] in {"seed", "static_page"}:
            static_seeds.append(seed)

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
