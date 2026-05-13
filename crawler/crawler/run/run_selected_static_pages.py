# crawler/run/run_selected_static_pages.py

import argparse
import json
from pathlib import Path

from crawler.config.domains import ALLOWED_HOSTS
from crawler.config.seeds import SEED_URLS
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.ingestion.document_version_manager import DocumentVersionManager
from crawler.normalize.text_cleaner import TextCleaner
from crawler.schemas.document_models import CuratedDocument
from crawler.storage.manifest_writer import ManifestWriter


BASE_DIR = Path("crawler/data")
RAW_HTML_DIR = BASE_DIR / "raw" / "html"
RAW_DOC_DIR = BASE_DIR / "raw" / "documents"
CURATED_DOC_DIR = BASE_DIR / "curated" / "documents"

for directory in [RAW_HTML_DIR, RAW_DOC_DIR, CURATED_DOC_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

text_cleaner = TextCleaner()
manifest_writer = ManifestWriter()
version_manager = DocumentVersionManager(curated_base_dir=str(CURATED_DOC_DIR))


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
        attachment_text=None,
        image_text=image_text,
        version=version,
        collected_at=raw_doc["collected_at"],
        content_hash=raw_doc["content_hash"],
    )
    return curated_doc.model_dump()


def save_document_bundle(raw_doc: dict) -> Path:
    source_type = raw_doc["source_type"]
    doc_id = raw_doc["doc_id"]

    html_path = RAW_HTML_DIR / source_type / f"{doc_id}.html"
    raw_path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    curated_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"

    save_text(html_path, raw_doc["html"])

    raw_to_save = dict(raw_doc)
    raw_to_save["html_path"] = str(html_path.as_posix())
    raw_to_save.pop("html", None)
    raw_to_save["downloaded_attachments"] = []
    raw_to_save["attachment_text"] = None

    candidate_curated = build_curated_document(raw_to_save, version=1)
    version_result = version_manager.apply_version(source_type, dict(candidate_curated))
    final_curated = version_result["document"]
    decision = version_result["decision"]
    final_curated["change_type"] = decision
    raw_to_save["version"] = final_curated["version"]

    save_json(raw_path, raw_to_save)
    save_json(curated_path, final_curated)

    manifest_writer.write_document_record(raw_to_save)
    manifest_writer.append_jsonl(
        "document_versioning.jsonl",
        {
            "doc_id": doc_id,
            "source_type": source_type,
            "decision": decision,
            "version": final_curated["version"],
            "source_url": final_curated.get("source_url"),
            "mode": "selected_static_pages",
        },
    )

    print(f"[STATIC SAVE OK] doc_id={doc_id} decision={decision} source_type={source_type}")
    return curated_path


def selected_seeds(names: set[str]) -> list[dict]:
    return [
        seed
        for seed in SEED_URLS
        if seed.get("page_kind") in {"seed", "static_page"} and seed.get("name") in names
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl selected static page seeds.")
    parser.add_argument("names", nargs="+", help="Seed names to crawl.")
    parser.add_argument(
        "--skip-image-ocr",
        action="store_true",
        help="Skip OCR for images and collect only HTML text/table content.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = set(args.names)
    seeds = selected_seeds(names)
    missing = sorted(names - {seed["name"] for seed in seeds})
    if missing:
        raise ValueError(f"unknown static seed names: {', '.join(missing)}")

    if args.skip_image_ocr:
        import crawler.extractors.image_text_extractor as image_text_extractor

        image_text_extractor.ImageTextExtractor.extract_many = lambda self, urls: []

    extractor = StaticPageExtractor(allowed_hosts=ALLOWED_HOSTS)
    saved_paths = []
    failed = []

    for seed in seeds:
        try:
            raw_doc = extractor.extract_static_page(
                source_type=seed["source_type"],
                page_url=seed["url"],
            )
            saved_paths.append(save_document_bundle(raw_doc))
        except Exception as exc:
            failed.append((seed["name"], seed["url"], exc))
            print(f"[STATIC SAVE ERROR] name={seed['name']} url={seed['url']} error={exc}")

    print("[STATIC SAVE SUMMARY]")
    for path in saved_paths:
        print(path.as_posix())
    if failed:
        print("[STATIC SAVE FAILED]")
        for name, url, exc in failed:
            print(f"{name}\t{url}\t{exc}")


if __name__ == "__main__":
    main()
