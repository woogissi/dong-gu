# crawler/extractors/board_detail_extractor.py

import re
from crawler.utils.content_hash import build_content_hash       # 해시코드 제작용
from datetime import datetime, timezone, timedelta              # 수집시간용
from pathlib import Path                                        # fallback시 path명을 얻기 위함
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup                                   # html 파싱용

from crawler.schemas.document_models import BoardDetailRawDocument      # JSON 구조
from crawler.extractors.image_text_extractor import ImageTextExtractor  # 이미지 추출

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}

KST = timezone(timedelta(hours=9))                              # 한국 시간대 객체


class BoardDetailExtractor:
    def __init__(
        self,
        enable_image_ocr: bool = False,
        timeout: tuple[float, float] = (5, 30),
    ):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout
        self.enable_image_ocr = enable_image_ocr
        self.image_text_extractor = ImageTextExtractor()

    def now_kst_iso(self) -> str:
        return datetime.now(KST).isoformat(timespec="seconds")  # 현재 시각을 한국 시간 기준 ISO 문자열로 반환한다.


    def normalize_text(self, text: str) -> str:                 # 한 줄용 텍스트 정리 함수
        if not text:
            return ""
        text = text.replace("\xa0", " ")                        # HTML에서 자주 나오는 non-breaking space를 일반 공백으로 바꿈
        text = re.sub(r"\s+", " ", text)                        # 여러 공백/줄바꿈/탭을 전부 한 칸 공백으로 줄임
        return text.strip()

    def normalize_multiline_text(self, text: str) -> str:       # 본문용 정리 함수
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\r\n|\r", "\n", text)                   # 줄바꿈을 없애진 않음
        text = re.sub(r"\n{3,}", "\n\n", text)                  # 너무 많은 빈 줄 줄임
        text = re.sub(r"[ \t]+", " ", text)                     # 탭/공백만 정리
        return text.strip()

    def extract_article_no(self, url: str) -> str | None:       # 게시글 번호 뽑기
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        article_no = qs.get("articleNo", [None])[0]             # ex) mode=view&articleNo=79040 -> mode=view&articleNo=79040
        if article_no:
            return article_no

        match = re.search(r"articleNo=(\d+)", url)
        return match.group(1) if match else None

    def make_doc_id(self, source_type: str, article_no: str) -> str:    # 문서 고유 ID 생성 = source_type + article_no
        return f"deu_{source_type}_{article_no}"

    def fetch(self, url: str) -> str:                           # 상세 페이지 html을 그대로 가져옴
        res = self.session.get(url, timeout=self.timeout)
        res.raise_for_status()
        return res.text

    def clean_title(self, title: str) -> str:
        title = self.normalize_text(title)
        title = re.sub(r"\s*\|\s*동의대학교.*$", "", title)
        title = re.sub(r"\s*-\s*동의대학교.*$", "", title)
        return title.strip()

    def find_title(self, soup: BeautifulSoup, title_hint: str | None = None) -> str:           # 제목 찾기
        if title_hint:
            title = self.clean_title(title_hint)
            if title:
                return title

        if soup.title:
            title = self.clean_title(soup.title.get_text(" ", strip=True))
            if title and title != "동의대학교 DONG-EUI UNIVERSITY":
                return title

        selectors = [                                           # selectors 목록
            ".title", ".view-title",
            ".board_view .title",
            ".board-view .title",
            "h2", "h3", "h4",
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:                                                    # 일치하는 selectors가 있고, 비어있지 않으면 text 반환
                text = self.clean_title(node.get_text(" ", strip=True))
                if text and text != "동의대학교 DONG-EUI UNIVERSITY":
                    return text

        return ""                                                        # 다 없으면 빈 텍스트 반환

    def extract_meta_value_from_lines(self, lines: list[str], labels: list[str]) -> str | None:
        label_set = {label.rstrip(":") for label in labels}
        stop_labels = {"작성일", "작성자", "부서", "조회수", "첨부파일", "목록", "이전글", "다음글"}

        for idx, line in enumerate(lines):
            normalized = line.rstrip(":").strip()
            if normalized in label_set:
                for next_line in lines[idx + 1:]:
                    value = self.normalize_text(next_line)
                    if not value:
                        continue
                    if value.rstrip(":") in stop_labels:
                        break
                    return value

            for label in labels:
                if line.startswith(label):
                    value = self.normalize_text(line[len(label):])
                    if value:
                        return value

        return None

    def clean_meta_person(self, text: str | None) -> str | None:
        if not text:
            return None
        text = self.normalize_text(text)
        text = re.split(r"\s*(?:조회수|작성일|첨부파일|목록|이전글|다음글)\s*", text)[0]
        text = text.strip(" :")
        return text or None

    def find_meta(self, html: str) -> dict:                              # 게시글 메타데이터 추출       
        soup = BeautifulSoup(html, "html.parser")
        lines = [line.strip() for line in soup.get_text("\n", strip=True).splitlines() if line.strip()]
        full_text = self.normalize_text(soup.get_text(" ", strip=True))   # 전체 html을 한줄로

        published_at = self.extract_meta_value_from_lines(lines, ["작성일:", "작성일"])
        if not published_at:
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", full_text)
            published_at = date_match.group(1) if date_match else None

        views_value = self.extract_meta_value_from_lines(lines, ["조회수:", "조회수"])
        views_match = re.search(r"([0-9,]+)", views_value or "")
        if not views_match:
            views_match = re.search(r"조회수\s*:?\s*([0-9,]+)", full_text)
        views = int(views_match.group(1).replace(",", "")) if views_match else None

        author = self.clean_meta_person(
            self.extract_meta_value_from_lines(lines, ["작성자:", "작성자", "부서:", "부서"])
        )

        # 추가 메타데이터 추출
        metadata = {}
        if published_at:
            metadata["published_at"] = published_at
        if views is not None:
            metadata["views"] = views
        if author:
            metadata["author"] = author
            metadata["department"] = author  # department로도 저장

        return {            # 본문데이터 구성
            "published_at": published_at,
            "updated_at": None,
            "views": views,
            "author": author,
            "metadata": metadata,
        }

    def find_content_node(self, soup: BeautifulSoup):                   # 본문 DOM 노드 찾기
        selectors = [                                                   # selector
            ".board_view .cont",
            ".board_view .content",
            ".board-view .cont",
            ".board-view .content",
            ".view_cont",
            ".view-content",
            "#contents",
            "#content",
            ".content",
            "main",
            ".fr-view",
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return node

        # fallback
        best = None
        best_len = 0
        for div in soup.find_all("div"):                                # selector에서 못 찾으면 div중에서 가장 긴 div를 본문으로 체텍
            text = self.normalize_text(div.get_text(" ", strip=True))
            if len(text) > best_len:
                best = div
                best_len = len(text)
        return best

    def extract_table_text(self, content_node) -> str:
        if not content_node:
            return ""

        lines = []
        tables = content_node.find_all("table")                         # 본문에서 table을 찾기(표)
        for idx, table in enumerate(tables, start=1):
            lines.append(f"[TABLE {idx}]")                              # 각 테이블을 TABLE 1, TABLE 2 로 구분자 추가 후 텍스트 추출
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                cell_texts = [self.normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
                cell_texts = [c for c in cell_texts if c]
                if cell_texts:
                    lines.append(" | ".join(cell_texts))

        return "\n".join(lines).strip()

    def extract_image_urls(self, content_node, page_url: str) -> list[str]:
        if not content_node:
            return []

        urls = []
        for img in content_node.find_all("img", src=True):              # src = True인 이미지 찾기
            urls.append(urljoin(page_url, img["src"]))                  # urljoin으로 절대 URL화(상대경로 예방)

        return sorted(set(urls))                                        # set으로 정렬

    def extract_attachments(self, soup: BeautifulSoup, page_url: str) -> list[dict]:    # 첨부파일 링크 추출
        results = []
        file_exts = (
            ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
            ".ppt", ".pptx", ".zip", ".jpg", ".jpeg", ".png"
        )

        idx = 1
        for a in soup.find_all("a", href=True):                         # 링크 전체 탐색
            href = a["href"]                                           
            full_url = urljoin(page_url, href)
            link_text = self.normalize_text(a.get_text(" ", strip=True))
            href_lower = href.lower()

            is_attachment = (                                           # 링크에 download or file or file_exts 가 있거나 링크 텍스트에 첨부 or 다운로드가 있으면 첨부파일로 분류
                "download" in href_lower
                or "file" in href_lower
                or any(href_lower.endswith(ext) for ext in file_exts)
                or "첨부" in link_text
                or "다운로드" in link_text
            )

            if not is_attachment:
                continue

            file_name = link_text if link_text else Path(urlparse(full_url).path).name  # 링크 텍스트가 없으면 path를 이름으로

             # 🔥 확장자 보정
            url_path = urlparse(full_url).path
            url_ext = Path(url_path).suffix

            if not Path(file_name).suffix and url_ext:
                file_name = file_name + url_ext

            results.append({                #첨부파일 구성
                "attachment_index": idx,
                "file_name": file_name,
                "file_url": full_url,
            })
            idx += 1

        # 중복 제거
        unique = []
        seen = set()
        for item in results:
            key = (item["file_name"], item["file_url"])         # file_name과 file_url 기준으로 중복검사
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    def remove_meta_from_content(self, text: str, meta: dict) -> str:
        """본문 텍스트에서 메타데이터 관련 텍스트를 제거"""
        if not text:
            return text
        
        # 메타데이터 값들을 텍스트에서 제거
        patterns = []
        if meta.get("published_at"):
            patterns.append(re.escape(f"작성일: {meta['published_at']}"))
            patterns.append(re.escape(f"작성일 {meta['published_at']}"))
        if meta.get("author"):
            patterns.append(re.escape(f"작성자: {meta['author']}"))
            patterns.append(re.escape(f"부서: {meta['author']}"))
        if meta.get("views") is not None:
            patterns.append(re.escape(f"조회수: {meta['views']}"))
        
        # 이전글/다음글 패턴
        patterns.extend([
            r"이전글\s*[^\n]*다음글",
            r"이전글",
            r"다음글",
        ])
        
        cleaned = text
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
        
        # 연속된 공백/줄바꿈 정리
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        return cleaned.strip()

    def build_raw_document(
        self,
        source_type: str,
        detail_url: str,
        html: str,
        title_hint: str | None = None,
    ) -> dict:     # 최종 조립 함수
        soup = BeautifulSoup(html, "html.parser")                                           # html 파싱
        article_no = self.extract_article_no(detail_url) or "unknown"                       # article_no
        title = self.find_title(soup, title_hint=title_hint)                                                       # 제목 
        meta = self.find_meta(html)                                                         # 메타
        content_node = self.find_content_node(soup)                                         # 본문 노드

        raw_text = ""
        if content_node:
            raw_text = self.normalize_multiline_text(content_node.get_text("\n", strip=True))   # 본문 텍스트
            raw_text = self.remove_meta_from_content(raw_text, meta)  # 메타데이터 제거

        table_text = self.extract_table_text(content_node)                  # 표텍스트
        image_urls = self.extract_image_urls(content_node, detail_url)      # 이미지 url
        image_texts = (
            self.image_text_extractor.extract_many(image_urls)
            if self.enable_image_ocr
            else [
                {"image_index": idx, "image_url": image_url, "image_text": ""}
                for idx, image_url in enumerate(image_urls, start=1)
            ]
        )
        attachments = self.extract_attachments(soup, detail_url)            # 첨부파일

        merged_image_text = "\n\n".join(
            item["image_text"] for item in image_texts if item.get("image_text")
        ).strip()

        doc_id = self.make_doc_id(source_type, article_no)
        hash = build_content_hash(
                    raw_text=raw_text,
                    table_text=table_text,
                    attachment_text=None,
                    image_text=merged_image_text,

                )


        raw_doc = BoardDetailRawDocument(
            doc_id=doc_id,
            source_type=source_type,                # notice, academic_notice 등
            page_kind="board_detail",
            department=meta["author"],              # 작성자/부서
            title=title,
            source_url=detail_url,                  # 상세 URL
            published_at=meta["published_at"],      # 작성일
            updated_at=meta["updated_at"],
            raw_text=raw_text,
            normalize=None,
            table_text=table_text,
            attachment_text=None,
            version=1,
            collected_at=self.now_kst_iso(),
            views=meta["views"],
            image_urls=image_urls,
            image_texts=image_texts,
            attachments=attachments,
            content_hash=hash,        # 본문 해시
            html=html,
            metadata=meta["metadata"],
        )

        return raw_doc.model_dump()

    def extract_detail(self, source_type: str, detail_url: str, title_hint: str | None = None) -> dict:
        html = self.fetch(detail_url)
        return self.build_raw_document(source_type, detail_url, html, title_hint=title_hint)
