# crawler/extractors/static_page_extractor.py

import re
import hashlib
import os
from crawler.utils.content_hash import build_content_hash
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, urldefrag

from crawler.schemas.document_models import StaticPageRawDocument
from crawler.extractors.image_text_extractor import ImageTextExtractor

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}

KST = timezone(timedelta(hours=9))


class StaticPageExtractor:
    def __init__(
        self,
        allowed_hosts: set[str] | None = None,
        enable_image_ocr: bool = False,
        timeout: tuple[float, float] = (5, 30),
    ):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.allowed_hosts = allowed_hosts or set()     #허용도메인
        self.enable_image_ocr = enable_image_ocr
        self.timeout = timeout
        self.image_text_extractor = ImageTextExtractor()

    def now_kst_iso(self) -> str:                       #현재 시각을 한국 시간 ISO 문자열로 반환
        return datetime.now(KST).isoformat(timespec="seconds")

    def sha1_text(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def normalize_text(self, text: str) -> str:         #한줄 텍스트 정리
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def clean_title(self, title: str) -> str:
        title = self.normalize_text(title)
        title = re.sub(r"\s*\|\s*동의대학교.*$", "", title)
        title = re.sub(r"\s*-\s*동의대학교.*$", "", title)
        return title.strip()

    def normalize_multiline_text(self, text: str) -> str:       #여러줄 텍스트 정리
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def canonicalize_url(self, url: str) -> str:            #url중복처리를 위한 url 정규화
        url, _ = urldefrag(url)
        return url

    def fetch(self, url: str) -> str:                       #정적 페이지 HTML을 실제로 가져오는 함수
        try:
            res = self.session.get(url, timeout=self.timeout)
            res.raise_for_status()
            return res.text
        except requests.exceptions.SSLError:
            insecure_ssl_hosts = ("lib.deu.ac.kr", "has.deu.ac.kr")
            if any(host in url for host in insecure_ssl_hosts) and os.getenv("CRAWLER_ALLOW_INSECURE_SSL") == "1":
                res = self.session.get(url, timeout=self.timeout, verify=False)       # 도서관 사이트 SSLhandshake failure 해결
                res.raise_for_status()
                return res.text
            raise

    def make_doc_id(self, url: str) -> str:
        return f"static_{self.sha1_text(url)[:16]}"         #정적페이지는 articleNo가 없기 때문에 해시로 id생성

    def find_title(self, soup: BeautifulSoup) -> str:       #제목찾기
        if soup.title:
            title = self.clean_title(soup.title.get_text(" ", strip=True))
            if title and title != "동의대학교 DONG-EUI UNIVERSITY":
                return title

        selectors = [
            "h2",
            "h3",
            ".title",
            ".sub-title",
            ".page-title",
            ".contents-title",
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                text = self.clean_title(node.get_text(" ", strip=True))
                if text and text != "동의대학교 DONG-EUI UNIVERSITY":
                    return text

        return ""

    def remove_noise_nodes(self, node) -> None:         #본문에서 필요없는 거 제거 함수
        if not node:
            return

        noise_selectors = [
            "header",
            "footer",
            "nav",
            "aside",
            "script",
            "style",
            ".breadcrumb",
            ".quick",
            ".quickMenu",
            ".pagination",
            ".sns",
            ".share",
        ]
        for sel in noise_selectors:
            for tag in node.select(sel):
                tag.decompose()

    def find_content_node(self, soup: BeautifulSoup):       #본문 찾기
        selectors = [
            "main",
            "#contents",
            "#content",
            ".contents",
            ".content",
            ".sub-content",
            ".cont",
            "#board_skin",
        ]

        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                cloned = BeautifulSoup(str(node), "html.parser")        #필요없는 정보 제거 전 원본 DOM 노드를 문자열로 만든 뒤 다시 파싱해서 복제본을 만듬
                candidate = cloned.select_one(sel) or cloned
                self.remove_noise_nodes(candidate)                      #필요없는 거 제거
                return candidate

        best = None                                                     #fallback
        best_len = 0
        for div in soup.find_all("div"):                                #제일 긴 div을 본문으로 결정
            text = self.normalize_text(div.get_text(" ", strip=True))
            if len(text) > best_len:
                best = div
                best_len = len(text)

        if best:
            cloned = BeautifulSoup(str(best), "html.parser")            
            node = cloned.find()
            self.remove_noise_nodes(node)                               
            return node

        return soup

    def extract_table_text(self, content_node) -> str:                  # 표 -> 텍스트
        if not content_node:
            return ""

        lines = []
        for idx, table in enumerate(content_node.find_all("table"), start=1):       #각 테이블을 TABLE 1, TABLE 2 로 구분자 추가 후 텍스트 추출
            lines.append(f"[TABLE {idx}]")
            for row in table.find_all("tr"):
                cells = row.find_all(["th", "td"])
                cell_texts = [self.normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
                cell_texts = [c for c in cell_texts if c]
                if cell_texts:
                    lines.append(" | ".join(cell_texts))

        return "\n".join(lines).strip()

    def extract_image_urls(self, content_node, page_url: str) -> list[str]:         # 본문 안 이미지 URL 수집 함수
        if not content_node:
            return []

        urls = []
        for img in content_node.find_all("img", src=True):
            urls.append(urljoin(page_url, img["src"]))

        return sorted(set(urls))        #중복검사

    def extract_internal_links(self, content_node, page_url: str) -> list[str]:     # 본문 안 내부 url 수집
        if not content_node:
            return []

        urls = []
        for a in content_node.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"): # javascript, mailto, tel 이 포함된 링크는 무시
                continue

            full_url = self.canonicalize_url(urljoin(page_url, href))
            host = urlparse(full_url).netloc.lower()                    # url 속 host 추출

            if not self.allowed_hosts or host in self.allowed_hosts:    # 허용 도메인만
                urls.append(full_url)

        return sorted(set(urls))

    def infer_category(self, url: str, title: str) -> tuple[str | None, str | None]:        # 정적 페이지의 카테고리를 URL과 제목 기반으로 추정하는 함수
        combined = f"{url} {title}"

        if "ipsi.deu.ac.kr" in url:
            return "입학", title if title else None
        if "dorm.deu.ac.kr" in url:
            return "대학생활", "기숙사"
        if "lib.deu.ac.kr" in url:
            return "대학생활", "도서관"
        if "셔틀" in combined or "bus" in combined.lower():
            return "대학생활", "셔틀버스"
        if "전화" in combined or "연락처" in combined:
            return "대학생활", "교내연락처"

        return None, None

    def extract_static_page(self, source_type: str, page_url: str) -> dict:         # 외부에서 호출하는 정적 페이지 추출 메인 함수
        html = self.fetch(page_url)
        soup = BeautifulSoup(html, "html.parser")

        title = self.find_title(soup)       # 제목
        content_node = self.find_content_node(soup)     # 본문 노드
        raw_text = self.normalize_multiline_text(content_node.get_text("\n", strip=True)) if content_node else ""
        table_text = self.extract_table_text(content_node)
        image_urls = self.extract_image_urls(content_node, page_url)
        image_texts = (
            self.image_text_extractor.extract_many(image_urls)
            if self.enable_image_ocr
            else [
                {"image_index": idx, "image_url": image_url, "image_text": ""}
                for idx, image_url in enumerate(image_urls, start=1)
            ]
        )
        outgoing_links = self.extract_internal_links(content_node, page_url)
        merged_image_text = "\n\n".join(
            item["image_text"] for item in image_texts if item.get("image_text")
        ).strip()
        hash = build_content_hash(
                    raw_text=raw_text,
                    table_text=table_text,
                    attachment_text=None,
                    image_text=merged_image_text,
                )

        raw_doc = StaticPageRawDocument(
        doc_id=self.make_doc_id(page_url),      # 해시기반 id
        source_type=source_type,                # homepage, library, dormitory 등
        page_kind="static_page",
        department=None,
        title=title,
        source_url=page_url,
        published_at=None,
        updated_at=None,
        raw_text=raw_text,
        normalize=None,
        table_text=table_text,
        attachment_text=None,
        version=1,
        collected_at=self.now_kst_iso(),
        views=None,
        image_urls=image_urls,
        image_texts=image_texts,
        attachments=[],
        outgoing_links=outgoing_links,
        content_hash=hash,
        html=html,
    )
        return raw_doc.model_dump()
