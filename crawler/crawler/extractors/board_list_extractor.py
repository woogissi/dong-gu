# crawler/extractors/board_list_extractor.py

import re
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


class BoardListExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def fetch(self, url: str, params: dict | None = None) -> str:
        res = self.session.get(url, params=params, timeout=20)
        res.raise_for_status()
        return res.text

    def extract_article_no(self, url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        article_no = qs.get("articleNo", [None])[0]
        if article_no:
            return article_no

        match = re.search(r"articleNo=(\d+)", url)
        return match.group(1) if match else None

    def parse_rows(self, html: str, base_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = []

        rows = soup.select("table tbody tr")
        if not rows:
            rows = soup.find_all("tr")

        for row in rows:
            a_tag = row.find("a", href=True)
            if not a_tag:
                continue

            href = a_tag["href"]
            full_url = urljoin(base_url, href)

            if "articleNo=" not in full_url:
                continue

            title = a_tag.get_text(" ", strip=True)
            row_text = row.get_text(" ", strip=True)

            date_match = re.search(r"\d{4}-\d{2}-\d{2}", row_text)
            published_at = date_match.group(0) if date_match else None

            items.append({
                "article_no": self.extract_article_no(full_url),
                "title_hint": title,
                "detail_url": full_url,
                "published_at_hint": published_at,
                "row_text": row_text,
            })

        # 중복 제거
        dedup = {}
        for item in items:
            if item["article_no"]:
                dedup[item["article_no"]] = item

        return list(dedup.values())

    def extract_list(self, list_url: str, page_no: int = 1, page_size: int = 10) -> dict:
        params = {
            "article.offset": (page_no - 1) * page_size,
            "articleLimit": page_size,
            "mode": "list",
        }

        html = self.fetch(list_url, params=params)
        items = self.parse_rows(html, list_url)

        return {
            "list_url": list_url,
            "page_no": page_no,
            "page_size": page_size,
            "count": len(items),
            "items": items,
            "html": html,
        }