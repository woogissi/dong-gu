# crawler/extractors/board_detail_extractor.py

import re
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from crawler.utils.attachment_utils import dedupe_attachments_by_url
from crawler.utils.content_hash import build_content_hash
from crawler.schemas.document_models import BoardDetailRawDocument
from crawler.extractors.base import BaseExtractor
from crawler.extractors.image_text_extractor import ImageTextExtractor


SOCIAL_LINK_HOSTS = {
    "facebook.com", "m.facebook.com", "www.facebook.com",
    "instagram.com", "www.instagram.com",
    "twitter.com", "x.com",
    "www.youtube.com", "youtube.com", "youtu.be",
    "pf.kakao.com", "blog.naver.com",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    )
}

KST = timezone(timedelta(hours=9))


class BoardDetailExtractor(BaseExtractor):
    name = "board_detail"
    version = "1"

    def __init__(
        self,
        enable_image_ocr: bool = False,
        timeout: tuple[float, float] = (5, 30),
        session=None,
    ):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout
        self.enable_image_ocr = enable_image_ocr
        self.image_text_extractor = ImageTextExtractor()

    def now_kst_iso(self) -> str:
        return datetime.now(KST).isoformat(timespec="seconds")

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

    def is_dap_notice_url(self, url: str) -> bool:
        parsed = urlparse(url)
        return (
            parsed.netloc.lower() == "dap.deu.ac.kr"
            and "stdnotice02.aspx" in parsed.path.lower()
        )

    def extract_article_no(self, url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)

        if self.is_dap_notice_url(url):
            notice_mst = qs.get("NoticeMst", [""])[0]
            notice_no = qs.get("NoticeNo", [""])[0]

            if notice_no and notice_mst:
                return f"{notice_mst}_{notice_no}"
            if notice_no:
                return notice_no

        for key in (
            "articleNo", "id", "seq", "post", "post_id",
            "articleId", "boardId", "NoticeNo",
        ):
            value = qs.get(key, [None])[0]
            if value:
                return value

        match = re.search(
            r"(?:articleNo|id|seq|post|post_id|articleId|boardId|NoticeNo)=([A-Za-z0-9_-]+)",
            url,
            flags=re.IGNORECASE,
        )
        return match.group(1) if match else None

    def build_dap_doc_id(self, source_type: str, detail_url: str) -> str:
        parsed = urlparse(detail_url)
        qs = parse_qs(parsed.query)

        notice_mst = qs.get("NoticeMst", [""])[0]
        notice_no = qs.get("NoticeNo", [""])[0]

        if notice_no and notice_mst:
            return f"{source_type}_notice_{notice_mst}_{notice_no}"

        if notice_no:
            return f"{source_type}_notice_{notice_no}"

        h = hashlib.sha1(detail_url.encode("utf-8")).hexdigest()[:16]
        return f"{source_type}_{h}"

    def make_doc_id(self, source_type: str, detail_url: str, article_no: str | None) -> str:
        if self.is_dap_notice_url(detail_url):
            return self.build_dap_doc_id(source_type, detail_url)

        if article_no and article_no.lower() not in {
            "board_contents_list",
            "contents_list",
            "list",
        }:
            return f"deu_{source_type}_{article_no}"

        h = hashlib.sha1(detail_url.encode("utf-8")).hexdigest()[:16]
        return f"deu_{source_type}_{h}"

    def fetch(self, url: str) -> str:
        return self.fetch_result(url).raw_html

    def clean_title(self, title: str) -> str:
        title = self.normalize_text(title)
        title = re.sub(r"\s*\|\s*동의대학교.*$", "", title)
        title = re.sub(r"\s*-\s*동의대학교.*$", "", title)
        return title.strip()

    def find_title(self, soup: BeautifulSoup, title_hint: str | None = None) -> str:
        if title_hint:
            title = self.clean_title(title_hint)
            if title:
                return title

        selectors = [
            "#CP1_divContents .panel-heading .panel-title",
            "#CP1_divContents h2.panel-title",

            ".panel-heading .panel-title",
            ".panel-title",
            ".view-title",
            ".board-view-title",
            ".board_view .title",
            ".board-view .title",
            ".title",
            "h2",
            "h3",
            "h4",
        ]

        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                text = self.clean_title(node.get_text(" ", strip=True))
                if text and text != "동의대학교 DAP시스템":
                    return text

        if soup.title:
            title = self.clean_title(soup.title.get_text(" ", strip=True))
            if title and title != "동의대학교 DAP시스템":
                return title

        return ""

    def extract_meta_value_from_lines(self, lines: list[str], labels: list[str]) -> str | None:
        label_set = {label.rstrip(":") for label in labels}
        stop_labels = {
            "작성일", "작성자", "부서", "조회수", "첨부파일", "목록",
            "이전글", "다음글", "Name", "Date", "Views", "File",
        }

        for idx, line in enumerate(lines):
            normalized = line.rstrip(":").strip()

            if normalized in label_set:
                for next_line in lines[idx + 1:]:
                    value = self.normalize_text(next_line)
                    if not value:
                        continue
                    if value.rstrip(":") in stop_labels:
                        break
                    return value

            for label in labels:
                if line.startswith(label):
                    value = self.normalize_text(line[len(label):])
                    if value:
                        return value

        return None

    def clean_meta_person(self, text: str | None) -> str | None:
        if not text:
            return None

        text = self.normalize_text(text)
        text = re.split(
            r"\s*(?:조회수|작성일|첨부파일|목록|이전글|다음글|Date|Views|File)\s*",
            text,
        )[0]
        text = text.strip(" :|")
        return text or None

    def normalize_date(self, text: str | None) -> str | None:
        if not text:
            return None

        text = self.normalize_text(text)
        match = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)

        if match:
            y, m, d = match.groups()
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

        return text


    def find_meta(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        lines = [
            line.strip()
            for line in soup.get_text("\n", strip=True).splitlines()
            if line.strip()
        ]
        full_text = self.normalize_text(soup.get_text(" ", strip=True))

        published_at = self.extract_meta_value_from_lines(
            lines,
            ["작성일:", "작성일", "Date"],
        )

        if not published_at:
            date_match = re.search(r"(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})", full_text)
            published_at = date_match.group(1) if date_match else None

        published_at = self.normalize_date(published_at)

        views_value = self.extract_meta_value_from_lines(
            lines,
            ["조회수:", "조회수", "Views"],
        )
        views_match = re.search(r"([0-9,]+)", views_value or "")

        if not views_match:
            views_match = re.search(r"(?:조회수|Views)\s*:?\s*([0-9,]+)", full_text)

        views = int(views_match.group(1).replace(",", "")) if views_match else None

        author = self.clean_meta_person(
            self.extract_meta_value_from_lines(
                lines,
                ["작성자:", "작성자", "부서:", "부서", "Name"],
            )
        )

        metadata = {}

        if published_at:
            metadata["published_at"] = published_at
        if views is not None:
            metadata["views"] = views
        if author:
            metadata["author"] = author
            metadata["department"] = author

        return {
            "published_at": published_at,
            "updated_at": None,
            "views": views,
            "author": author,
            "metadata": metadata,
        }

    def find_content_node(self, soup: BeautifulSoup):
        selectors = [
            "#CP1_divContents .fr-view",
            "#CP1_divContents .board-contents",
            "#CP1_divContents",
            ".board-contents .fr-view",
            ".board-contents",

            ".board_view .cont",
            ".board_view .content",
            ".board-view .cont",
            ".board-view .content",
            ".view_cont",
            ".view-content",
            ".fr-view",
            "#contents",
            "#content",
            ".content",
            ".pagecont",
            ".page",
            "main",
        ]

        for sel in selectors:
            node = soup.select_one(sel)
            if node:
                return node

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
                cell_texts = [
                    self.normalize_text(cell.get_text(" ", strip=True))
                    for cell in cells
                ]
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

    def extract_dap_javascript_attachment_url(self, href: str, page_url: str) -> str | None:
        """
        DAP 게시판의 javascript 다운로드 링크를 실제 URL로 변환한다.
        예:
        javascript:fnFileDown('85762','1')
        javascript:fileDown('...')
        """
        if not href.lower().startswith("javascript:"):
            return None

        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query)

        notice_mst = qs.get("NoticeMst", [""])[0]
        notice_no = qs.get("NoticeNo", [""])[0]

        numbers = re.findall(r"'([^']+)'|\"([^\"]+)\"", href)
        args = [a or b for a, b in numbers if (a or b)]

        # 실제 DAP 다운로드 URL이 다르면 이 부분만 바꾸면 된다.
        if notice_no:
            file_seq = args[-1] if args else "1"
            return urljoin(
                page_url,
                f"/StdNoticeFileDown.aspx?NoticeMst={notice_mst}&NoticeNo={notice_no}&FileSeq={file_seq}",
            )

        return None

    def extract_attachments(self, soup: BeautifulSoup, page_url: str) -> list[dict]:
        results = []

        file_exts = (
            ".pdf", ".hwp", ".hwpx", ".doc", ".docx", ".xls", ".xlsx",
            ".ppt", ".pptx", ".zip", ".jpg", ".jpeg", ".png"
        )

        idx = 1

        # DAP StdNotice02.aspx 첨부파일 영역 우선 처리
        dap_file_links = soup.select(
            "#CP1_divUploadFile a[href], "
            "#CP1_divUploadFile .summary-file[href], "
            "#CP1_divUploadFile a.summary-file[href], "
            "a[id*='lnkbtnUploadFile'][href], "
            "a[href*='mode=download'][href], "
            "a[href*='attachNo='][href]"
        )

        for a in dap_file_links:
            href = a.get("href", "").strip()

            if not href:
                continue

            js_attachment_url = self.extract_dap_javascript_attachment_url(href, page_url)

            if href.lower().startswith("javascript:") and not js_attachment_url:
                continue

            full_url = js_attachment_url or urljoin(page_url, href)

            parsed_url = urlparse(full_url)
            if parsed_url.scheme and parsed_url.scheme not in {"http", "https"}:
                continue
            link_text = self.normalize_text(a.get_text(" ", strip=True))

            file_name = link_text

            if not file_name:
                parsed = urlparse(full_url)
                file_name = Path(parsed.path).name or f"attachment_{idx}"

            results.append({
                "attachment_index": idx,
                "file_name": file_name,
                "file_url": full_url,
            })

            idx += 1

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            if not href:
                continue

            js_attachment_url = self.extract_dap_javascript_attachment_url(href, page_url)

            if href.startswith(("mailto:", "tel:")):
                continue

            if href.lower().startswith("javascript:") and not js_attachment_url:
                continue

            full_url = js_attachment_url or urljoin(page_url, href)

            link_text = self.normalize_text(a.get_text(" ", strip=True))
            href_lower = href.lower()
            parsed_url = urlparse(full_url)

            if parsed_url.scheme and parsed_url.scheme not in {"http", "https"}:
                continue

            if parsed_url.netloc.lower() in SOCIAL_LINK_HOSTS:
                continue

            url_path = parsed_url.path
            url_ext = Path(url_path).suffix.lower()
            qs = parse_qs(parsed_url.query)
            mode = qs.get("mode", [""])[0].lower()

            if url_ext == ".do" and mode != "download":
                continue

            is_attachment = (
                js_attachment_url is not None
                or mode == "download"
                or url_ext in file_exts
                or any(href_lower.endswith(ext) for ext in file_exts)
                or bool(re.search(r"(^|/)(download|file|attach)(/|\.|$)", parsed_url.path.lower()))
                or (
                    urlparse(page_url).netloc.lower() == parsed_url.netloc.lower()
                    and (
                        "첨부" in link_text
                        or "다운로드" in link_text
                        or "file" in link_text.lower()
                        or "attachment" in link_text.lower()
                        or "download" in link_text.lower()
                    )
                )
            )

            if not is_attachment:
                continue

            file_name = link_text if link_text else Path(parsed_url.path).name

            if not file_name:
                file_name = f"attachment_{idx}"

            if not Path(file_name).suffix and url_ext and url_ext != ".do":
                file_name = file_name + url_ext

            results.append({
                "attachment_index": idx,
                "file_name": file_name,
                "file_url": full_url,
            })
            idx += 1

        return dedupe_attachments_by_url(results)

    def remove_meta_from_content(self, text: str, meta: dict) -> str:
        if not text:
            return text

        patterns = []

        if meta.get("published_at"):
            patterns.append(re.escape(f"작성일: {meta['published_at']}"))
            patterns.append(re.escape(f"작성일 {meta['published_at']}"))
            patterns.append(re.escape(f"Date {meta['published_at']}"))

        if meta.get("author"):
            patterns.append(re.escape(f"작성자: {meta['author']}"))
            patterns.append(re.escape(f"부서: {meta['author']}"))
            patterns.append(re.escape(f"Name {meta['author']}"))

        if meta.get("views") is not None:
            patterns.append(re.escape(f"조회수: {meta['views']}"))
            patterns.append(re.escape(f"Views {meta['views']}"))

        patterns.extend([
            r"이전글\s*[^\n]*다음글",
            r"이전글",
            r"다음글",
            r"목록\s*$",
        ])

        cleaned = text

        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE | re.IGNORECASE)

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)

        return cleaned.strip()

    def build_raw_document(
        self,
        source_type: str,
        detail_url: str,
        html: str,
        title_hint: str | None = None,
    ) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        article_no = self.extract_article_no(detail_url)
        doc_id = self.make_doc_id(source_type, detail_url, article_no)

        title = self.find_title(soup, title_hint=title_hint)
        meta = self.find_meta(html)
        content_node = self.find_content_node(soup)

        raw_text = ""

        if content_node:
            raw_text = self.normalize_multiline_text(
                content_node.get_text("\n", strip=True)
            )
            raw_text = self.remove_meta_from_content(raw_text, meta)

        table_text = self.extract_table_text(content_node)
        image_urls = self.extract_image_urls(content_node, detail_url)

        if self.enable_image_ocr:
            image_texts = self.image_text_extractor.extract_many(image_urls)
        else:
            image_texts = [
                {
                    "image_index": idx,
                    "image_url": image_url,
                    "image_text": "",
                }
                for idx, image_url in enumerate(image_urls, start=1)
            ]

        attachments = self.extract_attachments(soup, detail_url)

        merged_image_text = "\n\n".join(
            item["image_text"]
            for item in image_texts
            if item.get("image_text")
        ).strip()

        content_hash = build_content_hash(
            raw_text=raw_text,
            table_text=table_text,
            attachment_text=None,
            image_text=merged_image_text,
        )

        raw_doc = BoardDetailRawDocument(
            doc_id=doc_id,
            source_type=source_type,
            page_kind="board_detail",
            department=meta["author"],
            title=title,
            source_url=detail_url,
            published_at=meta["published_at"],
            updated_at=meta["updated_at"],
            raw_text=raw_text,
            normalize=None,
            table_text=table_text,
            attachment_text=None,
            version=1,
            collected_at=self.now_kst_iso(),
            views=meta["views"],
            image_urls=image_urls,
            image_texts=image_texts,
            attachments=attachments,
            content_hash=content_hash,
            html=html,
            metadata=meta["metadata"],
        )

        return raw_doc.model_dump()

    def extract_detail(
        self,
        source_type: str,
        detail_url: str,
        title_hint: str | None = None,
    ) -> dict:
        fetch_result = self.fetch_result(detail_url)

        raw_doc = self.build_raw_document(
            source_type=source_type,
            detail_url=detail_url,
            html=fetch_result.raw_html,
            title_hint=title_hint,
        )

        raw_doc["metadata"]["fetch"] = self.fetch_metadata(fetch_result)

        return raw_doc