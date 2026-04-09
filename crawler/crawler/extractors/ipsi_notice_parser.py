# crawler/extractors/ipsi_notice_parser.py

from bs4 import BeautifulSoup

from crawler.extractors.board_detail_extractor import BoardDetailExtractor  #board_detail_extractor.py 기능 일부 사용


class IpsiNoticeParser(BoardDetailExtractor):
    """
    입학처 전용 파서
    기본적으로 BoardDetailExtractor를 재사용하되,
    title / content selector를 입학처 구조에 맞게 우선 탐색
    """

    def find_title(self, soup: BeautifulSoup) -> str:   #오버라이드
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

    def build_raw_document(self, source_type: str, detail_url: str, html: str) -> dict:     # 부모의 build_raw_document를 그대로 쓰는데 category12, target_audience만 추가하여 오버라이딩
        raw_doc = super().build_raw_document(source_type, detail_url, html)

        # 입학처 전용 카테고리 기본값
        raw_doc["category_lv1"] = "입학"
        raw_doc["category_lv2"] = "입시공지"

        # target_audience 예시
        raw_doc["target_audience"] = ["신입생", "수험생"]

        return raw_doc