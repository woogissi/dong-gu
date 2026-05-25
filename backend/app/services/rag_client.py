import json
import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ChatQuery:
    text: str


class RagApiClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or os.getenv("RAG_API_URL", "http://rag:8001")).rstrip("/")
        self.timeout = timeout or float(os.getenv("RAG_API_TIMEOUT_SECONDS", "120"))

    def initialize(self) -> None:
        """Keep the backend startup contract without importing the RAG package."""
        return None

    def run(self, query: ChatQuery | str) -> dict[str, Any]:
        text = query.text if hasattr(query, "text") else str(query)
        payload = json.dumps({"text": text}).encode("utf-8")
        request = Request(
            f"{self.base_url}/api/rag/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                print(
                    "[backend timing] "
                    f"rag_api_call_ms={int(round((time.perf_counter() - started) * 1000))} "
                    f"payload_bytes={len(payload)} response_bytes={len(body)} "
                    f"query={text!r}",
                    flush=True,
                )
                return json.loads(body)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"RAG API request failed with {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"RAG API is unavailable: {exc.reason}") from exc
