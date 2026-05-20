from __future__ import annotations

import hashlib
import mimetypes
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, unquote_to_bytes, urlparse

import requests

from crawler.paths import RAW_FILE_DIR
from crawler.utils.http_client import build_retry_session


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class AttachmentDownloader:
    SUPPORTED_EXTENSIONS = {
        ".pdf", ".hwp", ".hwpx", ".doc", ".docx",
        ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".jpg", ".jpeg", ".png",
    }
    QUERY_FILENAME_KEYS = ("filename", "ofn", "sfn", "fileName", "downloadName")
    MAGIC_EXTENSION_SIGNATURES = (
        (b"%PDF", ".pdf"),
        (b"HWP Document File", ".hwp"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ".hwp"),
        (b"PK\x03\x04", ".zip"),
        (b"\xff\xd8\xff", ".jpg"),
        (b"\x89PNG\r\n\x1a\n", ".png"),
    )

    def __init__(
        self,
        base_save_dir: str | Path | None = None,
        max_file_size: int = 100 * 1024 * 1024,
        timeout: tuple[float, float] = (5, 30),
        max_download_attempts: int = 3,
        retry_backoff_factor: float = 0.5,
    ):
        self.session = build_retry_session(HEADERS)
        self.base_save_dir = Path(base_save_dir) if base_save_dir is not None else RAW_FILE_DIR
        self.max_file_size = max_file_size
        self.timeout = timeout
        self.max_download_attempts = max(1, max_download_attempts)
        self.retry_backoff_factor = max(0.0, retry_backoff_factor)
        self.base_save_dir.mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, text: str, max_len: int = 150) -> str:
        text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
        text = re.sub(r"\s+", "_", text).strip("_")
        return text[:max_len] if len(text) > max_len else text

    def supported_extension(self, extension: str | None) -> str:
        if not extension:
            return ""
        normalized = extension.strip().lower()
        return normalized if normalized in self.SUPPORTED_EXTENSIONS else ""

    def supported_suffix(self, text: str | None) -> str:
        if not text:
            return ""
        return self.supported_extension(Path(text).suffix)

    def decode_filename_value(self, value: str | None, charset: str | None = None) -> str | None:
        if not value:
            return None
        value = value.strip().strip('"')
        raw_bytes = unquote_to_bytes(value)
        encodings = [charset] if charset else []
        encodings.extend(["utf-8", "euc-kr", "cp949", "latin1"])
        for encoding in filter(None, encodings):
            try:
                decoded = raw_bytes.decode(encoding)
                if decoded:
                    return decoded.strip()
            except UnicodeDecodeError:
                continue

        decoded = unquote(value).strip()
        for encoding in ("utf-8", "euc-kr", "cp949"):
            try:
                repaired = decoded.encode("latin1").decode(encoding)
                if repaired:
                    return repaired.strip()
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        return decoded

    def extract_filename_from_content_disposition(self, content_disposition: str | None) -> str | None:
        if not content_disposition:
            return None

        match = re.search(r"filename\*\s*=\s*([^']*)''([^;]+)", content_disposition, flags=re.IGNORECASE)
        if match:
            return self.decode_filename_value(match.group(2), charset=match.group(1))

        match = re.search(r'filename\s*=\s*"([^"]+)"', content_disposition, flags=re.IGNORECASE)
        if match:
            return self.decode_filename_value(match.group(1))

        match = re.search(r"filename\s*=\s*([^;]+)", content_disposition, flags=re.IGNORECASE)
        if match:
            return self.decode_filename_value(match.group(1))

        return None

    def extract_filename_from_url_query(self, file_url: str) -> str | None:
        query = parse_qs(urlparse(file_url).query, keep_blank_values=True)
        for key in self.QUERY_FILENAME_KEYS:
            values = query.get(key)
            if not values:
                continue
            decoded = self.decode_filename_value(values[0])
            if decoded:
                return decoded
        return None

    def guess_extension(self, file_url: str, file_name: str) -> str:
        return (
            self.supported_suffix(file_name)
            or self.supported_suffix(unquote(urlparse(file_url).path))
            or ""
        )

    def guess_extension_from_content_type(self, content_type: str | None) -> str:
        if not content_type:
            return ""

        content_type = content_type.split(";")[0].strip().lower()
        custom_map = {
            "application/pdf": ".pdf",
            "application/haansofthwp": ".hwp",
            "application/x-hwp": ".hwp",
            "application/hwp": ".hwp",
            "application/vnd.hancom.hwpx": ".hwpx",
            "application/zip": ".zip",
            "application/x-zip-compressed": ".zip",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.ms-excel": ".xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
            "application/vnd.ms-powerpoint": ".ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        }
        if content_type in custom_map:
            return custom_map[content_type]
        return mimetypes.guess_extension(content_type) or ""

    def guess_extension_from_magic_bytes(self, sample: bytes) -> str:
        for signature, extension in self.MAGIC_EXTENSION_SIGNATURES:
            if sample.startswith(signature) or signature in sample[:4096]:
                return extension
        if b"[Content_Types].xml" in sample[:4096]:
            return ".zip"
        return ""

    def url_path_extension(self, file_url: str) -> str:
        ext = self.supported_suffix(unquote(urlparse(file_url).path))
        return "" if ext == ".do" else ext

    def choose_download_name(
        self,
        file_name: str,
        file_url: str,
        content_disposition: str | None,
    ) -> tuple[str, str | None, str | None]:
        cd_filename = self.extract_filename_from_content_disposition(content_disposition)
        query_filename = self.extract_filename_from_url_query(file_url)
        chosen = cd_filename or query_filename or file_name
        source = "content_disposition" if cd_filename else "url_query" if query_filename else None
        safe_name = self.sanitize_filename(chosen) if chosen else ""
        lower_safe_name = safe_name.lower()
        if lower_safe_name.endswith(".do") or ".do_mode" in lower_safe_name:
            safe_name = ""
        return safe_name, source, cd_filename or query_filename

    def ensure_extension(
        self,
        file_name: str,
        file_url: str,
        content_disposition: str | None,
        content_type: str | None,
    ) -> tuple[str, str, dict]:
        cd_filename = self.extract_filename_from_content_disposition(content_disposition)
        cd_ext = self.supported_suffix(cd_filename)
        query_filename = self.extract_filename_from_url_query(file_url)
        query_ext = self.supported_suffix(query_filename)
        type_ext = self.supported_extension(self.guess_extension_from_content_type(content_type))
        url_ext = self.url_path_extension(file_url)
        current_ext = self.supported_suffix(file_name)
        if Path(file_name).suffix and not current_ext:
            file_name = str(Path(file_name).with_suffix(""))

        final_ext = cd_ext or query_ext or type_ext or url_ext or current_ext
        if final_ext and not Path(file_name).suffix:
            file_name = file_name + final_ext

        metadata = {
            "extension_source": (
                "content_disposition"
                if cd_ext
                else "url_query"
                if query_ext
                else "content_type"
                if type_ext
                else "url_path"
                if url_ext
                else "attachment_name"
                if current_ext
                else None
            ),
            "content_disposition_filename": cd_filename,
            "query_filename": query_filename,
        }
        return file_name, final_ext, metadata

    def _sleep_before_retry(self, attempt: int) -> None:
        if self.retry_backoff_factor <= 0:
            return
        time.sleep(self.retry_backoff_factor * (2 ** (attempt - 1)))

    def _is_retryable_download_error(self, error: Exception) -> bool:
        return isinstance(
            error,
            (
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
                requests.exceptions.Timeout,
            ),
        )

    def download(self, source_type: str, parent_doc_id: str, attachment: dict) -> dict:
        last_error: Exception | None = None
        for attempt in range(1, self.max_download_attempts + 1):
            try:
                return self._download_once(source_type, parent_doc_id, attachment)
            except Exception as error:
                last_error = error
                if attempt >= self.max_download_attempts or not self._is_retryable_download_error(error):
                    raise
                print(
                    f"[ATTACH RETRY] attempt={attempt + 1}/{self.max_download_attempts} "
                    f"url={attachment.get('file_url')} error={error}"
                )
                self._sleep_before_retry(attempt)

        raise last_error if last_error else RuntimeError("attachment download failed")

    def _download_once(self, source_type: str, parent_doc_id: str, attachment: dict) -> dict:
        file_url = attachment["file_url"]
        file_name = attachment["file_name"]
        attachment_index = attachment["attachment_index"]

        res = self.session.get(file_url, timeout=self.timeout, stream=True)
        res.raise_for_status()

        content_disposition = res.headers.get("Content-Disposition")
        content_type = res.headers.get("Content-Type")
        content_length = res.headers.get("Content-Length")
        if content_length and int(content_length) > self.max_file_size:
            raise ValueError(f"Attachment too large: {content_length} bytes url={file_url}")

        safe_name, filename_source, inferred_filename = self.choose_download_name(
            file_name=file_name,
            file_url=file_url,
            content_disposition=content_disposition,
        )
        safe_name = safe_name or f"attachment_{attachment_index}"
        safe_name, ext, extension_metadata = self.ensure_extension(
            file_name=safe_name,
            file_url=file_url,
            content_disposition=content_disposition,
            content_type=content_type,
        )

        normalized_ext = ext.lower() if ext else ""
        if normalized_ext and normalized_ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported attachment extension: {normalized_ext} url={file_url}")
        if content_type and content_type.split(";")[0].strip().lower() == "text/html":
            raise ValueError(f"Attachment content-type mismatch: text/html url={file_url}")

        save_dir = self.base_save_dir / source_type / parent_doc_id
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / safe_name
        temp_path = save_dir / f"{safe_name}.part"

        file_size = 0
        file_hash = hashlib.sha256()
        magic_sample = b""
        try:
            with open(temp_path, "wb") as file:
                for chunk in res.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    file_size += len(chunk)
                    if file_size > self.max_file_size:
                        raise ValueError(f"Attachment too large: {file_size} bytes url={file_url}")
                    file_hash.update(chunk)
                    if len(magic_sample) < 4096:
                        magic_sample += chunk[: 4096 - len(magic_sample)]
                    file.write(chunk)

            if not ext:
                magic_ext = self.supported_extension(self.guess_extension_from_magic_bytes(magic_sample))
                if magic_ext:
                    ext = magic_ext
                    extension_metadata["extension_source"] = "magic_bytes"
                    safe_name = (
                        safe_name + ext
                        if not Path(safe_name).suffix
                        else str(Path(safe_name).with_suffix(ext))
                    )
                    save_path = save_dir / safe_name

            temp_path.replace(save_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        notes = []
        if not ext:
            notes.append("missing_extension")
        if not file_size:
            notes.append("empty_download")

        print(
            f"[ATTACH DEBUG] url={file_url} "
            f"orig_name={file_name} "
            f"final_name={safe_name} "
            f"content_type={content_type} "
            f"content_disposition={content_disposition}"
        )

        return {
            "attachment_index": attachment_index,
            "file_name": file_name,
            "file_url": file_url,
            "file_ext": ext if ext else None,
            "saved_path": str(save_path.as_posix()),
            "file_size": file_size,
            "file_hash_sha256": file_hash.hexdigest(),
            "content_type": content_type,
            "download_filename_source": filename_source,
            "inferred_file_name": inferred_filename,
            "extension_source": extension_metadata.get("extension_source"),
            "note": "; ".join(notes) if notes else None,
        }
