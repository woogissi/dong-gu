# crawler/extractors/base.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    version = "1"
