# crawler/parsers/hwpx_parser.py

import zipfile                          # hwpx는 내부적으로 zip 구조
import xml.etree.ElementTree as ET      # XML 파싱용
from pathlib import Path


class HWPXParser:
    def extract_text(self, file_path: str) -> dict:         # 전체 HWPX 파싱의 메인 함수
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"HWPX file not found: {file_path}")

        paragraphs = []
        raw_xml_files = []

        with zipfile.ZipFile(path, "r") as zf:              # HWPX 파일을 읽기 모드로 ZIP처럼 엶
            file_list = zf.namelist()                       # zip 안의 파일을 전부 list로 가져옴

            xml_candidates = [                              # HWPX 내부 문서중 파일명이 XML이고 Contents section content이 들어있으면 우선 후보
                name for name in file_list
                if name.endswith(".xml") and ("Contents" in name or "section" in name.lower() or "content" in name.lower())     
            ]

            if not xml_candidates:                          # 후보가 하나도 없으면 XML 전체를 후보로
                xml_candidates = [name for name in file_list if name.endswith(".xml")]

            for xml_name in xml_candidates:                 # 후보 XML을 하나씩 순회
                raw_xml_files.append(xml_name)              # 순회한 xml 기록

                try:
                    with zf.open(xml_name) as f:            # XML 읽기
                        tree = ET.parse(f)                  # 열린 XML 파일을 파싱해서 XML 트리 객체 생성
                        root = tree.getroot()               # XML의 루트 노드를 가져옴

                        texts = []
                        for elem in root.iter():                    # 루트 아래의 모든 XML 요소(element)를 순회
                            if elem.text and elem.text.strip():
                                texts.append(elem.text.strip())     # 실제 텍스트가 있으면 저장

                        if texts:
                            paragraphs.append("\n".join(texts))

                except Exception:
                    # 특정 xml 파싱 실패는 전체 실패로 보지 않음
                    continue

        full_text = "\n\n".join(paragraphs).strip()                 # 모든 XML 파일에서 모은 텍스트 묶음들을 빈 줄 1개씩 띄워 이어붙여 완성

        return {
            "file_path": str(path.as_posix()),                      # 파일 경로를 POSIX 형식 문자열로
            "page_count": None,                                     # 페이지 수 (지금은 X)
            "text": full_text if full_text else None,               
            "pages": [],                                            # 페이지별 정보 (지금은 x)
            "raw_xml_files": raw_xml_files,                         # 읽은 xml목록
        }