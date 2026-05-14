# crawler/extractors/board_list_extractor.py

import re
from urllib.parse import urljoin, urlparse, parse_qs        # urljoin <- 절대경로 base : https://www.deu.ac.kr/www/deu-notice.do?mode=list + href : ?mode=view&articleNo=123

from bs4 import BeautifulSoup

from crawler.utils.http_client import build_retry_session


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}


class BoardListExtractor:
    def __init__(self, timeout: tuple[float, float] = (5, 30)):
        self.session = build_retry_session(HEADERS)
        self.timeout = timeout

    def fetch(self, url: str, params: dict | None = None) -> str:       #html 가져오기
        res = self.session.get(url, params=params, timeout=self.timeout)
        res.raise_for_status()
        return res.text

    def extract_article_no(self, url: str) -> str | None:               #게시글 번호 뽑기
        parsed = urlparse(url)                                          
        qs = parse_qs(parsed.query)                                     
        for key in ("articleNo", "id", "seq", "post", "post_id", "articleId", "boardId"):
            value = qs.get(key, [None])[0]
            if value:
                return value

        match = re.search(r"(?:articleNo|id|seq|post|post_id|articleId|boardId)=([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else None

    def extraction_strategy_for(self, full_url: str, href: str, onclick: str | None) -> str | None:
        parsed = urlparse(full_url)
        qs = parse_qs(parsed.query)
        if qs.get("articleNo"):
            return "articleNo"
        for key in ("id", "seq", "post", "post_id", "articleId", "boardId"):
            if qs.get(key):
                return f"query_{key}"
        if onclick and re.search(r"(?:view|detail)\s*\(", onclick, flags=re.IGNORECASE):
            return "onclick_parser"
        if re.search(r"\d", href):
            return "regex_fallback"
        return None

    def detail_url_from_link(self, base_url: str, href: str, onclick: str | None = None) -> str:
        if href and href.strip() and href.strip() != "#":
            return urljoin(base_url, href)

        onclick = onclick or ""
        match = re.search(r"(?:view|detail)\s*\(([^)]*)\)", onclick, flags=re.IGNORECASE)
        if not match:
            return urljoin(base_url, href)

        first_arg = match.group(1).split(",")[0].strip().strip("'\"")
        if not first_arg:
            return urljoin(base_url, href)

        if re.match(r"https?://|/", first_arg):
            return urljoin(base_url, first_arg)

        return urljoin(base_url, f"?mode=view&id={first_arg}")

    def parse_rows(self, html: str, base_url: str) -> list[dict]:       #목록에서 각 게시글 뽑기
        soup = BeautifulSoup(html, "html.parser")
        items = []

        rows = soup.select("table tbody tr")                            #테이블형인 게시글 목록 뽑기
        if not rows:
            rows = soup.find_all("tr")

        for row in rows:
            a_tag = row.find("a", href=True)                            #표에서 링크가 있는 데이터 찾기
            if not a_tag:
                continue

            href = a_tag["href"]
            onclick = a_tag.get("onclick") or row.get("onclick")
            full_url = self.detail_url_from_link(base_url, href, onclick)
            extraction_strategy = self.extraction_strategy_for(full_url, href, onclick)

            if not extraction_strategy:
                continue

            title = a_tag.get_text(" ", strip=True)                     #제목 뽑기
            row_text = row.get_text(" ", strip=True)                    #글번호 제목 날짜 작성자 조회수 뽑기

            date_match = re.search(r"\d{4}-\d{2}-\d{2}", row_text)      #날짜 뽑기
            published_at = date_match.group(0) if date_match else None

            items.append({
                "article_no": self.extract_article_no(full_url),
                "title_hint": title,
                "detail_url": full_url,
                "published_at_hint": published_at,
                "row_text": row_text,
                "extraction_strategy": extraction_strategy,
            })

        # 중복 제거
        dedup = {}
        for item in items:
            if item["article_no"]:
                dedup[item["article_no"]] = item                        #같은 article_no가 있으면 마지막 받은걸로 덮어쓰기
            else:
                dedup[item["detail_url"]] = item

        return list(dedup.values())

    def extract_list(self, list_url: str, page_no: int = 1, page_size: int = 10) -> dict:   #목록 추출 메인 함수
        params = {
            "article.offset": (page_no - 1) * page_size,                                    # 몇번째 게시글부터
            "articleLimit": page_size,                                                      # 한페이지에 몇개씩
            "mode": "list",
        }

        html = self.fetch(list_url, params)
        items = self.parse_rows(html, list_url)

        return {
            "list_url": list_url,               #어떤 URL을 요청했는지
            "page_no": page_no,                 #몇 페이지인지
            "page_size": page_size,             #페이지 크기
            "count": len(items),                #몇 개 찾았는지
            "items": items,                     #실제 아이템 목록
            "html": html,                       #원본 HTML
        }
