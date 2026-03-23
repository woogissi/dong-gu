# crawler/extractors/ipsi_notice_parser.py

from bs4 import BeautifulSoup

from crawler.extractors.board_detail_extractor import BoardDetailExtractor


class IpsiNoticeParser(BoardDetailExtractor):
    """
    입학처 전용 파서
    기본적으로 BoardDetailExtractor를 재사용하되,
    title / content selector를 입학처 구조에 맞게 우선 탐색
    """

    def find_title(self, soup: BeautifulSoup) -> str:
        selectors = [
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

    def find_content_node(self, soup: BeautifulSoup):
        selectors = [
            ".board-view .content",
            ".board-view .cont",
            ".view-content",
            ".contents",
            "#contents",
            ".content",
            "main",
        ]
        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return node

        return super().find_content_node(soup)

    def build_raw_document(self, source_type: str, detail_url: str, html: str) -> dict:
        raw_doc = super().build_raw_document(source_type, detail_url, html)

        # 입학처 전용 카테고리 기본값
        raw_doc["category_lv1"] = "입학"
        raw_doc["category_lv2"] = "입시공지"

        # target_audience 예시
        raw_doc["target_audience"] = ["신입생", "수험생"]

        return raw_doc