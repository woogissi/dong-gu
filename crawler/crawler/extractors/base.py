# crawler/extractors/base.py

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from crawler.utils.http_client import build_retry_session


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    raw_html: str


class BaseExtractor:
    name = "base"
    version = "1"

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        timeout: tuple[float, float] = (5, 30),
    ):
        self.session = build_retry_session(headers)
        self.timeout = timeout

    def fetch_result(self, url: str) -> FetchResult:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return FetchResult(
            url=url,
            final_url=response.url,
            status_code=response.status_code,
            headers=dict(response.headers),
            raw_html=response.text,
        )

    def fetch(self, url: str) -> str:
        return self.fetch_result(url).raw_html

    def fetch_metadata(self, result: FetchResult) -> dict[str, Any]:
        return {
            "url": result.url,
            "final_url": result.final_url,
            "status_code": result.status_code,
            "headers": result.headers,
            "extractor_name": self.name,
            "extractor_version": self.version,
        }

    def extract_content(self, *_args, **_kwargs) -> dict:
        raise NotImplementedError

    def extract_attachments(self, *_args, **_kwargs) -> list[dict]:
        return []


class GenericExtractor(BaseExtractor):
    name = "generic"
    version = "2"

    def _json_text_candidates(self, soup: BeautifulSoup) -> list[str]:
        candidates: list[str] = []
        for node in soup.select('script[type="application/ld+json"]'):
            text = node.string or node.get_text(" ", strip=True)
            if text:
                candidates.append(text)

        html = str(soup)
        next_match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if next_match:
            candidates.append(next_match.group(1))

        for pattern in (
            r"window\.__INITIAL_STATE__\s*=\s*({.*?})\s*</script>",
            r"window\.__NUXT__\s*=\s*({.*?})\s*</script>",
        ):
            for match in re.finditer(pattern, html, flags=re.IGNORECASE | re.DOTALL):
                candidates.append(match.group(1))
        return candidates

    def _flatten_json_text(self, value: Any, depth: int = 0) -> list[str]:
        if depth > 6:
            return []
        if isinstance(value, str):
            text = re.sub(r"\s+", " ", value).strip()
            if 2 <= len(text) <= 1000 and not re.match(r"^https?://", text):
                return [text]
            return []
        if isinstance(value, dict):
            parts: list[str] = []
            for item in value.values():
                parts.extend(self._flatten_json_text(item, depth + 1))
            return parts
        if isinstance(value, list):
            parts = []
            for item in value[:200]:
                parts.extend(self._flatten_json_text(item, depth + 1))
            return parts
        return []

    def _extract_json_text(self, soup: BeautifulSoup) -> str:
        texts: list[str] = []
        for candidate in self._json_text_candidates(soup):
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            texts.extend(self._flatten_json_text(parsed))

        seen = set()
        deduped = []
        for text in texts:
            if text in seen:
                continue
            seen.add(text)
            deduped.append(text)
        return "\n".join(deduped[:200])

    def extract_content(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        json_text = self._extract_json_text(soup)
        for node in soup.select("script, style, nav, header, footer, aside, noscript"):
            node.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        content_nodes = soup.select("main, article")
        if content_nodes:
            text = "\n".join(node.get_text("\n", strip=True) for node in content_nodes)
        else:
            body = soup.body or soup
            headings = [node.get_text(" ", strip=True) for node in body.select("h1, h2, h3")]
            body_text = body.get_text("\n", strip=True)
            text = "\n".join([*headings, body_text])
        if json_text:
            text = "\n\n".join([text, "[JSON]\n" + json_text]).strip()
        return {
            "title": title,
            "raw_text": text,
            "extraction_strategy": "generic_fallback_json" if json_text else "generic_fallback",
        }
