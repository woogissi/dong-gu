# crawler/extractors/attachment_downloader.py

import re                                   # 파일 정규식(ex /\: -> _)
from pathlib import Path                    # Path(base) / subdir / filename 형식으로 경로를 만들기 위함
from urllib.parse import urlparse

import requests                             # 첨부파일 다운을 위한 http 라이브러리


HEADERS = {                                 # 봇차단을 방지하기 위한 USER-Agent 채워주기 용도
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class AttachmentDownloader:
    def __init__(self, base_save_dir: str = "crawler/data/raw/files"):  # 첨부파일 저장 기본 위치 : crawler/data/raw/files
        self.session = requests.Session()                               # 요청 세션
        self.session.headers.update(HEADERS)                            # USER-agent 헤더로 적용
        self.base_save_dir = Path(base_save_dir)                        # 저장 기본 위치를 Path 객체로 바꾼다.
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

    def download(self, source_type: str, parent_doc_id: str, attachment: dict) -> dict:
        file_url = attachment["file_url"]                                                           #다운로드 주소
        file_name = attachment["file_name"]                                                         #원래 파일명
        attachment_index = attachment["attachment_index"]                                           #몇번째 첨부파일인지

        ext = self.guess_extension(file_url, file_name)                                             #확장자 받기
        safe_name = self.sanitize_filename(file_name) or f"attachment_{attachment_index}{ext}"      #변환된 파일명 or 몇번째 첨부파일인지로 파일명 설정

        save_dir = self.base_save_dir / source_type / parent_doc_id                                 #crawler/data/raw/files / source_type / id 경로로 파일 생성
        save_dir.mkdir(parents=True, exist_ok=True)

        save_path = save_dir / safe_name

        res = self.session.get(file_url, timeout=30)                                                #30초내로 다운로드 응답을 보낸다
        res.raise_for_status()                                                                      #http 상태코드가 200번대가 아니면 에러코드 발생

        with open(save_path, "wb") as f:                                                            #첨부파일 바이너리로 저장
            f.write(res.content)

        return {
            "attachment_index": attachment_index,
            "file_name": file_name,
            "file_url": file_url,
            "file_ext": ext if ext else None,
            "saved_path": str(save_path.as_posix()),                                                #파일 저장 위치
            "file_size": len(res.content),                                                          #바이트 단위 파일 크기
        }