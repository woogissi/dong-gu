# crawler/run/run_static_discovery.py

import json
import time
from pathlib import Path
from datetime import datetime


from crawler.utils.content_hash import build_content_hash
from crawler.config.seeds import SEED_URLS
from crawler.config.domains import ALLOWED_HOSTS
from crawler.discovery.url_classifier import URLClassifier
from crawler.discovery.frontier_manager import FrontierManager
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.storage.manifest_writer import ManifestWriter
from crawler.normalize.text_cleaner import TextCleaner
from crawler.schemas.document_models import CuratedDocument
from crawler.ingestion.document_version_manager import DocumentVersionManager
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.ipsi_notice_parser import IpsiNoticeParser
from crawler.ingestion.pgvector_loader import PGVectorLoader

BASE_DIR = Path("crawler/data")
RAW_HTML_DIR = BASE_DIR / "raw" / "html"
RAW_DOC_DIR = BASE_DIR / "raw" / "documents"
CURATED_DOC_DIR = BASE_DIR / "curated" / "documents"
LOG_DIR = BASE_DIR / "logs"

version_manager = DocumentVersionManager(curated_base_dir=str(CURATED_DOC_DIR))

for d in [RAW_HTML_DIR, RAW_DOC_DIR, CURATED_DOC_DIR, LOG_DIR]:     # 필요한 폴더들을 미리 생성
    d.mkdir(parents=True, exist_ok=True)

manifest_writer = ManifestWriter()
url_classifier = URLClassifier()
text_cleaner = TextCleaner()

pgv_loader = None

try:
    pgv_loader = PGVectorLoader()
except Exception as e:
    print(f"[DB DISABLED] DB connection failed. DB logging will be skipped. error={e}")

def save_json(path: Path, data: dict | list) -> None:       # JSON 저장 함수
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, text: str) -> None:               # html 원문 저장용 텍스트 파일 저장 함수
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "crawl_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def merge_image_texts(image_texts: list[dict]) -> str | None:
    texts = []

    for item in image_texts or []:
        image_text = item.get("image_text")
        image_url = item.get("image_url")
        if image_text:
            texts.append(f"[IMAGE: {image_url}]\n{image_text}")

    merged = "\n\n".join(texts).strip()
    return merged if merged else None


def build_curated_document(raw_doc: dict, version: int) -> dict:      # raw 정적 문서를 curated 문서로 바꾸는 함수
    normalize = text_cleaner.build_clean_text(         # full_pipeline 보다 더 정제 열심히
        raw_text=raw_doc["raw_text"],
        table_text=raw_doc["table_text"],
    )
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
        normalize=normalize,
        table_text=raw_doc["table_text"],
        attachment_text=raw_doc["attachment_text"],
        image_text=image_text,
        version=version,
        collected_at=raw_doc["collected_at"],
        content_hash=raw_doc["content_hash"],
    )

    return curated_doc.model_dump()


def save_static_document(raw_doc: dict) -> None:        # 문서의 source_type과 doc_id를 이용해 저장 경로 계산 함수
    source_type = raw_doc["source_type"]
    doc_id = raw_doc["doc_id"]

    html_path = RAW_HTML_DIR / source_type / f"{doc_id}.html"
    raw_path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"

    save_text(html_path, raw_doc["html"])       # 원문 저장

    raw_to_save = dict(raw_doc)
    raw_to_save["html_path"] = str(html_path.as_posix())
    raw_to_save.pop("html", None)

    raw_to_save["content_hash"] = build_content_hash(
        raw_text=raw_to_save.get("raw_text"),
        table_text=raw_to_save.get("table_text"),
        attachment_text=raw_to_save.get("attachment_text"),
    )

    # 새 curated 후보 생성
    candidate_curated = build_curated_document(raw_to_save, version=1)

    # 저장 전에 기존 curated와 비교
    version_result = version_manager.apply_version(source_type, dict(candidate_curated))
    final_curated = version_result["document"]
    decision = version_result["decision"]
    final_curated["change_type"] = decision

    raw_to_save["version"] = final_curated["version"]

    save_json(raw_path, raw_to_save)            # raw 저장
    save_json(curated_path, final_curated)        # curated 저장
    manifest_writer.write_document_record(raw_to_save)      # manifest 기록
    manifest_writer.append_jsonl("document_versioning.jsonl", {
        "doc_id": doc_id,
        "source_type": source_type,
        "decision": decision,
        "version": final_curated["version"],
        "source_url": final_curated.get("source_url"),
    })

    print(f"[STATIC SAVE OK] doc_id={doc_id} decision={decision} version={final_curated['version']}")

def process_board_list_from_html(
    list_url: str,
    source_type: str,
    html: str,
    pages: int = 10,
    page_size: int = 10,
) -> None:
    list_extractor = BoardListExtractor()

    if "ipsi.deu.ac.kr" in list_url.lower():
        detail_extractor = IpsiNoticeParser()
    else:
        detail_extractor = BoardDetailExtractor()

    current_year_start = f"{datetime.now().year}-01-01"
    stop_crawling = False
    seen_doc_ids = set()

    try:
        first_items = list_extractor.parse_rows(html, list_url)
    except Exception as e:
        message = f"[DISCOVERED BOARD PARSE ROWS ERROR] url={list_url} error={e}"
        log_error(message)
        manifest_writer.write_error_record(
            stage="discovered_board_parse_rows",
            message=message,
            extra={
                "source_type": source_type,
                "list_url": list_url,
            },
        )
        pgv_loader.insert_crawl_job_error(
            run_type="static_discovery",
            stage="discovered_board_parse_rows",
            error=e,
            source_type=source_type,
            url=list_url,
            context={
                "list_url": list_url,
                "page_no": 1,
                "mode": "html_detected_board",
            },
        )
        return

    page_results = [
        {
            "list_url": list_url,
            "page_no": 1,
            "page_size": page_size,
            "count": len(first_items),
            "items": first_items,
            "html": html,
        }
    ]

    for page_no in range(2, pages + 1):
        if stop_crawling:
            break

        try:
            list_result = list_extractor.extract_list(
                list_url,
                page_no=page_no,
                page_size=page_size,
            )

            page_results.append(list_result)

            if list_result["count"] == 0:
                break

        except Exception as e:
            message = f"[DISCOVERED BOARD LIST ERROR] url={list_url} page={page_no} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="discovered_board_list",
                message=message,
                extra={
                    "source_type": source_type,
                    "list_url": list_url,
                    "page_no": page_no,
                },
            )
            pgv_loader.insert_crawl_job_error(
                run_type="static_discovery",
                stage="discovered_board_list",
                error=e,
                source_type=source_type,
                url=list_url,
                context={
                    "list_url": list_url,
                    "page_no": page_no,
                    "page_size": page_size,
                },
            )
            break

    for list_result in page_results:
        if stop_crawling:
            break

        if list_result["count"] == 0:
            break

        print(
            f"[DISCOVERED BOARD LIST] "
            f"source={source_type} page={list_result['page_no']} "
            f"count={list_result['count']} url={list_url}"
        )

        for item in list_result["items"]:
            try:
                raw_doc = detail_extractor.extract_detail(
                    source_type=source_type,
                    detail_url=item["detail_url"],
                    title_hint=item.get("title_hint"),
                )

                if raw_doc["doc_id"] in seen_doc_ids:
                    continue

                seen_doc_ids.add(raw_doc["doc_id"])

                save_static_document(raw_doc)

                manifest_writer.append_jsonl("discovered_board_items.jsonl", {
                    "list_url": list_url,
                    "detail_url": item.get("detail_url"),
                    "doc_id": raw_doc.get("doc_id"),
                    "source_type": source_type,
                    "page_no": list_result["page_no"],
                    "title_hint": item.get("title_hint"),
                    "published_at_hint": item.get("published_at_hint"),
                })

                print(f"[DISCOVERED BOARD DETAIL OK] doc_id={raw_doc['doc_id']}")

                published_at = item.get("published_at_hint")

                if published_at and published_at < current_year_start:
                    print(
                        f"[DISCOVERED BOARD STOP] "
                        f"{source_type} reached older post: "
                        f"{published_at} < {current_year_start}"
                    )
                    stop_crawling = True
                    break

            except Exception as e:
                doc_id = None
                if item.get("article_no"):
                    doc_id = f"deu_{source_type}_{item.get('article_no')}"

                message = (
                    f"[DISCOVERED BOARD DETAIL ERROR] "
                    f"source={source_type} url={item.get('detail_url')} error={e}"
                )
                log_error(message)
                manifest_writer.write_error_record(
                    stage="discovered_board_detail",
                    message=message,
                    extra={
                        "source_type": source_type,
                        "list_url": list_url,
                        "detail_url": item.get("detail_url"),
                        "item": item,
                    },
                )
                pgv_loader.insert_crawl_job_error(
                    run_type="static_discovery",
                    stage="discovered_board_detail",
                    error=e,
                    source_type=source_type,
                    doc_id=doc_id,
                    url=item.get("detail_url"),
                    context={
                        "list_url": list_url,
                        "article_no": item.get("article_no"),
                        "title_hint": item.get("title_hint"),
                        "published_at_hint": item.get("published_at_hint"),
                        "row_text": item.get("row_text"),
                    },
                )

def main(max_pages: int = 50, max_depth: int = 2):
    frontier = FrontierManager(ALLOWED_HOSTS, max_depth=max_depth)
    extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)

    # static seed만 넣기
    for seed in SEED_URLS:
        if seed["page_kind"] in {"static_page", "seed"}:
            frontier.add_url(seed["url"], depth=0, discovered_from="seed", source_type=seed["source_type"],)

    crawled_count = 0

    while frontier.has_next() and crawled_count < max_pages:        # frontier에 방문할 URL이 남아있고, 최대 수집 페이지 수를 넘지 않으면 
        item = frontier.pop_next()      # 큐에서 다음 URL을 꺼내서 정보를 꺼냄
        if not item:
            break

        url, depth, discovered_from, inherited_source_type = item
        frontier.mark_visited(url)      # 방문한 곳인지

        try:
            url_type = url_classifier.classify(url)     # 정적페이지인지 다시 확인

            # 현재 static discovery는 정적 페이지만 대상으로 삼음
            if url_type != "static_page":
                continue

            source_type = source_type = inherited_source_type or url_classifier.infer_source_type(url)

            html = extractor.fetch(url)

            list_extractor = BoardListExtractor()

            if list_extractor.looks_like_board_list(html, url):
                process_board_list_from_html(
                    list_url=url,
                    source_type=source_type,
                    html=html,
                    pages=10,
                    page_size=10,
                )

                manifest_writer.append_jsonl("discovery_edges.jsonl", {
                    "url": url,
                    "depth": depth,
                    "discovered_from": discovered_from,
                    "source_type": source_type,
                    "detected_type": "board_list_by_html",
                })

                crawled_count += 1
                print(f"[DISCOVERY BOARD OK] depth={depth} source={source_type} url={url}")
                time.sleep(0.5)
                continue

            raw_doc = extractor.extract_static_page(
                source_type=source_type,
                page_url=url,
            )
            save_static_document(raw_doc)   

            manifest_writer.append_jsonl("discovery_edges.jsonl", {
                "url": url,
                "depth": depth,
                "discovered_from": discovered_from,
                "source_type": source_type,
                "outgoing_link_count": len(raw_doc.get("outgoing_links", [])),
            })

            # 내부 링크 확장
            for next_url in raw_doc.get("outgoing_links", []):
                next_type = url_classifier.classify(next_url)

                # 정적 페이지만 계속 확장
                if next_type == "static_page":
                    frontier.add_url(next_url, depth=depth + 1, discovered_from=url, source_type= source_type)

            crawled_count += 1
            print(f"[DISCOVERY OK] depth={depth} source={source_type} url={url}")
            time.sleep(0.5)

        except Exception as e:
            message = f"[DISCOVERY ERROR] url={url} depth={depth} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="static_discovery",
                message=message,
                extra={"url": url, "depth": depth},
            )
            pgv_loader.insert_crawl_job_error(
                run_type="static_discovery",
                stage="static_page",
                error=e,
                source_type=source_type if "source_type" in locals() else None,
                url=url,
                context={
                    "url": url,
                    "depth": depth,
                    "discovered_from": discovered_from,
                    "inherited_source_type": inherited_source_type if "inherited_source_type" in locals() else None,
                },
            )

    print("[DONE] static discovery finished")
    print(frontier.stats())


if __name__ == "__main__":
    try:
        main(max_pages=50, max_depth=2)
    finally:
        if pgv_loader:
            pgv_loader.close()
