from __future__ import annotations                  # 타입 표기 좀 더 편하게 하기 위함

import shutil
import subprocess                                   # 외부 프로그램 실행용
import tempfile                                     # 임시 폴더용
from pathlib import Path


class HWPParser:
    """
    HWP 파일 텍스트 추출기.

    우선 LibreOffice(soffice) headless 변환을 이용해 TXT/HTML로 변환한 뒤
    텍스트를 읽는다. 변환이 실패하면 명확한 note를 남긴 fallback 결과를 반환한다.
    """

    def __init__(self, soffice_path: str | None = None, timeout: int = 60):
        self.soffice_path = soffice_path or shutil.which("soffice") or "soffice"        # soffice 실행 경로 찾기
        self.timeout = timeout

    def _read_text_file(self, path: Path) -> str:                       # 변환된 TXT 파일을 여러 인코딩으로 읽어보는 함수
        encodings = ["utf-8", "cp949", "euc-kr", "utf-16", "latin-1"]
        last_error: Exception | None = None

        for enc in encodings:                                           # 인코딩 성공할때까지 돌려보기 
            try:
                return path.read_text(encoding=enc)
            except Exception as e:  # pragma: no cover - best effort fallback
                last_error = e
                continue

        if last_error:
            raise last_error
        return ""

    def _convert_with_soffice(self, input_path: Path, out_dir: Path, target: str) -> Path | None:       # LibreOffice를 실제로 실행해서 HWP를 다른 형식으로 변환하는 함수
        cmd = [                         # soffice --headless --convert-to txt:Text --outdir /tmp/xxxxx /path/to/file.hwp 명령의 리스트
            self.soffice_path,
            "--headless",
            "--convert-to",
            target,                     # 무슨 형식으로 변환할지 (우리는 보통 TXT 씀)
            "--outdir",
            str(out_dir),               # 변환 결과 파일이 저장될 폴더
            str(input_path),            # 원본 HWP 파일 경로
        ]

        subprocess.run(                 # 외부 프로그램 실행
            cmd,
            stdout=subprocess.PIPE,     # 표준출력 캡처 
            stderr=subprocess.PIPE,     # 표준에러 캡처
            check=False,                # 명령 실패해도 바로 예외를 던지지 않음
            timeout=self.timeout,
        )

        suffix = "." + target.split(":", 1)[0].split(";", 1)[0]     # target 문자열에서 앞에 '.' 붙여서 확장자로
        candidate = out_dir / f"{input_path.stem}{suffix}"          # sample.hwp, sample, .txt -> /tmp/xxxxx/sample.txt
        return candidate if candidate.exists() else None

    def _parse_txt_output(self, txt_path: Path) -> dict:            # 변환된 TXT 파일을 읽어서 최종 파싱 결과 구조로 바꾸는 함수
        text = self._read_text_file(txt_path).replace("\r\n", "\n").replace("\r", "\n").strip()     # 줄바꿈을 모두 \n으로 통일 후 앞뒤 공백 제거
        if not text:                                                # 변환 실패 시 저장될 구조
            return {
                "page_count": None,
                "text": None,
                "pages": [],
                "note": "LibreOffice converted HWP to TXT, but extracted text was empty",
            }

        raw_pages = [p.strip() for p in text.split("\f")]           # TXT 내 폼피드(\f)가 있으면 페이지 경계로 간주
        pages = [                                                   # 페이지별 딕셔너리 리스트
            {"page_no": idx, "text": page_text}
            for idx, page_text in enumerate(raw_pages, start=1)
            if page_text
        ]

        if pages:
            full_text = "\n\n".join(page["text"] for page in pages).strip()
            page_count = len(pages)
        else:                                                       # 폼피드가 없거나 페이지 구분이 안 되면 1페이지 짜리로 전체 텍스트 그대로 사용
            full_text = text
            pages = [{"page_no": 1, "text": text}]
            page_count = 1

        return {
            "page_count": page_count,
            "text": full_text,
            "pages": pages,
            "note": "extracted via LibreOffice TXT conversion",
        }

    def extract_text(self, file_path: str) -> dict:                 # 메인 함수
        path = Path(file_path)

        if not path.exists():                                       # HWP 파일 자체가 없으면 바로 실패
            raise FileNotFoundError(f"HWP file not found: {file_path}")

        with tempfile.TemporaryDirectory(prefix="hwp_parse_") as tmpdir:    # 변환용 임시 폴더
            tmp_path = Path(tmpdir)                                 # 임시 폴더 경로를 Path로 변환

            txt_path = self._convert_with_soffice(path, tmp_path, "txt:Text")   # LibreOffice 변환시키기
            if txt_path:
                parsed = self._parse_txt_output(txt_path)
                return {
                    "file_path": str(path.as_posix()),
                    "page_count": parsed["page_count"],
                    "text": parsed["text"],
                    "pages": parsed["pages"],
                    "note": parsed["note"],
                }

        return {        # 파일은 있지만 변환 실패했을때 구조
            "file_path": str(path.as_posix()),
            "page_count": None,
            "text": None,
            "pages": [],
            "note": "LibreOffice conversion failed; HWP text extraction unavailable for this file",
        }
