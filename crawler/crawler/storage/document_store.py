# crawler/storage/document_store.py

from __future__ import annotations

import json
from pathlib import Path

from crawler.paths import CURATED_DOC_DIR, RAW_DOC_DIR, RAW_HTML_DIR


class DocumentStore:
    def __init__(
        self,
        raw_html_dir: Path = RAW_HTML_DIR,
        raw_doc_dir: Path = RAW_DOC_DIR,
        curated_doc_dir: Path = CURATED_DOC_DIR,
    ):
        self.raw_html_dir = raw_html_dir
        self.raw_doc_dir = raw_doc_dir
        self.curated_doc_dir = curated_doc_dir

    def save_json(self, path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def raw_html_path(self, source_type: str, doc_id: str) -> Path:
        return self.raw_html_dir / source_type / f"{doc_id}.html"

    def raw_doc_path(self, source_type: str, doc_id: str) -> Path:
        return self.raw_doc_dir / source_type / f"{doc_id}.json"

    def curated_doc_path(self, source_type: str, doc_id: str) -> Path:
        return self.curated_doc_dir / source_type / f"{doc_id}.json"

    def prepare_raw_document(self, raw_doc: dict) -> tuple[dict, Path, Path]:
        source_type = raw_doc["source_type"]
        doc_id = raw_doc["doc_id"]
        html_path = self.raw_html_path(source_type, doc_id)
        raw_path = self.raw_doc_path(source_type, doc_id)

        html = raw_doc.get("raw_html") or raw_doc.get("html") or ""
        self.save_text(html_path, html)

        raw_to_save = dict(raw_doc)
        raw_to_save["html"] = html
        raw_to_save["raw_html"] = html
        raw_to_save["html_path"] = str(html_path.as_posix())
        raw_to_save["raw_html_path"] = str(html_path.as_posix())

        return raw_to_save, raw_path, html_path

    def save_raw_document(self, raw_doc: dict) -> tuple[dict, Path, Path]:
        raw_to_save, raw_path, html_path = self.prepare_raw_document(raw_doc)
        self.save_json(raw_path, raw_to_save)
        return raw_to_save, raw_path, html_path

    def save_curated_document(self, source_type: str, doc_id: str, curated_doc: dict) -> Path:
        curated_path = self.curated_doc_path(source_type, doc_id)
        self.save_json(curated_path, curated_doc)
        return curated_path
