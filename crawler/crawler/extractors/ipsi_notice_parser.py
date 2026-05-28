# crawler/extractors/ipsi_notice_parser.py

from bs4 import BeautifulSoup

from crawler.extractors.board_detail_extractor import BoardDetailExtractor  #board_detail_extractor.py 기능 일부 사용


class IpsiNoticeParser(BoardDetailExtractor):
    """
    입학처 전용 파서
    기본적으로 BoardDetailExtractor를 재사용하되,
    title / content selector를 입학처 구조에 맞게 우선 탐색
    """

    def find_title(self, soup: BeautifulSoup, title_hint: str | None = None) -> str:   #오버라이드
        if title_hint:
            title = self.normalize_text(title_hint)
            if title:
                return title

        selectors = [                                   #입학처 전용 제목 찾는 selector
            ".board-view .title",
            ".view-title",
            ".title",
            "h3",
            "h2",
            "h1",
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

    def find_content_node(self, soup: BeautifulSoup):   #오버라이드
        selectors = [                                   #입학처 전용 본문 찾는 selector
            ".board-view .content",
            ".board-view .cont",
            ".view-content",
            ".contents",
            "#contents",
            ".content",
            "main",
            "main-board-area",
            ".fr-view",
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return node

        return super().find_content_node(soup)          #입학처 전용 탐색 실패 시 부모의 find_content_node로 탐색

    def build_raw_document(
        self,
        source_type: str,
        detail_url: str,
        html: str,
        title_hint: str | None = None,
    ) -> dict:
        raw_doc = super().build_raw_document(source_type, detail_url, html, title_hint=title_hint)
        return raw_doc
