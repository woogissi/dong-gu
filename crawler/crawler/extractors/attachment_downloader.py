# crawler/extractors/attachment_downloader.py

from __future__ import annotations

import mimetypes
import re                                   # 파일 정규식(ex /\: -> _)
from pathlib import Path                    # Path(base) / subdir / filename 형식으로 경로를 만들기 위함
from urllib.parse import urlparse, unquote

import requests                             # 첨부파일 다운을 위한 http 라이브러리


HEADERS = {                                 # 봇차단을 방지하기 위한 USER-Agent 채워주기 용도
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class AttachmentDownloader:
    def __init__(self, base_save_dir: str = "crawler/data/raw/files", max_file_size: int = 100 * 1024 * 1024):
        self.session = requests.Session()                               # 요청 세션
        self.session.headers.update(HEADERS)                            # USER-agent 헤더로 적용
        self.base_save_dir = Path(base_save_dir)                        # 저장 기본 위치를 Path 객체로 바꾼다.
        self.max_file_size = max_file_size
        self.base_save_dir.mkdir(parents=True, exist_ok=True)           # 폴더가 없으면 생성한다. parents=True: 상위 폴더도 같이 생성 exist_ok=True: 이미 있어도 에러 안 냄

    def sanitize_filename(self, text: str, max_len: int = 150) -> str:  # 파일명으로 저장안되는 문자들 _로 변환
        text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
        text = re.sub(r"\s+", "_", text).strip("_")
        return text[:max_len] if len(text) > max_len else text          # 파일명 길 시 150자까지만 저장

    def guess_extension(self, file_url: str, file_name: str) -> str:
        parsed_path = urlparse(file_url).path.lower()                   # url의 path만 뽑는다.

        for ext in [
            ".pdf", ".hwp", ".hwpx", ".doc", ".docx",
            ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".jpg", ".jpeg", ".png"
        ]:
            if parsed_path.endswith(ext) or file_name.lower().endswith(ext):    # url이 확장자로 끝나거나 파일명이 확장자로 끝날시 그 확장자 반환
                return ext

        return ""
    
    def extract_filename_from_content_disposition(self, content_disposition: str | None) -> str | None:
        if not content_disposition:
            return None

        # filename*=UTF-8''...
        match = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", content_disposition, flags=re.IGNORECASE)
        if match:
            return unquote(match.group(1)).strip().strip('"')

        # filename="abc.pdf"
        match = re.search(r'filename\s*=\s*"([^"]+)"', content_disposition, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # filename=abc.pdf
        match = re.search(r"filename\s*=\s*([^;]+)", content_disposition, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip('"')

        return None


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


    def ensure_extension(self, file_name: str, file_url: str, content_disposition: str | None, content_type: str | None) -> tuple[str, str]:
        """
        파일명에 확장자가 없으면
        Content-Disposition -> URL -> Content-Type 순서로 확장자를 보정
        """
        current_ext = Path(file_name).suffix

        cd_filename = self.extract_filename_from_content_disposition(content_disposition)
        cd_ext = Path(cd_filename).suffix if cd_filename else ""

        url_path = unquote(urlparse(file_url).path)
        url_ext = Path(url_path).suffix

        type_ext = self.guess_extension_from_content_type(content_type)

        final_ext = current_ext or cd_ext or url_ext or type_ext

        if not current_ext and final_ext:
            file_name = file_name + final_ext

        return file_name, final_ext

    def download(self, source_type: str, parent_doc_id: str, attachment: dict) -> dict:
        file_url = attachment["file_url"]                                                           #다운로드 주소
        file_name = attachment["file_name"]                                                         #원래 파일명
        attachment_index = attachment["attachment_index"]                                           #몇번째 첨부파일인지

        res = self.session.get(file_url, timeout=30, stream=True)                                   #30초내로 다운로드 응답을 보낸다
        res.raise_for_status()                                                                      #http 상태코드가 200번대가 아니면 에러코드 발생

        content_disposition = res.headers.get("Content-Disposition")
        content_type = res.headers.get("Content-Type")
        content_length = res.headers.get("Content-Length")
        if content_length and int(content_length) > self.max_file_size:
            raise ValueError(f"Attachment too large: {content_length} bytes url={file_url}")

        safe_name = self.sanitize_filename(file_name) or f"attachment_{attachment_index}"           #변환된 파일명 or 몇번째 첨부파일인지로 파일명 설정

        # 확장자 보정
        safe_name, ext = self.ensure_extension(
            file_name=safe_name,
            file_url=file_url,
            content_disposition=content_disposition,
            content_type=content_type,
        )

        save_dir = self.base_save_dir / source_type / parent_doc_id                                 #crawler/data/raw/files / source_type / id 경로로 파일 생성
        save_dir.mkdir(parents=True, exist_ok=True)

        save_path = save_dir / safe_name

        

        file_size = 0
        with open(save_path, "wb") as f:                                                            #첨부파일 바이너리로 저장
            for chunk in res.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                file_size += len(chunk)
                if file_size > self.max_file_size:
                    save_path.unlink(missing_ok=True)
                    raise ValueError(f"Attachment too large: {file_size} bytes url={file_url}")
                f.write(chunk)

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
            "saved_path": str(save_path.as_posix()),                                                #파일 저장 위치
            "file_size": file_size,                                                                 #바이트 단위 파일 크기
            "content_type": content_type,
        }
