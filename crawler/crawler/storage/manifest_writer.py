# crawler/storage/manifest_writer.py

import json
from pathlib import Path
from datetime import datetime


class ManifestWriter:
    def __init__(self, base_dir: str = "crawler/data/manifest"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append_jsonl(self, filename: str, record: dict) -> None:
        path = self.base_dir / filename
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def write_document_record(self, raw_doc: dict) -> None:
        self.append_jsonl("documents.jsonl", {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "doc_id": raw_doc["doc_id"],
            "source_type": raw_doc["source_type"],
            "page_kind": raw_doc["page_kind"],
            "title": raw_doc["title"],
            "source_url": raw_doc["source_url"],
            "published_at": raw_doc["published_at"],
            "status": raw_doc["status"],
            "content_hash": raw_doc["content_hash"],
        })

    def write_attachment_record(self, parent_doc_id: str, attachment_doc: dict) -> None:
        self.append_jsonl("attachments.jsonl", {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "doc_id": attachment_doc["doc_id"],
            "parent_doc_id": parent_doc_id,
            "source_url": attachment_doc["source_url"],
            "title": attachment_doc["title"],
            "file_name": attachment_doc.get("file_name"),
            "attachment_index": attachment_doc.get("attachment_index"),
        })

    def write_file_parse_record(self, parent_doc_id: str, file_info: dict, parse_result: dict) -> None:
        self.append_jsonl("file_parsing.jsonl", {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "parent_doc_id": parent_doc_id,
            "file_path": file_info.get("saved_path"),
            "file_url": file_info.get("file_url"),
            "file_name": file_info.get("file_name"),
            "parser_type": parse_result.get("parser_type"),
            "page_count": parse_result.get("page_count"),
            "attachment_text_length": len(parse_result.get("attachment_text") or ""),
        })

    def write_error_record(self, stage: str, message: str, extra: dict | None = None) -> None:
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "stage": stage,
            "message": message,
        }
        if extra:
            payload["extra"] = extra
        self.append_jsonl("errors.jsonl", payload)