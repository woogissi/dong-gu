# crawler/run/run_static_discovery.py

import json
import argparse
import os
import time
from pathlib import Path

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
from crawler.paths import CURATED_DOC_DIR, DATA_DIR, LOG_DIR, RAW_DOC_DIR, RAW_HTML_DIR, ensure_dirs

BASE_DIR = DATA_DIR

version_manager = DocumentVersionManager(curated_base_dir=str(CURATED_DOC_DIR))

ensure_dirs(RAW_HTML_DIR, RAW_DOC_DIR, CURATED_DOC_DIR, LOG_DIR)     # 필요한 폴더들을 미리 생성

manifest_writer = ManifestWriter()
url_classifier = URLClassifier()
text_cleaner = TextCleaner()


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
    image_text = merge_image_texts(raw_to_save.get("image_texts", []))

    raw_to_save["content_hash"] = build_content_hash(
        raw_text=raw_to_save.get("raw_text"),
        table_text=raw_to_save.get("table_text"),
        attachment_text=raw_to_save.get("attachment_text"),
        image_text=image_text,
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

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover and crawl static DEU pages.")
    parser.add_argument("--max-pages", type=int, default=50, help="Maximum static pages to crawl.")
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum discovery depth.")
    parser.add_argument("--enable-image-ocr", action="store_true", help="Enable image OCR. Disabled by default.")
    parser.add_argument("--skip-image-ocr", action="store_true", help="Compatibility flag. Image OCR is skipped by default.")
    parser.add_argument("--connect-timeout", type=float, default=5, help="HTTP connect timeout in seconds.")
    parser.add_argument("--read-timeout", type=float, default=30, help="HTTP read timeout in seconds.")
    parser.add_argument("--sleep", type=float, default=0.5, help="Delay between successful requests.")
    parser.add_argument(
        "--allow-insecure-ssl",
        action="store_true",
        help="Allow configured legacy DEU hosts to retry without SSL verification.",
    )
    return parser.parse_args()


def main(
    max_pages: int = 50,
    max_depth: int = 2,
    enable_image_ocr: bool = False,
    timeout: tuple[float, float] = (5, 30),
    sleep_seconds: float = 0.5,
    allow_insecure_ssl: bool = False,
):
    if allow_insecure_ssl:
        os.environ["CRAWLER_ALLOW_INSECURE_SSL"] = "1"

    frontier = FrontierManager(ALLOWED_HOSTS, max_depth=max_depth)
    extractor = StaticPageExtractor(
        allowed_hosts=ALLOWED_HOSTS,
        enable_image_ocr=enable_image_ocr,
        timeout=timeout,
    )

    # static seed만 넣기
    for seed in SEED_URLS:
        if seed["page_kind"] in {"static_page", "seed"}:
            frontier.add_url(seed["url"], depth=0, discovered_from="seed")

    crawled_count = 0

    while frontier.has_next() and crawled_count < max_pages:        # frontier에 방문할 URL이 남아있고, 최대 수집 페이지 수를 넘지 않으면 
        item = frontier.pop_next()      # 큐에서 다음 URL을 꺼내서 정보를 꺼냄
        if not item:
            break

        url, depth, discovered_from = item
        frontier.mark_visited(url)      # 방문한 곳인지

        try:
            url_type = url_classifier.classify(url)     # 정적페이지인지 다시 확인

            # 현재 static discovery는 정적 페이지만 대상으로 삼음
            if url_type != "static_page":
                continue

            source_type = url_classifier.infer_source_type(url)     # source_type을 추정
            raw_doc = extractor.extract_static_page(source_type=source_type, page_url=url)  # 실제 페이지를 가져와서 raw 문서 dict로 만듬
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
                    frontier.add_url(next_url, depth=depth + 1, discovered_from=url)

            crawled_count += 1
            print(f"[DISCOVERY OK] depth={depth} source={source_type} url={url}")
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        except Exception as e:
            message = f"[DISCOVERY ERROR] url={url} depth={depth} error={e}"
            log_error(message)
            manifest_writer.write_error_record(
                stage="static_discovery",
                message=message,
                extra={"url": url, "depth": depth},
            )

    print("[DONE] static discovery finished")
    print(frontier.stats())


if __name__ == "__main__":
    args = parse_args()
    main(
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        enable_image_ocr=bool(args.enable_image_ocr and not args.skip_image_ocr),
        timeout=(args.connect_timeout, args.read_timeout),
        sleep_seconds=args.sleep,
        allow_insecure_ssl=args.allow_insecure_ssl,
    )
