# crawler/run/run_full_pipeline.py

import json
from pathlib import Path
from datetime import datetime

from crawler.utils.content_hash import build_content_hash
from crawler.config.seeds import SEED_URLS
from crawler.config.domains import ALLOWED_HOSTS
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.extractors.attachment_downloader import AttachmentDownloader
from crawler.parsers.file_text_router import FileTextRouter
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


def save_json(path: Path, data: dict | list) -> None:               # JSON 저장용 유틸 함수
    path.parent.mkdir(parents=True, exist_ok=True)                  # 부모 폴더 없으면 생성
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")       # JSON pretty format, UTF-8 한글 안 깨지게 저장


def save_text(path: Path, text: str) -> None:           # HTML 원문 같은 텍스트 파일 저장용 함수
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def log_error(message: str) -> None:                    # 에러 로그를 콘솔에도 찍고 파일에도 남기는 함수
    print(message)
    with open(LOG_DIR / "crawl_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def merge_attachment_texts(downloaded_attachments: list[dict]) -> str | None:       # 첨부파일들에서 뽑은 텍스트를 문서 본문에 합칠 수 있는 하나의 문자열로 만드는 함수
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


def build_curated_document(raw_doc: dict, version: int) -> dict:                                  # raw 문서를 curated 문서로 바꾸는 함수
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


def save_document_bundle(raw_doc: dict, download_attachments: bool = False) -> None:        # 핵심 함수
    source_type = raw_doc["source_type"]
    doc_id = raw_doc["doc_id"]

    html_path = RAW_HTML_DIR / source_type / f"{doc_id}.html"
    raw_path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"

    save_text(html_path, raw_doc["html"])           # 원본 html 저장

    raw_to_save = dict(raw_doc)                     # raw_doc 복사(원문 손실 방지)
    raw_to_save["html_path"] = str(html_path.as_posix())
    raw_to_save.pop("html", None)

    downloaded_attachments = []
    if download_attachments and raw_to_save.get("attachments"):     # 첨부 다운로드가 켜져 있고, 실제 첨부가 있으면
        downloader = AttachmentDownloader()
        file_router = FileTextRouter()

        for att in raw_to_save["attachments"]:
            try:
                downloaded = downloader.download(source_type, doc_id, att)

                parse_result = file_router.extract_text(downloaded["saved_path"])       # 파일 경로를 파일 분기 router에 넘김
                downloaded["parser_type"] = parse_result.get("parser_type")             # 결과 받기
                downloaded["attachment_text"] = parse_result.get("attachment_text")
                downloaded["page_count"] = parse_result.get("page_count")
                downloaded["pages"] = parse_result.get("pages")
                downloaded["note"] = parse_result.get("note")
                downloaded["raw_xml_files"] = parse_result.get("raw_xml_files", [])

                downloaded_attachments.append(downloaded)
                manifest_writer.write_file_parse_record(doc_id, downloaded, parse_result)

            except Exception as e:              # 특정 첨부가 깨져도 계속 저장
                message = f"[ATTACH DOWNLOAD/PARSE ERROR] doc_id={doc_id} file_url={att['file_url']} error={e}"
                log_error(message)
                manifest_writer.write_error_record(
                    stage="attachment_download_or_parse",
                    message=message,
                    extra={"doc_id": doc_id, "file_url": att["file_url"]},
                )

    raw_to_save["downloaded_attachments"] = downloaded_attachments

    attachment_text = merge_attachment_texts(downloaded_attachments)
    image_text = merge_image_texts(raw_to_save.get("image_texts", []))
    raw_to_save["attachment_text"] = attachment_text
    raw_to_save["content_hash"] = build_content_hash(
        raw_text=raw_to_save.get("raw_text"),
        table_text=raw_to_save.get("table_text"),
        attachment_text=attachment_text,
        image_text=image_text,
    )

    # 먼저 "새 curated 후보"를 메모리에서 만든다
    candidate_curated = build_curated_document(raw_to_save, version=1)

    # 저장 전에 기존 curated와 비교
    version_result = version_manager.apply_version(source_type, dict(candidate_curated))
    final_curated = version_result["document"]
    decision = version_result["decision"]
    final_curated["change_type"] = decision

    # 비교 결과 version을 raw에도 맞춰줌
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

    for att in raw_to_save["attachments"]:              # 첨부 메타를 별도 attachment 문서로도 저장
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


def run_board_pipeline(source_type: str, list_url: str, pages: int = 50, parser_type: str = "default") -> None:      # 게시판형 seed를 처리하는 실행 함수
    list_extractor = BoardListExtractor()

    if parser_type == "ipsi":           # 입학처면 전용 파서, 아니면 일반 파서 사용
        detail_extractor = IpsiNoticeParser()
    else:
        detail_extractor = BoardDetailExtractor()

    current_year_start = f"{datetime.now().year}-01-01"
    stop_crawling = False

    seen_doc_ids = set()

    for page_no in range(1, pages + 1):     # 지정한 page만큼 탐색
        if stop_crawling:
            break
        try:
            list_result = list_extractor.extract_list(list_url, page_no=page_no, page_size=10)      # 목록 페이지 HTML을 읽고, 상세 URL 목록 추출
            print(f"[LIST] source={source_type} page={page_no} count={list_result['count']}")

            manifest_path = Path("crawler/data/manifest") / f"{source_type}_page_{page_no}.json"
            save_json(manifest_path, {
                "list_url": list_result["list_url"],
                "page_no": list_result["page_no"],
                "count": list_result["count"],
                "items": list_result["items"],
            })

            for item in list_result["items"]:           # 목록에서 나온 각 상세 URL을 하나씩 처리
                try:
                    raw_doc = detail_extractor.extract_detail(
                        source_type,
                        item["detail_url"],
                        title_hint=item.get("title_hint"),
                    )

                    if raw_doc["doc_id"] in seen_doc_ids:
                        continue

                    seen_doc_ids.add(raw_doc["doc_id"])
                    save_document_bundle(raw_doc, download_attachments=True)

                    print(f"[OK] saved {raw_doc['doc_id']}")

                    published_at = item.get("published_at_hint")
                    #날짜 올해 1월 1일 전이면 중지
                    if published_at and published_at < current_year_start:
                        print(f"[STOP] {source_type} reached older post: {published_at} < {current_year_start}")
                        stop_crawling = True
                        break

                except Exception as e:
                    message = f"[DETAIL ERROR] source={source_type} url={item['detail_url']} error={e}"
                    log_error(message)
                    manifest_writer.write_error_record(
                        stage="board_detail",
                        message=message,
                        extra={"source_type": source_type, "url": item["detail_url"]},
                    )

        except Exception as e:              # 목록 페이지 자체가 실패하면 그 페이지는 건너뜀
            message = f"[LIST ERROR] source={source_type} page={page_no} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="board_list",
                message=message,
                extra={"source_type": source_type, "list_url": list_url, "page_no": page_no},
            )


def run_static_pipeline(static_urls: list[dict]) -> None:           # 정적 페이지 seed 처리 함수
    extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)

    for item in static_urls:
        try:
            raw_doc = extractor.extract_static_page(
                source_type=item["source_type"],
                page_url=item["url"],
            )
            save_document_bundle(raw_doc, download_attachments=False)           # 현재 정적 페이지는 첨부파일을 다운하지 않음
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
            pages=50,
            parser_type=parser_type,
        )

    run_static_pipeline(static_seeds)


if __name__ == "__main__":
    main()
