# crawler/extractors/static_page_extractor.py

import re
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, urldefrag

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
    def __init__(self, allowed_hosts: set[str] | None = None):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.allowed_hosts = allowed_hosts or set()

    def now_kst_iso(self) -> str:
        return datetime.now(KST).isoformat(timespec="seconds")

    def sha1_text(self, text: str) -> str:
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def normalize_multiline_text(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"\r\n|\r", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def canonicalize_url(self, url: str) -> str:
        url, _ = urldefrag(url)
        return url

    def fetch(self, url: str) -> str:
        res = self.session.get(url, timeout=20)
        res.raise_for_status()
        return res.text

    def make_doc_id(self, url: str) -> str:
        return f"static_{self.sha1_text(url)[:16]}"

    def find_title(self, soup: BeautifulSoup) -> str:
        selectors = [
            "h1",
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
                text = self.normalize_text(node.get_text(" ", strip=True))
                if text:
                    return text

        if soup.title:
            return self.normalize_text(soup.title.get_text(" ", strip=True))

        return ""

    def remove_noise_nodes(self, node) -> None:
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

    def find_content_node(self, soup: BeautifulSoup):
        selectors = [
            "main",
            "#contents",
            "#content",
            ".contents",
            ".content",
            ".sub-content",
            ".cont",
        ]

        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                cloned = BeautifulSoup(str(node), "html.parser")
                candidate = cloned.select_one(sel) or cloned
                self.remove_noise_nodes(candidate)
                return candidate

        best = None
        best_len = 0
        for div in soup.find_all("div"):
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

    def extract_table_text(self, content_node) -> str:
        if not content_node:
            return ""

        lines = []
        for idx, table in enumerate(content_node.find_all("table"), start=1):
            lines.append(f"[TABLE {idx}]")
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
        for img in content_node.find_all("img", src=True):
            urls.append(urljoin(page_url, img["src"]))

        return sorted(set(urls))

    def extract_internal_links(self, content_node, page_url: str) -> list[str]:
        if not content_node:
            return []

        urls = []
        for a in content_node.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("javascript:") or href.startswith("mailto:") or href.startswith("tel:"):
                continue

            full_url = self.canonicalize_url(urljoin(page_url, href))
            host = urlparse(full_url).netloc.lower()

            if not self.allowed_hosts or host in self.allowed_hosts:
                urls.append(full_url)

        return sorted(set(urls))

    def infer_category(self, url: str, title: str) -> tuple[str | None, str | None]:
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

    def extract_static_page(self, source_type: str, page_url: str) -> dict:
        html = self.fetch(page_url)
        soup = BeautifulSoup(html, "html.parser")

        title = self.find_title(soup)
        content_node = self.find_content_node(soup)
        raw_text = self.normalize_multiline_text(content_node.get_text("\n", strip=True)) if content_node else ""
        table_text = self.extract_table_text(content_node)
        image_urls = self.extract_image_urls(content_node, page_url)
        outgoing_links = self.extract_internal_links(content_node, page_url)
        category_lv1, category_lv2 = self.infer_category(page_url, title)

        return {
            "doc_id": self.make_doc_id(page_url),
            "parent_doc_id": None,
            "university": "동의대학교",
            "campus": None,
            "source_type": source_type,
            "page_kind": "static_page",
            "category_lv1": category_lv1,
            "category_lv2": category_lv2,
            "department": None,
            "title": title,
            "summary": None,
            "source_url": page_url,
            "published_at": None,
            "updated_at": None,
            "valid_from": None,
            "valid_to": None,
            "target_audience": [],
            "keywords": [],
            "raw_text": raw_text,
            "clean_text": None,
            "table_text": table_text,
            "attachment_text": None,
            "language": "ko",
            "status": "active",
            "version": 1,
            "collected_at": self.now_kst_iso(),
            "views": None,
            "image_urls": image_urls,
            "attachments": [],
            "outgoing_links": outgoing_links,
            "content_hash": self.sha1_text(raw_text or ""),
            "html": html,
        }