# crawler/extractors/board_detail_extractor.py

import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

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


class BoardDetailExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

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

    def extract_article_no(self, url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        article_no = qs.get("articleNo", [None])[0]
        if article_no:
            return article_no

        match = re.search(r"articleNo=(\d+)", url)
        return match.group(1) if match else None

    def make_doc_id(self, source_type: str, article_no: str) -> str:
        return f"deu_{source_type}_{article_no}"

    def fetch(self, url: str) -> str:
        res = self.session.get(url, timeout=20)
        res.raise_for_status()
        return res.text

    def find_title(self, soup: BeautifulSoup) -> str:
        selectors = [
            "h1", "h2", "h3", "h4",
            ".title", ".view-title",
            ".board_view .title",
            ".board-view .title",
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

    def find_meta(self, html: str) -> dict:
        full_text = self.normalize_text(BeautifulSoup(html, "html.parser").get_text(" ", strip=True))

        date_match = re.search(r"\d{4}-\d{2}-\d{2}", full_text)
        published_at = date_match.group(0) if date_match else None

        views_match = re.search(r"조회수\s*([0-9,]+)", full_text)
        views = int(views_match.group(1).replace(",", "")) if views_match else None

        author = None
        for pattern in [
            r"작성자\s*([가-힣A-Za-z0-9·\-\(\)\s]+)",
            r"부서\s*([가-힣A-Za-z0-9·\-\(\)\s]+)",
        ]:
            m = re.search(pattern, full_text)
            if m:
                author = self.normalize_text(m.group(1))
                break

        return {
            "published_at": published_at,
            "updated_at": None,
            "views": views,
            "author": author,
        }

    def find_content_node(self, soup: BeautifulSoup):
        selectors = [
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
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return node

        # fallback
        best = None
        best_len = 0
        for div in soup.find_all("div"):
            text = self.normalize_text(div.get_text(" ", strip=True))
            if len(text) > best_len:
                best = div
                best_len = len(text)
        return best

    def extract_table_text(self, content_node) -> str:
        if not content_node:
            return ""

        lines = []
        tables = content_node.find_all("table")
        for idx, table in enumerate(tables, start=1):
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

    def extract_attachments(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        results = []
        file_exts = (
            ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
            ".ppt", ".pptx", ".zip", ".jpg", ".jpeg", ".png"
        )

        idx = 1
        for a in soup.find_all("a", href=True):
            href = a["href"]
            full_url = urljoin(page_url, href)
            link_text = self.normalize_text(a.get_text(" ", strip=True))
            href_lower = href.lower()

            is_attachment = (
                "download" in href_lower
                or "file" in href_lower
                or any(href_lower.endswith(ext) for ext in file_exts)
                or "첨부" in link_text
                or "다운로드" in link_text
            )

            if not is_attachment:
                continue

            file_name = link_text if link_text else Path(urlparse(full_url).path).name

            results.append({
                "attachment_index": idx,
                "file_name": file_name,
                "file_url": full_url,
            })
            idx += 1

        # 중복 제거
        unique = []
        seen = set()
        for item in results:
            key = (item["file_name"], item["file_url"])
            if key not in seen:
                seen.add(key)
                unique.append(item)

        return unique

    def build_raw_document(self, source_type: str, detail_url: str, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        article_no = self.extract_article_no(detail_url) or "unknown"
        title = self.find_title(soup)
        meta = self.find_meta(html)
        content_node = self.find_content_node(soup)

        raw_text = ""
        if content_node:
            raw_text = self.normalize_multiline_text(content_node.get_text("\n", strip=True))

        table_text = self.extract_table_text(content_node)
        image_urls = self.extract_image_urls(content_node, detail_url)
        attachments = self.extract_attachments(soup, detail_url)

        doc_id = self.make_doc_id(source_type, article_no)

        return {
            "doc_id": doc_id,
            "parent_doc_id": None,
            "university": "동의대학교",
            "campus": None,
            "source_type": source_type,
            "page_kind": "board_detail",
            "category_lv1": None,
            "category_lv2": None,
            "department": meta["author"],
            "title": title,
            "summary": None,
            "source_url": detail_url,
            "published_at": meta["published_at"],
            "updated_at": meta["updated_at"],
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
            "views": meta["views"],
            "image_urls": image_urls,
            "attachments": attachments,
            "content_hash": self.sha1_text(raw_text or ""),
            "html": html,
        }

    def extract_detail(self, source_type: str, detail_url: str) -> dict:
        html = self.fetch(detail_url)
        return self.build_raw_document(source_type, detail_url, html)