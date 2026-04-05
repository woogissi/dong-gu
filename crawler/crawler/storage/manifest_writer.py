# crawler/storage/manifest_writer.py

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


KST = timezone(timedelta(hours=9))


class ManifestWriter:
    def __init__(self, base_dir: str = "crawler/data/manifest"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def now_kst_iso(self) -> str:           # 현재 시각을 KST ISO 문자열로 반환
        return datetime.now(KST).isoformat(timespec="seconds")

    def append_jsonl(self, file_name: str, record: dict) -> None:       # JSONL은 한 줄에 JSON 하나인 형식이라서 append하기 쉽고 로그 파일로 쓰기 좋고 나중에 줄 단위로 읽기도 쉽다
        path = self.base_dir / file_name
        with open(path, "a", encoding="utf-8") as f:        # 파일을 append 모드로 열고, "a" : 이어쓰기(누적)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")      # record dict를 JSON 문자열로 바꿔 한 줄 쓰고 줄바꿈 추가

    def write_document_record(self, raw_doc: dict) -> None:     # # 문서 저장 기록
        self.append_jsonl("documents.jsonl", {      
            "timestamp": self.now_kst_iso(),    
            "doc_id": raw_doc["doc_id"],
            "source_type": raw_doc["source_type"],
            "page_kind": raw_doc["page_kind"],
            "source_url": raw_doc["source_url"],
            "title": raw_doc.get("title"),
            "published_at": raw_doc.get("published_at"),
            "content_hash": raw_doc.get("content_hash"),
        })

    def write_attachment_record(self, parent_doc_id: str, attachment_doc: dict) -> None:    # 첨부파일 메타 기록
        self.append_jsonl("attachments.jsonl", {
            "timestamp": self.now_kst_iso(),
            "parent_doc_id": parent_doc_id,
            "attachment_doc_id": attachment_doc["doc_id"],
            "file_name": attachment_doc.get("title"),
            "file_url": attachment_doc.get("source_url"),
            "file_ext": attachment_doc.get("file_ext"),
        })

    def write_file_parse_record(self, parent_doc_id: str, downloaded_attachment: dict, parse_result: dict) -> None:     # 첨부파일 파싱 결과 기록
        self.append_jsonl("file_parsing.jsonl", {
            "timestamp": self.now_kst_iso(),
            "parent_doc_id": parent_doc_id,
            "file_path": downloaded_attachment.get("saved_path"),
            "file_url": downloaded_attachment.get("file_url"),
            "file_name": downloaded_attachment.get("file_name"),
            "parser_type": parse_result.get("parser_type"),
            "page_count": parse_result.get("page_count"),
            "attachment_text_length": len(parse_result.get("attachment_text") or ""),
        })

    def write_error_record(self, stage: str, message: str, extra: dict | None = None) -> None: # 파이프라인 전 단계 공통 에러 기록 함수
        self.append_jsonl("errors.jsonl", {
            "timestamp": self.now_kst_iso(),
            "stage": stage,
            "message": message,
            "extra": extra or {},
        })