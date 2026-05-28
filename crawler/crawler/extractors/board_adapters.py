from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse


DETAIL_QUERY_KEYS = ("articleNo", "id", "seq", "post", "post_id", "articleId", "boardId", "nttId")


@dataclass(frozen=True)
class DetailUrlCandidate:
    url: str
    strategy: str | None
    article_no: str | None


class GenericBoardAdapter:
    name = "generic"

    def normalize_detail_url(self, base_url: str, href: str, onclick: str | None = None) -> DetailUrlCandidate:
        raw_href = (href or "").strip()
        if raw_href and raw_href != "#":
            url = urljoin(base_url, raw_href)
        else:
            url = self._url_from_onclick(base_url, onclick or "")

        url = self._canonicalize(url)
        strategy = self.strategy_for(url, raw_href, onclick)
        return DetailUrlCandidate(url=url, strategy=strategy, article_no=self.article_no_from_url(url))

    def _url_from_onclick(self, base_url: str, onclick: str) -> str:
        match = re.search(r"(?:view|detail|goView|fnView)\s*\(([^)]*)\)", onclick, flags=re.IGNORECASE)
        if not match:
            return urljoin(base_url, "")

        args = [part.strip().strip("'\"") for part in match.group(1).split(",")]
        first_arg = next((arg for arg in args if arg), "")
        if not first_arg:
            return urljoin(base_url, "")
        if re.match(r"https?://|/", first_arg):
            return urljoin(base_url, first_arg)

        key = "articleNo" if first_arg.isdigit() else "id"
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query["mode"] = ["view"]
        query[key] = [first_arg]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

    def _canonicalize(self, url: str) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        normalized_query = urlencode(sorted(query.items()), doseq=True)
        return urlunparse(parsed._replace(fragment="", query=normalized_query))

    def article_no_from_url(self, url: str) -> str | None:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        for key in DETAIL_QUERY_KEYS:
            value = qs.get(key, [None])[0]
            if value:
                return value

        path_match = re.search(r"/(?:view|detail|article|post)/([A-Za-z0-9_-]+)", parsed.path, flags=re.IGNORECASE)
        if path_match:
            return path_match.group(1)

        query_match = re.search(
            r"(?:articleNo|id|seq|post|post_id|articleId|boardId|nttId)=([A-Za-z0-9_-]+)",
            url,
            flags=re.IGNORECASE,
        )
        return query_match.group(1) if query_match else None

    def strategy_for(self, full_url: str, href: str, onclick: str | None) -> str | None:
        parsed = urlparse(full_url)
        qs = parse_qs(parsed.query)
        if qs.get("articleNo"):
            return "articleNo"
        for key in DETAIL_QUERY_KEYS:
            if qs.get(key):
                return f"query_{key}"
        if re.search(r"/(?:view|detail|article|post)/\w+", parsed.path, flags=re.IGNORECASE):
            return "path_detail_id"
        if onclick and re.search(r"(?:view|detail|goView|fnView)\s*\(", onclick, flags=re.IGNORECASE):
            return "onclick_parser"
        if re.search(r"\d", href or full_url):
            return "regex_fallback"
        return None


class DeuBoardAdapter(GenericBoardAdapter):
    name = "deu"

    def _url_from_onclick(self, base_url: str, onclick: str) -> str:
        # DEU 계열 게시판은 view/detail 계열 함수의 숫자 인자를 articleNo로 쓰는 경우가 흔하다.
        match = re.search(
            r"(?:view|detail|goView|fnView|jf_view)\s*\(([^)]*)\)",
            onclick,
            flags=re.IGNORECASE,
        )
        if not match:
            return super()._url_from_onclick(base_url, onclick)

        args = [part.strip().strip("'\"") for part in match.group(1).split(",")]
        article_arg = next((arg for arg in args if re.fullmatch(r"\d+", arg)), None)
        if not article_arg:
            return super()._url_from_onclick(base_url, onclick)

        parsed = urlparse(base_url)
        query = parse_qs(parsed.query)
        query["mode"] = ["view"]
        query["articleNo"] = [article_arg]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def adapter_for_url(url: str) -> GenericBoardAdapter:
    host = urlparse(url).netloc.lower()
    if host.endswith("deu.ac.kr"):
        return DeuBoardAdapter()
    return GenericBoardAdapter()
