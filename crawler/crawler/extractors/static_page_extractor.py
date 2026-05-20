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
from crawler.utils.attachment_utils import dedupe_attachments_by_url

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}

KST = timezone(timedelta(hours=9))

SOCIAL_LINK_HOSTS = {
    "facebook.com",
    "m.facebook.com",
    "www.facebook.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "x.com",
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
    "pf.kakao.com",
    "blog.naver.com",
}

STATIC_UI_PHRASES = (
    "HOME",
    "Home",
    "로그인",
    "메뉴",
    "공유",
    "페이스북",
    "트위터",
    "카카오톡 공유",
    "URL 복사",
    "프린트",
    "게시물 검색",
    "게시판 목록",
    "이전글",
    "다음글",
    "첨부파일",
    "SNS 영역",
    "게시물 좌측으로 이동",
    "게시물 우측으로 이동",
    "이전 정지 시작 다음",
    "행사사진 More",
    "PDF 다운로드",
    "HWP 다운로드",
    "전체화면 보기",
)

STATIC_STUB_LINES = {
    "HOME",
    "Home",
    "TOP",
    "로그인",
    "메뉴",
    "공유",
    "페이스북",
    "트위터",
    "카카오톡 공유",
    "URL 복사",
    "프린트",
    "게시물 검색",
    "게시판 목록",
    "이전글",
    "다음글",
    "첨부파일",
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

GENERIC_SKIP_LINES = {
    *STATIC_STUB_LINES,
    "구성원 보기",
    "바로가기",
    "홈페이지 새창 열기",
    "본문 바로가기",
    "전체메뉴",
    "로그인",
    "회원가입",
}

GENERIC_SKIP_LINE_PATTERNS = (
    re.compile(r"^(home|top|more|sns|menu|login|share|print)$", re.IGNORECASE),
    re.compile(r"^(로그인|메뉴|공유|페이스북|트위터|카카오톡\s*공유|URL\s*복사|프린트)$", re.IGNORECASE),
    re.compile(r"^(게시물\s*검색|게시판\s*목록|이전글|다음글|첨부파일)$"),
    re.compile(r"^(번호|제목|작성자|작성일|조회수)(\s*[|/]\s*(번호|제목|작성자|작성일|조회수))*$"),
    re.compile(r"^(no\.?|title|writer|date|views?)(\s*[|/]\s*(no\.?|title|writer|date|views?))*$", re.IGNORECASE),
    re.compile(r"^(facebook|twitter|kakao\s*talk|copy\s*url|url\s*copy)$", re.IGNORECASE),
)

BOARD_SHELL_TABLE_PATTERN = re.compile(
    r"^(번호|제목|작성자|작성일|조회수|첨부파일|no\.?|title|writer|date|views?)(\s*[|/]\s*"
    r"(번호|제목|작성자|작성일|조회수|첨부파일|no\.?|title|writer|date|views?))*$",
    re.IGNORECASE,
)

GENERIC_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "main",
    "ol",
    "p",
    "section",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
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

STATIC_NOISE_SELECTORS = [
    "header",
    "footer",
    "nav",
    "aside",
    "script",
    "style",
    "noscript",
    "form[action*='search']",
    ".breadcrumb",
    ".breadcrumbs",
    ".location",
    ".path",
    ".quick",
    ".quickMenu",
    ".quick-menu",
    ".pagination",
    ".paging",
    ".sns",
    ".sns-area",
    ".snsArea",
    ".share",
    ".share-area",
    ".shareArea",
    ".login",
    ".member",
    ".board-search",
    ".boardSearch",
    ".search-box",
    ".searchBox",
    ".board-util",
    ".boardUtil",
    ".board-list",
    ".boardList",
    ".btn-share",
    ".btn-print",
    "[class*='breadcrumb']",
    "[class*='location']",
    "[class*='quick']",
    "[class*='sns']",
    "[class*='share']",
    "[class*='login']",
    "[class*='member']",
    "[class*='paging']",
    "[class*='pagination']",
    "[class*='board-search']",
    "[class*='boardSearch']",
    "[class*='board-util']",
    "[class*='boardUtil']",
    "[class*='quick-menu']",
    "[id*='breadcrumb']",
    "[id*='location']",
    "[id*='quick']",
    "[id*='sns']",
    "[id*='share']",
    "[id*='login']",
    "[id*='paging']",
    "[id*='pagination']",
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

        noise_selectors = list(STATIC_NOISE_SELECTORS)
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
            if BOARD_SHELL_TABLE_PATTERN.fullmatch(normalized):
                removed_stub_lines += 1
                continue
            if any(pattern.search(normalized) for pattern in GENERIC_SKIP_LINE_PATTERNS):
                removed_stub_lines += 1
                continue
            if is_main_page and normalized in {"NOTICE", "PROGRAM", "행사사진", "SNS"}:
                removed_stub_lines += 1
                continue
            lines.append(line)

        cleaned = "\n".join(lines)
        if len(self.normalize_text(cleaned)) < 40 and len(self.normalize_text(text)) >= 120:
            meaningful_lines = []
            for line in text.splitlines():
                normalized = self.normalize_text(line)
                if not normalized or normalized in STATIC_STUB_LINES:
                    continue
                if BOARD_SHELL_TABLE_PATTERN.fullmatch(normalized):
                    continue
                if any(pattern.search(normalized) for pattern in GENERIC_SKIP_LINE_PATTERNS):
                    continue
                meaningful_lines.append(line)
            if len(meaningful_lines) >= 2:
                cleaned = "\n".join(meaningful_lines)
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

    def extract_structured_sections(self, content_node) -> list[dict]:
        if not content_node:
            return []

        admin_sections = self.extract_administration_sections(content_node)
        if admin_sections:
            return admin_sections

        organization_sections = self.extract_organization_sections(content_node)
        if organization_sections:
            return organization_sections

        return self.extract_generic_structured_sections(content_node)

    def extract_administration_sections(self, content_node) -> list[dict]:
        sections = []
        for group_index, group_node in enumerate(content_node.select(".con-box"), start=1):
            title_node = group_node.select_one(".h4-tit")
            group_title = self.normalize_text(title_node.get_text(" ", strip=True)) if title_node else ""
            for item_index, item_node in enumerate(group_node.select(".img-list"), start=1):
                subject_node = item_node.select_one(".subject")
                subject = self.normalize_text(subject_node.get_text(" ", strip=True)) if subject_node else ""
                if not subject:
                    continue

                desc_node = item_node.select_one(".con")
                description = self.normalize_multiline_text(desc_node.get_text("\n", strip=True)) if desc_node else ""
                details = []
                for li in item_node.select(".item-sdot li"):
                    li_copy = BeautifulSoup(str(li), "html.parser").find("li")
                    label_node = li_copy.find("strong") if li_copy else None
                    label = self.normalize_text(label_node.get_text(" ", strip=True)) if label_node else ""
                    if label_node:
                        label_node.extract()
                    value = self.normalize_text(li_copy.get_text(" ", strip=True).lstrip(":").strip()) if li_copy else ""
                    if label and value:
                        details.append(f"{label}: {value}")
                    elif value:
                        details.append(value)

                homepage = ""
                for link in item_node.select("a[href]"):
                    text = self.normalize_text(link.get_text(" ", strip=True))
                    href = link.get("href", "").strip()
                    if text == "바로가기" and href:
                        homepage = href
                        break

                lines = []
                if group_title:
                    lines.append(f"상위조직: {group_title}")
                lines.append(f"기관: {subject}")
                if description:
                    lines.append(f"업무: {description}")
                lines.extend(details)
                if homepage:
                    lines.append(f"홈페이지: {homepage}")

                section_title = " > ".join(part for part in (group_title, subject) if part)
                sections.append(
                    {
                        "section_type": "body",
                        "section_title": section_title or subject,
                        "text": "\n".join(lines).strip(),
                        "metadata": {
                            "structure_type": "administration_office",
                            "group_title": group_title or None,
                            "subject": subject,
                            "group_index": group_index,
                            "item_index": item_index,
                        },
                    }
                )

        return sections

    def extract_organization_sections(self, content_node) -> list[dict]:
        org_node = content_node.select_one(".organization-wrap")
        if not org_node:
            return []

        paths = []

        def direct_label(li: Tag) -> str:
            labels = []
            for child in li.children:
                if not isinstance(child, Tag):
                    continue
                if child.name in {"ul", "ol", "br", "a"}:
                    continue
                text = self.normalize_text(child.get_text(" ", strip=True))
                text = text.replace("홈페이지 새창 열기", "").strip()
                if text:
                    labels.append(text)
            return " / ".join(dict.fromkeys(labels))

        def walk_list(list_node: Tag, parents: list[str]) -> None:
            for li in list_node.find_all("li", recursive=False):
                label = direct_label(li)
                current = parents + ([label] if label else [])
                child_lists = [
                    child
                    for child in li.children
                    if isinstance(child, Tag) and child.name in {"ul", "ol"}
                ]
                if child_lists:
                    if label and current:
                        paths.append(current)
                    for child_list in child_lists:
                        walk_list(child_list, current)
                elif current:
                    paths.append(current)

        for root in org_node.find_all(["ol", "ul"], recursive=False):
            walk_list(root, [])

        lines = []
        seen = set()
        for path in paths:
            line = " > ".join(part for part in path if part)
            if not line or line in seen:
                continue
            seen.add(line)
            lines.append(line)

        if not lines:
            return []

        return [
            {
                "section_type": "body",
                "section_title": "조직도 계층",
                "text": "\n".join(lines),
                "metadata": {
                    "structure_type": "organization_chart",
                    "path_count": len(lines),
                },
            }
        ]

    def is_generic_heading(self, node: Tag) -> bool:
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return True
        class_text = " ".join(node.get("class", [])).lower()
        if not any(token in class_text for token in ("title", "tit", "subject", "heading", "headline")):
            return False
        text = self.normalize_text(node.get_text(" ", strip=True))
        return 2 <= len(text) <= 120

    def direct_text_without_block_children(self, node: Tag) -> str:
        clone = BeautifulSoup(str(node), "html.parser").find(node.name)
        if not clone:
            return ""
        for child in clone.find_all(True, recursive=False):
            if child.name in GENERIC_BLOCK_TAGS:
                child.decompose()
        return self.normalize_text(clone.get_text(" ", strip=True))

    def is_generic_skip_line(self, text: str) -> bool:
        normalized = self.normalize_text(text).strip(" -*:/")
        if not normalized:
            return True
        if normalized in GENERIC_SKIP_LINES:
            return True
        if BOARD_SHELL_TABLE_PATTERN.fullmatch(normalized):
            return True
        if any(pattern.search(normalized) for pattern in GENERIC_SKIP_LINE_PATTERNS):
            return True
        if normalized in {"<", ">", "|"}:
            return True
        if len(normalized) <= 20 and normalized in {"HOME", "TOP", "SNS", "NOTICE", "PROGRAM"}:
            return True
        if normalized in {"PDF 다운로드", "HWP 다운로드"}:
            return True
        return False

    def is_generic_section_marker(self, line: str) -> str | None:
        normalized = self.normalize_text(line).lstrip("- ").strip()
        if not normalized or len(normalized) > 90:
            return None
        if ":" in normalized or re.search(r"\d{4}[.-]\d{2}", normalized):
            return None
        if re.match(r"^[◈○●□■]?\s*제\s*\d+\s*조", normalized):
            return normalized
        if re.match(r"^\d+\s*[.)]\s+\S+", normalized):
            return normalized
        if re.search(r"(개요|소개|안내|절차|방법|기준|목표|문의|시간|노선|위치|유의사항)$", normalized):
            return normalized
        return None

    def render_table_lines(self, table: Tag) -> list[str]:
        lines = ["[TABLE]"]
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"], recursive=False)
            cell_texts = [self.normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
            cell_texts = [text for text in cell_texts if text and not self.is_generic_skip_line(text)]
            if cell_texts:
                lines.append(" | ".join(cell_texts))
        return lines if len(lines) > 1 else []

    def render_generic_lines(self, node: Tag, list_depth: int = 0) -> list[str]:
        if not isinstance(node, Tag):
            return []
        if node.name in {"script", "style", "noscript", "svg", "canvas", "form", "button"}:
            return []
        if node.name == "table":
            return self.render_table_lines(node)
        if self.is_generic_heading(node):
            text = self.normalize_text(node.get_text(" ", strip=True))
            return [f"## {text}"] if text and not self.is_generic_skip_line(text) else []
        if node.name == "li":
            lines = []
            direct_text = self.direct_text_without_block_children(node)
            if direct_text and not self.is_generic_skip_line(direct_text):
                lines.append(f"{'  ' * list_depth}- {direct_text}")
            for child in node.find_all(["ul", "ol"], recursive=False):
                lines.extend(self.render_generic_lines(child, list_depth=list_depth + 1))
            return lines
        if node.name in {"ul", "ol"}:
            lines = []
            for child in node.find_all("li", recursive=False):
                lines.extend(self.render_generic_lines(child, list_depth=list_depth))
            return lines
        if node.name in {"p", "dt", "dd", "figcaption", "blockquote", "address"}:
            text = self.normalize_multiline_text(node.get_text("\n", strip=True))
            return [text] if text and not self.is_generic_skip_line(text) else []

        child_tags = [child for child in node.children if isinstance(child, Tag)]
        has_block_child = any(child.name in GENERIC_BLOCK_TAGS for child in child_tags)
        if not has_block_child:
            text = self.normalize_text(node.get_text(" ", strip=True))
            return [text] if text and not self.is_generic_skip_line(text) else []

        lines = []
        for child in child_tags:
            lines.extend(self.render_generic_lines(child, list_depth=list_depth))
        return lines

    def split_generic_lines_into_sections(self, lines: list[str]) -> list[dict]:
        sections = []
        current_title = "content"
        current_lines = []
        section_index = 1

        def flush() -> None:
            nonlocal section_index, current_lines
            text = self.normalize_multiline_text("\n".join(current_lines))
            if len(text) < 20:
                current_lines = []
                return
            sections.append(
                {
                    "section_type": "body",
                    "section_title": current_title,
                    "text": text,
                    "metadata": {
                        "structure_type": "generic_dom",
                        "section_index": section_index,
                    },
                }
            )
            section_index += 1
            current_lines = []

        for line in lines:
            line = line.strip()
            if not line or self.is_generic_skip_line(line):
                continue
            if line.startswith("## "):
                flush()
                current_title = line.removeprefix("## ").strip() or "content"
                continue
            section_marker = self.is_generic_section_marker(line)
            if section_marker:
                if current_lines:
                    flush()
                current_title = section_marker
                continue
            current_lines.append(line)
        flush()

        if sections:
            return sections

        fallback_text = self.normalize_multiline_text("\n".join(line for line in lines if line.strip()))
        if len(fallback_text) < 20:
            return []
        return [
            {
                "section_type": "body",
                "section_title": "content",
                "text": fallback_text,
                "metadata": {
                    "structure_type": "generic_dom",
                    "section_index": 1,
                },
            }
        ]

    def extract_generic_structured_sections(self, content_node) -> list[dict]:
        lines = self.render_generic_lines(content_node)
        deduped_lines = []
        previous = None
        for line in lines:
            normalized = self.normalize_text(line)
            if not normalized or normalized == previous:
                continue
            deduped_lines.append(line)
            previous = normalized
        return self.split_generic_lines_into_sections(deduped_lines)

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
            if parsed_url.scheme and parsed_url.scheme not in {"http", "https"}:
                continue
            if parsed_url.netloc.lower() in SOCIAL_LINK_HOSTS:
                continue
            url_ext = os.path.splitext(parsed_url.path)[1].lower()
            mode = parse_qs(parsed_url.query).get("mode", [""])[0].lower()
            if url_ext == ".do" and mode != "download":
                continue
            is_attachment = (
                mode == "download"
                or url_ext in file_exts
                or any(href_lower.endswith(ext) for ext in file_exts)
                or bool(re.search(r"(^|/)(download|file)(/|\.|$)", parsed_url.path.lower()))
                or (
                    urlparse(page_url).netloc.lower() == parsed_url.netloc.lower()
                    and (
                        "첨부" in link_text
                        or "다운로드" in link_text
                        or "attachment" in link_text.lower()
                        or "download" in link_text.lower()
                    )
                )
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
        return dedupe_attachments_by_url(attachments)

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
        canonical_page_url = self.canonicalize_url(fetch_result.final_url or page_url)
        html = fetch_result.raw_html
        soup = BeautifulSoup(html, "html.parser")

        title = self.find_title(soup)       # 제목
        is_main_page = self.is_main_page_url(canonical_page_url)
        content_node = self.find_content_node(soup, page_url=canonical_page_url)     # 본문 노드
        raw_text_before_filter = self.normalize_multiline_text(content_node.get_text("\n", strip=True)) if content_node else ""
        raw_text, text_filter_metadata = self.clean_static_text(raw_text_before_filter, is_main_page=is_main_page)
        table_text_before_filter = self.extract_table_text(content_node)
        table_text, table_filter_metadata = self.clean_static_text(table_text_before_filter, is_main_page=is_main_page)
        structured_sections = self.extract_structured_sections(content_node)
        image_urls = self.extract_image_urls(content_node, canonical_page_url)
        image_texts = (
            self.image_text_extractor.extract_many(image_urls)
            if self.enable_image_ocr
            else [
                {"image_index": idx, "image_url": image_url, "image_text": ""}
                for idx, image_url in enumerate(image_urls, start=1)
            ]
        )
        outgoing_links = sorted(
            set(self.extract_internal_links(content_node, canonical_page_url))
            | set(self.extract_navigation_links(soup, canonical_page_url))
        )
        attachments = self.extract_attachments(content_node, canonical_page_url)
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
        doc_id=self.make_doc_id(canonical_page_url),      # 해시기반 id
        source_type=source_type,                # homepage, library, dormitory 등
        page_kind="static_page",
        department=None,
        title=title,
        source_url=canonical_page_url,
        published_at=None,
        updated_at=None,
        raw_text=raw_text,
        normalize=None,
        table_text=table_text,
        attachment_text=None,
        structured_sections=structured_sections,
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
                "structured_section_count": len(structured_sections),
                "text": text_filter_metadata,
                "table": table_filter_metadata,
            },
            "structure": {
                "section_count": len(structured_sections),
                "types": sorted(
                    {
                        section.get("metadata", {}).get("structure_type")
                        for section in structured_sections
                        if section.get("metadata", {}).get("structure_type")
                    }
                ),
            },
        },
    )
        return raw_doc.model_dump()
