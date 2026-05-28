# crawler/extractors/board_list_extractor.py

import re
from urllib.parse import (
    parse_qs,
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlsplit,
    urlunsplit,
)

import requests
from bs4 import BeautifulSoup

from crawler.extractors.board_adapters import adapter_for_url


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class BoardListExtractor:
    def __init__(self, timeout: tuple[float, float] = (5, 30), session=None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout

    def fetch(self, url: str, params: dict | None = None) -> str:
        res = self.session.get(url, params=params, timeout=self.timeout)
        res.raise_for_status()
        return res.text

    def is_dap_notice_list_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()

        return (
            parsed.netloc.lower() == "dap.deu.ac.kr"
            and (
                "stdnotice.aspx" in path
                or "stdnotice01.aspx" in path
            )
        )

    def is_dap_notice_detail_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()

        return (
            parsed.netloc.lower() == "dap.deu.ac.kr"
            and "stdnotice02.aspx" in path
        )

    def normalize_dap_list_request(
        self,
        list_url: str,
        page_no: int = 1,
        page_size: int = 10,
    ) -> tuple[str, dict[str, str | int]]:
        parsed = urlsplit(list_url)
        base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        params["PageNo"] = page_no

        # DAP은 보통 page_size 파라미터를 안 쓰지만,
        # seed에 있으면 유지하고 없으면 강제하지 않는다.
        return base_url, params

    def normalize_list_request(
        self,
        list_url: str,
        page_no: int = 1,
        page_size: int = 10,
    ) -> tuple[str, dict[str, str | int]]:
        if self.is_dap_notice_list_url(list_url):
            return self.normalize_dap_list_request(list_url, page_no, page_size)

        parsed = urlsplit(list_url)
        base_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        params.update(
            {
                "article.offset": (page_no - 1) * page_size,
                "articleLimit": page_size,
                "mode": "list",
            }
        )

        return base_url, params

    def extract_article_no(self, url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        notice_mst = qs.get("NoticeMst", [""])[0]
        notice_no = qs.get("NoticeNo", [""])[0]

        if self.is_dap_notice_detail_url(url) and notice_no:
            return f"{notice_mst}_{notice_no}" if notice_mst else notice_no

        return adapter_for_url(url).article_no_from_url(url)

    def extraction_strategy_for(
        self,
        full_url: str,
        href: str,
        onclick: str | None,
    ) -> str | None:
        if self.is_dap_notice_detail_url(full_url):
            return "dap_notice_detail"

        return adapter_for_url(full_url).strategy_for(full_url, href, onclick)

    def detail_url_from_link(
        self,
        base_url: str,
        href: str,
        onclick: str | None = None,
    ) -> str:
        if href:
            full_url = urljoin(base_url, href)

            if self.is_dap_notice_detail_url(full_url):
                return full_url

        if onclick:
            dap_url = self.extract_dap_detail_url_from_onclick(base_url, onclick)
            if dap_url:
                return dap_url

        return adapter_for_url(base_url).normalize_detail_url(
            base_url,
            href,
            onclick,
        ).url

    def extract_dap_detail_url_from_onclick(
        self,
        base_url: str,
        onclick: str | None,
    ) -> str | None:
        if not onclick:
            return None

        parsed_base = urlparse(base_url)
        base_qs = parse_qs(parsed_base.query)

        notice_mst = base_qs.get("NoticeMst", ["001"])[0]
        page_no = base_qs.get("PageNo", ["1"])[0]
        key_field = base_qs.get("KeyField", ["T"])[0]
        key_word = base_qs.get("KeyWord", [""])[0]

        # 예: fnView('85762') / goView('85762') / ViewNotice('85762')
        args = re.findall(r"'([^']+)'|\"([^\"]+)\"", onclick)
        values = [a or b for a, b in args if (a or b)]

        notice_no = None

        for value in values:
            if re.fullmatch(r"\d+", value):
                notice_no = value
                break

        if not notice_no:
            match = re.search(r"NoticeNo\s*=\s*['\"]?(\d+)", onclick, flags=re.IGNORECASE)
            if match:
                notice_no = match.group(1)

        if not notice_no:
            return None

        query = {
            "NoticeMst": notice_mst,
            "NoticeNo": notice_no,
            "KeyField": key_field,
            "KeyWord": key_word,
            "PageNo": page_no,
        }

        return urljoin(
            base_url,
            f"/StdNotice02.aspx?{urlencode(query)}",
        )

    def parse_dap_notice_rows(self, html: str, base_url: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        items = []

        rows = soup.select("table tbody tr")
        if not rows:
            rows = soup.find_all("tr")

        for row in rows:
            row_text = row.get_text(" ", strip=True)

            if not row_text:
                continue

            a_tag = row.find("a", href=True) or row.find("a", onclick=True)

            if not a_tag:
                continue

            href = a_tag.get("href", "") or ""
            onclick = a_tag.get("onclick") or row.get("onclick")

            full_url = self.detail_url_from_link(base_url, href, onclick)

            if not self.is_dap_notice_detail_url(full_url):
                continue

            title = a_tag.get_text(" ", strip=True)
            article_no = self.extract_article_no(full_url)

            date_match = re.search(
                r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})",
                row_text,
            )
            published_at = None

            if date_match:
                y, m, d = date_match.groups()
                published_at = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

            items.append(
                {
                    "article_no": article_no,
                    "title_hint": title,
                    "detail_url": full_url,
                    "published_at_hint": published_at,
                    "row_text": row_text,
                    "extraction_strategy": "dap_notice_detail",
                }
            )

        return self.dedupe_items(items)

    def parse_rows(self, html: str, base_url: str) -> list[dict]:
        if self.is_dap_notice_list_url(base_url):
            return self.parse_dap_notice_rows(html, base_url)

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
            onclick = a_tag.get("onclick") or row.get("onclick")
            full_url = self.detail_url_from_link(base_url, href, onclick)
            extraction_strategy = self.extraction_strategy_for(full_url, href, onclick)

            if not extraction_strategy:
                continue

            title = a_tag.get_text(" ", strip=True)
            row_text = row.get_text(" ", strip=True)

            date_match = re.search(r"\d{4}-\d{2}-\d{2}", row_text)
            published_at = date_match.group(0) if date_match else None

            items.append(
                {
                    "article_no": self.extract_article_no(full_url),
                    "title_hint": title,
                    "detail_url": full_url,
                    "published_at_hint": published_at,
                    "row_text": row_text,
                    "extraction_strategy": extraction_strategy,
                }
            )

        return self.dedupe_items(items)

    def dedupe_items(self, items: list[dict]) -> list[dict]:
        dedup = {}

        for item in items:
            key = item.get("article_no") or item.get("detail_url")
            if not key:
                continue
            dedup[key] = item

        return list(dedup.values())

    def extract_list(
        self,
        list_url: str,
        page_no: int = 1,
        page_size: int = 10,
    ) -> dict:
        base_url, params = self.normalize_list_request(
            list_url,
            page_no,
            page_size,
        )

        html = self.fetch(base_url, params)
        request_url = f"{base_url}?{urlencode(params)}"
        items = self.parse_rows(html, request_url)

        return {
            "list_url": request_url,
            "page_no": page_no,
            "page_size": page_size,
            "count": len(items),
            "items": items,
            "html": html,
        }

    def looks_like_board_list(self, html: str, base_url: str) -> bool:
        items = self.parse_rows(html, base_url)

        if len(items) >= 1:
            return True

        soup = BeautifulSoup(html, "html.parser")

        board_selectors = [
            "table tbody tr a[href]",
            "table tbody tr a[onclick]",
            ".board-list a[href]",
            ".board_list a[href]",
            ".bbs-list a[href]",
            ".list-board a[href]",
            ".board a[href]",
        ]

        for selector in board_selectors:
            nodes = soup.select(selector)

            for node in nodes:
                href = node.get("href", "")
                onclick = node.get("onclick", "")
                text = node.get_text(" ", strip=True)

                if (
                    "articleNo=" in href
                    or "mode=view" in href
                    or "StdNotice02.aspx" in href
                    or "NoticeNo=" in href
                    or "StdNotice02.aspx" in onclick
                    or "NoticeNo" in onclick
                    or "view" in href.lower()
                    or len(text) >= 5
                ):
                    return True

        return False