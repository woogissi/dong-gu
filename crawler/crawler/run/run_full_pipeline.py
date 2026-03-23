# crawler/run/run_full_pipeline.py

import json
from pathlib import Path

from crawler.config.seeds import SEED_URLS
from crawler.config.domains import ALLOWED_HOSTS
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.extractors.attachment_downloader import AttachmentDownloader
from crawler.parsers.file_text_router import FileTextRouter
from crawler.storage.manifest_writer import ManifestWriter


BASE_DIR = Path("crawler/data")
RAW_HTML_DIR = BASE_DIR / "raw" / "html"
RAW_DOC_DIR = BASE_DIR / "raw" / "documents"
RAW_ATTACH_DIR = BASE_DIR / "raw" / "attachments"
CURATED_DOC_DIR = BASE_DIR / "curated" / "documents"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_HTML_DIR, RAW_DOC_DIR, RAW_ATTACH_DIR, CURATED_DOC_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "crawl_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def simple_clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    return raw_text.strip()


def merge_attachment_texts(downloaded_attachments: list[dict]) -> str | None:
    texts = []

    for item in downloaded_attachments:
        attachment_text = item.get("attachment_text")
        file_name = item.get("file_name")
        if attachment_text:
            texts.append(f"[ATTACHMENT: {file_name}]\n{attachment_text}")

    merged = "\n\n".join(texts).strip()
    return merged if merged else None


def build_curated_document(raw_doc: dict) -> dict:
    attachment_text = merge_attachment_texts(raw_doc.get("downloaded_attachments", []))

    return {
        "doc_id": raw_doc["doc_id"],
        "parent_doc_id": raw_doc["parent_doc_id"],
        "university": raw_doc["university"],
        "campus": raw_doc["campus"],
        "source_type": raw_doc["source_type"],
        "page_kind": raw_doc["page_kind"],
        "category_lv1": raw_doc["category_lv1"],
        "category_lv2": raw_doc["category_lv2"],
        "department": raw_doc["department"],
        "title": raw_doc["title"],
        "summary": raw_doc["summary"],
        "source_url": raw_doc["source_url"],
        "published_at": raw_doc["published_at"],
        "updated_at": raw_doc["updated_at"],
        "valid_from": raw_doc["valid_from"],
        "valid_to": raw_doc["valid_to"],
        "target_audience": raw_doc["target_audience"],
        "keywords": raw_doc["keywords"],
        "raw_text": raw_doc["raw_text"],
        "clean_text": simple_clean_text(raw_doc["raw_text"]),
        "table_text": raw_doc["table_text"],
        "attachment_text": attachment_text,
        "language": raw_doc["language"],
        "status": raw_doc["status"],
        "version": raw_doc["version"],
        "collected_at": raw_doc["collected_at"],
        "content_hash": raw_doc["content_hash"],
    }


def save_document_bundle(raw_doc: dict, download_attachments: bool = False) -> None:
    source_type = raw_doc["source_type"]
    doc_id = raw_doc["doc_id"]

    html_path = RAW_HTML_DIR / source_type / f"{doc_id}.html"
    raw_path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"

    save_text(html_path, raw_doc["html"])

    raw_to_save = dict(raw_doc)
    raw_to_save["html_path"] = str(html_path.as_posix())
    raw_to_save.pop("html", None)

    downloaded_attachments = []
    if download_attachments and raw_to_save.get("attachments"):
        downloader = AttachmentDownloader()
        file_router = FileTextRouter()

        for att in raw_to_save["attachments"]:
            try:
                downloaded = downloader.download(source_type, doc_id, att)

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
                message = f"[ATTACH DOWNLOAD/PARSE ERROR] doc_id={doc_id} file_url={att['file_url']} error={e}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="attachment_download_or_parse",
                    message=message,
                    extra={"doc_id": doc_id, "file_url": att["file_url"]},
                )

    raw_to_save["downloaded_attachments"] = downloaded_attachments
    save_json(raw_path, raw_to_save)

    curated_doc = build_curated_document(raw_to_save)
    save_json(curated_path, curated_doc)

    manifest_writer.write_document_record(raw_to_save)

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


def run_board_pipeline(source_type: str, list_url: str, pages: int = 2, parser_type: str = "default") -> None:
    list_extractor = BoardListExtractor()

    if parser_type == "ipsi":
        detail_extractor = IpsiNoticeParser()
    else:
        detail_extractor = BoardDetailExtractor()

    for page_no in range(1, pages + 1):
        try:
            list_result = list_extractor.extract_list(list_url, page_no=page_no, page_size=10)
            print(f"[LIST] source={source_type} page={page_no} count={list_result['count']}")

            manifest_path = Path("crawler/data/manifest") / f"{source_type}_page_{page_no}.json"
            save_json(manifest_path, {
                "list_url": list_result["list_url"],
                "page_no": list_result["page_no"],
                "count": list_result["count"],
                "items": list_result["items"],
            })

            for item in list_result["items"]:
                try:
                    raw_doc = detail_extractor.extract_detail(source_type, item["detail_url"])
                    save_document_bundle(raw_doc, download_attachments=True)
                    print(f"[OK] saved {raw_doc['doc_id']}")
                except Exception as e:
                    message = f"[DETAIL ERROR] source={source_type} url={item['detail_url']} error={e}"
                    log_error(message)
                    manifest_writer.write_error_record(
                        stage="board_detail",
                        message=message,
                        extra={"source_type": source_type, "url": item["detail_url"]},
                    )

        except Exception as e:
            message = f"[LIST ERROR] source={source_type} page={page_no} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="board_list",
                message=message,
                extra={"source_type": source_type, "list_url": list_url, "page_no": page_no},
            )


def run_static_pipeline(static_urls: list[dict]) -> None:
    extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)

    for item in static_urls:
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


def main():
    board_seeds = []
    static_seeds = []

    for seed in SEED_URLS:
        if seed["page_kind"] == "board_list":
            board_seeds.append(seed)
        elif seed["page_kind"] in {"seed", "static_page"}:
            static_seeds.append(seed)

    for seed in board_seeds:
        parser_type = "ipsi" if "ipsi" in seed["url"] else "default"
        run_board_pipeline(
            source_type=seed["source_type"],
            list_url=seed["url"],
            pages=2,
            parser_type=parser_type,
        )

    run_static_pipeline(static_seeds)


if __name__ == "__main__":
    main()