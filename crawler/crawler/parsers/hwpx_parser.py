# crawler/parsers/hwpx_parser.py

import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


class HWPXParser:
    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"HWPX file not found: {file_path}")

        paragraphs = []
        raw_xml_files = []

        with zipfile.ZipFile(path, "r") as zf:
            file_list = zf.namelist()

            # HWPX 내부 문서 XML 후보
            xml_candidates = [
                name for name in file_list
                if name.endswith(".xml") and ("Contents" in name or "section" in name.lower() or "content" in name.lower())
            ]

            if not xml_candidates:
                xml_candidates = [name for name in file_list if name.endswith(".xml")]

            for xml_name in xml_candidates:
                raw_xml_files.append(xml_name)

                try:
                    with zf.open(xml_name) as f:
                        tree = ET.parse(f)
                        root = tree.getroot()

                        texts = []
                        for elem in root.iter():
                            if elem.text and elem.text.strip():
                                texts.append(elem.text.strip())

                        if texts:
                            paragraphs.append("\n".join(texts))

                except Exception:
                    # 특정 xml 파싱 실패는 전체 실패로 보지 않음
                    continue

        full_text = "\n\n".join(paragraphs).strip()

        return {
            "file_path": str(path.as_posix()),
            "page_count": None,
            "text": full_text if full_text else None,
            "pages": [],
            "raw_xml_files": raw_xml_files,
        }