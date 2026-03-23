# crawler/extractors/attachment_downloader.py

import re
from pathlib import Path
from urllib.parse import urlparse

import requests


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class AttachmentDownloader:
    def __init__(self, base_save_dir: str = "crawler/data/raw/files"):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.base_save_dir = Path(base_save_dir)
        self.base_save_dir.mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, text: str, max_len: int = 150) -> str:
        text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
        text = re.sub(r"\s+", "_", text).strip("_")
        return text[:max_len] if len(text) > max_len else text

    def guess_extension(self, file_url: str, file_name: str) -> str:
        parsed_path = urlparse(file_url).path.lower()

        for ext in [
            ".pdf", ".hwp", ".hwpx", ".doc", ".docx",
            ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".jpg", ".jpeg", ".png"
        ]:
            if parsed_path.endswith(ext) or file_name.lower().endswith(ext):
                return ext

        return ""

    def download(self, source_type: str, parent_doc_id: str, attachment: dict) -> dict:
        file_url = attachment["file_url"]
        file_name = attachment["file_name"]
        attachment_index = attachment["attachment_index"]

        ext = self.guess_extension(file_url, file_name)
        safe_name = self.sanitize_filename(file_name) or f"attachment_{attachment_index}{ext}"

        save_dir = self.base_save_dir / source_type / parent_doc_id
        save_dir.mkdir(parents=True, exist_ok=True)

        save_path = save_dir / safe_name

        res = self.session.get(file_url, timeout=30)
        res.raise_for_status()

        with open(save_path, "wb") as f:
            f.write(res.content)

        return {
            "attachment_index": attachment_index,
            "file_name": file_name,
            "file_url": file_url,
            "file_ext": ext if ext else None,
            "saved_path": str(save_path.as_posix()),
            "file_size": len(res.content),
        }