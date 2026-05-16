# crawler/extractors/board_list_extractor.py

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from crawler.utils.http_client import build_retry_session
from crawler.extractors.board_adapters import adapter_for_url


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

    def normalize_list_request(
        self,
        list_url: str,
        page_no: int = 1,
        page_size: int = 10,
    ) -> tuple[str, dict[str, str | int]]:
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

    def extract_article_no(self, url: str) -> str | None:               #게시글 번호 뽑기
        return adapter_for_url(url).article_no_from_url(url)

    def extraction_strategy_for(self, full_url: str, href: str, onclick: str | None) -> str | None:
        return adapter_for_url(full_url).strategy_for(full_url, href, onclick)

    def detail_url_from_link(self, base_url: str, href: str, onclick: str | None = None) -> str:
        return adapter_for_url(base_url).normalize_detail_url(base_url, href, onclick).url

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
        base_url, params = self.normalize_list_request(list_url, page_no, page_size)

        html = self.fetch(base_url, params)
        request_url = f"{base_url}?{urlencode(params)}"
        items = self.parse_rows(html, request_url)

        return {
            "list_url": request_url,            #어떤 URL을 요청했는지
            "page_no": page_no,                 #몇 페이지인지
            "page_size": page_size,             #페이지 크기
            "count": len(items),                #몇 개 찾았는지
            "items": items,                     #실제 아이템 목록
            "html": html,                       #원본 HTML
        }
