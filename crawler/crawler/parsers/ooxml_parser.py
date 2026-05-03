# crawler/parsers/ooxml_parser.py

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


class OOXMLParser:
    def extract_text(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"OOXML file not found: {file_path}")

        raw_xml_files = []
        text_parts = []

        with zipfile.ZipFile(path, "r") as zf:
            shared_strings = self._read_shared_strings(zf)
            for xml_name in self._candidate_xml_files(zf.namelist(), path.suffix.lower()):
                raw_xml_files.append(xml_name)
                try:
                    with zf.open(xml_name) as f:
                        text = self._extract_xml_text(f, shared_strings)
                        if text:
                            text_parts.append(text)
                except Exception:
                    continue

        full_text = self._normalize_text("\n\n".join(text_parts))
        pages = [{"page_no": 1, "text": full_text}] if full_text else []

        return {
            "file_path": str(path.as_posix()),
            "page_count": 1 if full_text else None,
            "text": full_text if full_text else None,
            "pages": pages,
            "raw_xml_files": raw_xml_files,
            "note": "extracted OOXML text from zipped XML parts",
        }

    def _candidate_xml_files(self, names: list[str], ext: str) -> list[str]:
        names = [name for name in names if name.endswith(".xml")]
        if ext == ".xlsx":
            return [
                name
                for name in names
                if name.startswith("xl/worksheets/")
                or name == "xl/sharedStrings.xml"
            ]
        if ext == ".pptx":
            return [name for name in names if name.startswith("ppt/slides/")]
        if ext == ".docx":
            return [name for name in names if name == "word/document.xml" or name.startswith("word/header")]
        return names

    def _read_shared_strings(self, zf: zipfile.ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in zf.namelist():
            return []

        try:
            with zf.open("xl/sharedStrings.xml") as f:
                root = ET.parse(f).getroot()
        except Exception:
            return []

        strings = []
        for si in root.iter():
            if not si.tag.endswith("si"):
                continue
            values = [elem.text.strip() for elem in si.iter() if elem.text and elem.text.strip()]
            if values:
                strings.append(" ".join(values))
        return strings

    def _extract_xml_text(self, file_obj, shared_strings: list[str]) -> str:
        root = ET.parse(file_obj).getroot()
        values = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag == "v" and elem.text and elem.text.strip():
                value = elem.text.strip()
                if shared_strings and value.isdigit():
                    idx = int(value)
                    if 0 <= idx < len(shared_strings):
                        value = shared_strings[idx]
                values.append(value)
            elif tag in {"t", "a:t"} and elem.text and elem.text.strip():
                values.append(elem.text.strip())

        return self._normalize_text("\n".join(values))

    def _normalize_text(self, text: str) -> str:
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
