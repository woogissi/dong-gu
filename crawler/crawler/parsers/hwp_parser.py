from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


class HWPParser:
    """
    HWP 파일 텍스트 추출기.
    LibreOffice 버리고 hwp5txt 사용
    """

    def __init__(self, hwp5txt_path: str | None = None, timeout: int = 60):
        self.hwp5txt_path = (
            hwp5txt_path
            or os.getenv("HWP5TXT_PATH")
            or shutil.which("hwp5txt")
            or "hwp5txt"
        )
        self.timeout = timeout

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _build_result(self, file_path: Path, text: str, note: str) -> dict:
        text = self._normalize_text(text)

        if not text:
            return {
                "file_path": str(file_path.as_posix()),
                "page_count": None,
                "text": None,
                "pages": [],
                "note": "hwp5txt returned empty text",
            }

        pages = [{"page_no": 1, "text": text}]

        return {
            "file_path": str(file_path.as_posix()),
            "page_count": 1,
            "text": text,
            "pages": pages,
            "note": note,
        }

    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"HWP file not found: {file_path}")

        cmd = [self.hwp5txt_path, str(path)]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=self.timeout,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            print(f"[HWP DEBUG] hwp5txt_path={self.hwp5txt_path}")
            print(f"[HWP DEBUG] file_path={path}")
            print(f"[HWP DEBUG] returncode={result.returncode}")
            print(f"[HWP DEBUG] stdout_len={len(result.stdout or '')}")
            print(f"[HWP DEBUG] stderr={result.stderr}")
        except FileNotFoundError:
            return {
                "file_path": str(path.as_posix()),
                "page_count": None,
                "text": None,
                "pages": [],
                "note": f"hwp5txt command not found: {self.hwp5txt_path}",
            }
        except Exception as e:
            return {
                "file_path": str(path.as_posix()),
                "page_count": None,
                "text": None,
                "pages": [],
                "note": f"hwp5txt execution failed: {e}",
            }

        text = self._normalize_text(result.stdout)
        stderr = result.stderr.strip() if result.stderr else ""

        if text:
            return self._build_result(
                file_path=path,
                text=text,
                note="extracted via hwp5txt",
            )

        return {
            "file_path": str(path.as_posix()),
            "page_count": None,
            "text": None,
            "pages": [],
            "note": (
                "hwp5txt extraction failed; "
                f"returncode={result.returncode}; "
                f"stderr={stderr}"
            ),
        }