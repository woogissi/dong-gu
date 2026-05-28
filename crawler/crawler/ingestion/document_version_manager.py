# crawler/ingestion/document_version_manager.py

import json
from pathlib import Path

from crawler.paths import CURATED_DOC_DIR


class DocumentVersionManager:
    def __init__(self, curated_base_dir: str | Path | None = None):       # 여기를 기준으로 기존 문서를 찾는다
        self.curated_base_dir = Path(curated_base_dir) if curated_base_dir is not None else CURATED_DOC_DIR

    def load_existing_document(self, source_type: str, doc_id: str) -> dict | None:     # curated문서에서 같은 id 기준으로 읽는 함수
        path = self.curated_base_dir / source_type / f"{doc_id}.json"
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)                             # 같은 source_type의 같은 id의 문서가 있다면 문서 전체 호출

    def compare_document(self, source_type: str, new_doc: dict) -> dict:                # 새 문서와 기존 문서를 비교해서 상태와 새 버전 번호를 결정하는 함수
        existing = self.load_existing_document(source_type, new_doc["doc_id"])          # 새 문서를 같은 source_type, id를 기준으로 기존 문서를 부른다.

        if not existing:                                                                # 기존문서가 없으면 새 문서로 생성
            return {
                "status": "new",
                "existing_doc": None,
                "new_version": 1,
            }

        old_hash = existing.get("content_hash")         # 기존 문서 해시(내용 비교)
        new_hash = new_doc.get("content_hash")          # 새 문서 해시(내용 비교)

        if old_hash == new_hash:                        # 내용이 같은 경우
            return {                                    # 변경이 없으면(내용 같음) status를 unchanged로 하고 그대로
                "status": "unchanged",
                "existing_doc": existing,
                "new_version": existing.get("version", 1),
            }

        return {                                        # 해시가 다르면(내용 다름) 업데이트 후 version + 1 
            "status": "updated",
            "existing_doc": existing,
            "new_version": existing.get("version", 1) + 1,
        }

    def apply_version(self, source_type: str, new_doc: dict) -> dict:       # compare_document() 결과를 실제 문서에 적용하는 함수
        result = self.compare_document(source_type, new_doc)
        new_doc["version"] = result["new_version"]                          # compare_document() 결과를 새 문서에 적용
        return {
            "decision": result["status"],
            "document": new_doc,
            "existing_doc": result["existing_doc"],
        }
