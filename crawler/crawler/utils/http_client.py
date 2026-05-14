from __future__ import annotations

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_RETRY_STATUS_CODES = (429, 500, 502, 503, 504)


def build_retry_session(
    headers: dict[str, str] | None = None,
    total_retries: int = 2,
    backoff_factor: float = 0.5,
) -> Session:
    session = Session()
    if headers:
        session.headers.update(headers)

    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=DEFAULT_RETRY_STATUS_CODES,
        allowed_methods=frozenset({"GET", "HEAD"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
