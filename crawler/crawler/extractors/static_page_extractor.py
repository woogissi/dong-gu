# crawler/extractors/static_page_extractor.py

import re
import hashlib
import os
from crawler.utils.content_hash import build_content_hash
from datetime import datetime, timezone, timedelta
from urllib.parse import parse_qs, urljoin, urlparse, urldefrag

from crawler.schemas.document_models import StaticPageRawDocument
from crawler.extractors.base import BaseExtractor, FetchResult
from crawler.extractors.image_text_extractor import ImageTextExtractor
from crawler.utils.text_quality import is_binary_like_text
from crawler.config.domains import DEPARTMENT_HOSTS

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

STATIC_UI_PHRASES = (
    "게시물 좌측으로 이동",
    "게시물 우측으로 이동",
    "이전 정지 시작 다음",
    "행사사진 More",
    "PDF 다운로드",
    "HWP 다운로드",
    "전체화면 보기",
)

STATIC_STUB_LINES = {
    "More",
    "NOTICE",
    "PROGRAM",
    "SNS",
    "로그인",
    "회원가입",
    "이용문의",
    "PDF 다운로드",
    "HWP 다운로드",
    "전체화면 보기",
}

MAIN_PAGE_EXCLUDE_SELECTORS = [
    ".notice",
    ".notice-list",
    ".latest",
    ".latest-list",
    ".board",
    ".board-list",
    ".program",
    ".program-list",
    ".gallery",
    ".photo",
    ".media",
    ".sns",
    ".login",
    ".member",
    ".popup",
    ".quick",
    "[class*='notice']",
    "[class*='latest']",
    "[class*='board']",
    "[class*='program']",
    "[class*='gallery']",
    "[class*='photo']",
    "[class*='sns']",
    "[class*='login']",
    "[class*='popup']",
    "[id*='notice']",
    "[id*='latest']",
    "[id*='board']",
    "[id*='program']",
    "[id*='gallery']",
    "[id*='sns']",
    "[id*='login']",
]

STATIC_INCLUDE_SELECTORS = [
    ".contents",
    ".content",
    ".sub-content",
    ".cont",
    ".intro",
    ".greeting",
    ".overview",
    ".vision",
    ".purpose",
    ".info",
    "#contents",
    "#content",
    "main",
]


class StaticPageExtractor(BaseExtractor):
    name = "static_page"
    version = "1"

    def __init__(
        self,
        allowed_hosts: set[str] | None = None,
        enable_image_ocr: bool = False,
        timeout: tuple[float, float] = (5, 30),
    ):
        super().__init__(headers=HEADERS, timeout=timeout)
        self.allowed_hosts = allowed_hosts or set()     #허용도메인
        self.enable_image_ocr = enable_image_ocr
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

    def is_main_page_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path:
            return True
        lowered = path.lower()
        if lowered.endswith("index.do"):
            return True
        if lowered in {"main.do", "main"}:
            return True
        if "." not in lowered.rsplit("/", 1)[-1] and len(path.split("/")) <= 2:
            return True
        return False

    def _response_text(self, res: requests.Response, url: str) -> str:
        content_type = res.headers.get("content-type", "").lower()
        if content_type and not any(
            marker in content_type
            for marker in ("text/html", "application/xhtml", "text/plain")
        ):
            raise ValueError(f"non-html static response: url={url} content_type={content_type}")

        text = res.text
        if is_binary_like_text(text[:2000]):
            raise ValueError(f"binary-like static response: url={url} content_type={content_type or 'unknown'}")
        return text

    def fetch_result(self, url: str) -> FetchResult:
        try:
            res = self.session.get(url, timeout=self.timeout)
            res.raise_for_status()
            return FetchResult(
                url=url,
                final_url=res.url,
                status_code=res.status_code,
                headers=dict(res.headers),
                raw_html=self._response_text(res, url),
            )
        except requests.exceptions.SSLError as exc:
            if "has.deu.ac.kr" in url:
                raise requests.exceptions.SSLError(
                    f"SSL verification failed for has.deu.ac.kr; keeping verify=True and skipping url={url}"
                ) from exc
            insecure_ssl_hosts = ("lib.deu.ac.kr",)
            if any(host in url for host in insecure_ssl_hosts) and os.getenv("CRAWLER_ALLOW_INSECURE_SSL") == "1":
                res = self.session.get(url, timeout=self.timeout, verify=False)       # 도서관 사이트 SSLhandshake failure 해결
                res.raise_for_status()
                return FetchResult(
                    url=url,
                    final_url=res.url,
                    status_code=res.status_code,
                    headers=dict(res.headers),
                    raw_html=self._response_text(res, url),
                )
            raise

    def fetch(self, url: str) -> str:                       #정적 페이지 HTML을 실제로 가져오는 함수
        return self.fetch_result(url).raw_html

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

    def remove_noise_nodes(self, node, is_main_page: bool = False) -> None:         #본문에서 필요없는 거 제거 함수
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
        if is_main_page:
            noise_selectors.extend(MAIN_PAGE_EXCLUDE_SELECTORS)

        for sel in noise_selectors:
            for tag in node.select(sel):
                tag.decompose()

    def node_noise_score(self, node) -> int:
        text = self.normalize_text(node.get_text(" ", strip=True))
        score = 0
        for phrase in STATIC_UI_PHRASES:
            if phrase in text:
                score += 3
        for phrase in STATIC_STUB_LINES:
            if phrase in text:
                score += 1
        return score

    def find_content_node(self, soup: BeautifulSoup, page_url: str | None = None):       #본문 찾기
        is_main_page = self.is_main_page_url(page_url or "")
        selectors = [
            *STATIC_INCLUDE_SELECTORS,
            "#board_skin",
        ]

        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                cloned = BeautifulSoup(str(node), "html.parser")        #필요없는 정보 제거 전 원본 DOM 노드를 문자열로 만든 뒤 다시 파싱해서 복제본을 만듬
                candidate = cloned.select_one(sel) or cloned
                self.remove_noise_nodes(candidate, is_main_page=is_main_page)                      #필요없는 거 제거
                return candidate

        best = None                                                     #fallback
        best_score = -1
        for div in soup.find_all("div"):                                #제일 긴 div을 본문으로 결정
            text = self.normalize_text(div.get_text(" ", strip=True))
            if not text:
                continue
            score = len(text) - (self.node_noise_score(div) * 300)
            if score > best_score:
                best = div
                best_score = score

        if best:
            cloned = BeautifulSoup(str(best), "html.parser")            
            node = cloned.find()
            self.remove_noise_nodes(node, is_main_page=is_main_page)                               
            return node

        return soup

    def clean_static_text(self, text: str, is_main_page: bool = False) -> tuple[str, dict]:
        if not text:
            return "", {"removed_ui_patterns": [], "removed_stub_lines": 0}

        removed_patterns = []
        cleaned = text
        for phrase in STATIC_UI_PHRASES:
            if phrase in cleaned:
                removed_patterns.append(phrase)
                cleaned = cleaned.replace(phrase, "\n")

        removed_stub_lines = 0
        lines = []
        for line in cleaned.splitlines():
            normalized = self.normalize_text(line)
            if not normalized:
                continue
            if normalized in STATIC_STUB_LINES:
                removed_stub_lines += 1
                continue
            if is_main_page and normalized in {"NOTICE", "PROGRAM", "행사사진", "SNS"}:
                removed_stub_lines += 1
                continue
            lines.append(line)

        cleaned = "\n".join(lines)
        return self.normalize_multiline_text(cleaned), {
            "removed_ui_patterns": sorted(set(removed_patterns)),
            "removed_stub_lines": removed_stub_lines,
        }

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

    def extract_attachments(self, content_node, page_url: str) -> list[dict]:
        if not content_node:
            return []

        file_exts = (
            ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
            ".ppt", ".pptx", ".zip", ".jpg", ".jpeg", ".png"
        )
        attachments = []
        for idx, a_tag in enumerate(content_node.find_all("a", href=True), start=1):
            href = a_tag["href"].strip()
            href_lower = href.lower()
            link_text = self.normalize_text(a_tag.get_text(" ", strip=True))
            full_url = urljoin(page_url, href)
            parsed_url = urlparse(full_url)
            url_ext = os.path.splitext(parsed_url.path)[1].lower()
            mode = parse_qs(parsed_url.query).get("mode", [""])[0].lower()
            if url_ext == ".do" and mode != "download":
                continue
            is_attachment = (
                "download" in href_lower
                or "file" in href_lower
                or any(href_lower.endswith(ext) for ext in file_exts)
                or "첨부" in link_text
                or "다운로드" in link_text
            )
            if not is_attachment:
                continue
            attachments.append(
                {
                    "attachment_index": len(attachments) + 1,
                    "file_name": link_text or full_url.rsplit("/", 1)[-1],
                    "file_url": full_url,
                }
            )
        return attachments

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

    def first_path_segment(self, url: str) -> str:
        path = urlparse(url).path.strip("/")
        return path.split("/", 1)[0] if path else ""

    def is_navigation_link_allowed(self, page_url: str, link_url: str) -> bool:
        page = urlparse(page_url)
        link = urlparse(link_url)
        link_ext = os.path.splitext(link.path)[1].lower()

        if link.scheme not in {"http", "https"}:
            return False

        if link.netloc.lower() != page.netloc.lower():
            return False

        if link_ext in {".css", ".js", ".ico"}:
            return False

        if link_ext and link_ext != ".do":
            return False

        if page.netloc.lower() in DEPARTMENT_HOSTS:
            page_section = self.first_path_segment(page_url)
            link_section = self.first_path_segment(link_url)
            if page_section and link_section and page_section != link_section:
                return False

        return True

    def extract_navigation_links(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        selectors = [
            "header",
            "nav",
            "#gnb",
            "#mGnb",
            ".gnb",
            ".mbGnb",
        ]
        urls = []
        seen_nodes = set()

        for selector in selectors:
            for node in soup.select(selector):
                node_id = id(node)
                if node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                for a_tag in node.find_all("a", href=True):
                    href = a_tag["href"].strip()
                    if href.startswith(("javascript:", "mailto:", "tel:", "#")):
                        continue

                    full_url = self.canonicalize_url(urljoin(page_url, href))
                    if self.is_navigation_link_allowed(page_url, full_url):
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
        fetch_result = self.fetch_result(page_url)
        html = fetch_result.raw_html
        soup = BeautifulSoup(html, "html.parser")

        title = self.find_title(soup)       # 제목
        is_main_page = self.is_main_page_url(page_url)
        content_node = self.find_content_node(soup, page_url=page_url)     # 본문 노드
        raw_text_before_filter = self.normalize_multiline_text(content_node.get_text("\n", strip=True)) if content_node else ""
        raw_text, text_filter_metadata = self.clean_static_text(raw_text_before_filter, is_main_page=is_main_page)
        table_text_before_filter = self.extract_table_text(content_node)
        table_text, table_filter_metadata = self.clean_static_text(table_text_before_filter, is_main_page=is_main_page)
        image_urls = self.extract_image_urls(content_node, page_url)
        image_texts = (
            self.image_text_extractor.extract_many(image_urls)
            if self.enable_image_ocr
            else [
                {"image_index": idx, "image_url": image_url, "image_text": ""}
                for idx, image_url in enumerate(image_urls, start=1)
            ]
        )
        outgoing_links = sorted(
            set(self.extract_internal_links(content_node, page_url))
            | set(self.extract_navigation_links(soup, page_url))
        )
        attachments = self.extract_attachments(content_node, page_url)
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
        attachments=attachments,
        outgoing_links=outgoing_links,
        content_hash=hash,
        html=html,
        metadata={
            "fetch": self.fetch_metadata(fetch_result),
            "static_extraction_policy": "main_page" if is_main_page else "static_page",
            "quality_filter": {
                "raw_text_length_before": len(raw_text_before_filter),
                "raw_text_length_after": len(raw_text),
                "table_text_length_before": len(table_text_before_filter),
                "table_text_length_after": len(table_text),
                "text": text_filter_metadata,
                "table": table_filter_metadata,
            },
        },
    )
        return raw_doc.model_dump()
