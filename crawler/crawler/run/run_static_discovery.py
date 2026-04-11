# crawler/run/run_static_discovery.py

import json
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


BASE_DIR = Path("crawler/data")
RAW_HTML_DIR = BASE_DIR / "raw" / "html"
RAW_DOC_DIR = BASE_DIR / "raw" / "documents"
CURATED_DOC_DIR = BASE_DIR / "curated" / "documents"
LOG_DIR = BASE_DIR / "logs"

for d in [RAW_HTML_DIR, RAW_DOC_DIR, CURATED_DOC_DIR, LOG_DIR]:     # 필요한 폴더들을 미리 생성
    d.mkdir(parents=True, exist_ok=True)

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


def build_curated_document(raw_doc: dict) -> dict:      # raw 정적 문서를 curated 문서로 바꾸는 함수
    normalize = text_cleaner.build_clean_text(         # full_pipeline 보다 더 정제 열심히
        raw_text=raw_doc["raw_text"],
        table_text=raw_doc["table_text"],
    )

    curated_doc = CuratedDocument(
        doc_id=raw_doc["doc_id"],
        parent_doc_id=raw_doc["parent_doc_id"],
        university=raw_doc["university"],
        campus=raw_doc["campus"],
        source_type=raw_doc["source_type"],
        page_kind=raw_doc["page_kind"],
        category_lv1=raw_doc["category_lv1"],
        category_lv2=raw_doc["category_lv2"],
        department=raw_doc["department"],
        title=raw_doc["title"],
        summary=raw_doc["summary"],
        source_url=raw_doc["source_url"],
        published_at=raw_doc["published_at"],
        updated_at=raw_doc["updated_at"],
        valid_from=raw_doc["valid_from"],
        valid_to=raw_doc["valid_to"],
        target_audience=raw_doc["target_audience"],
        keywords=raw_doc["keywords"],
        raw_text=raw_doc["raw_text"],
        normalize=normalize,
        table_text=raw_doc["table_text"],
        attachment_text=raw_doc["attachment_text"],
        language=raw_doc["language"],
        status=raw_doc["status"],
        version=raw_doc["version"],
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

    save_json(raw_path, raw_to_save)            # raw 저장
    save_json(curated_path, build_curated_document(raw_to_save))        # curated 저장
    manifest_writer.write_document_record(raw_to_save)      # manifest 기록


def main(max_pages: int = 50, max_depth: int = 2):
    frontier = FrontierManager(ALLOWED_HOSTS, max_depth=max_depth)
    extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)

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
            time.sleep(0.5)

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
    main(max_pages=50, max_depth=2)