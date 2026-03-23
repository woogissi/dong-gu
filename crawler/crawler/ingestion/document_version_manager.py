# crawler/ingestion/document_version_manager.py

import json
from pathlib import Path


class DocumentVersionManager:
    def __init__(self, curated_base_dir: str = "crawler/data/curated/documents"):
        self.curated_base_dir = Path(curated_base_dir)

    def load_existing_document(self, source_type: str, doc_id: str) -> dict | None:
        path = self.curated_base_dir / source_type / f"{doc_id}.json"
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def compare_document(self, source_type: str, new_doc: dict) -> dict:
        existing = self.load_existing_document(source_type, new_doc["doc_id"])

        if not existing:
            return {
                "status": "new",
                "existing_doc": None,
                "new_version": 1,
            }

        old_hash = existing.get("content_hash")
        new_hash = new_doc.get("content_hash")

        if old_hash == new_hash:
            return {
                "status": "unchanged",
                "existing_doc": existing,
                "new_version": existing.get("version", 1),
            }

        return {
            "status": "updated",
            "existing_doc": existing,
            "new_version": existing.get("version", 1) + 1,
        }

    def apply_version(self, source_type: str, new_doc: dict) -> dict:
        result = self.compare_document(source_type, new_doc)
        new_doc["version"] = result["new_version"]
        return {
            "decision": result["status"],
            "document": new_doc,
            "existing_doc": result["existing_doc"],
        }