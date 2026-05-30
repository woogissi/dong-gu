from __future__ import annotations

import ssl

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_RETRY_STATUS_CODES = (403, 408, 429, 500, 502, 503, 504)

# lib.deu.ac.kr 등 구형 DEU 호스트는 기본 OpenSSL security level에서 handshake 실패.
# SECLEVEL=1로 낮춰야 연결 가능.
INSECURE_SSL_HOSTS = frozenset({"lib.deu.ac.kr", "has.deu.ac.kr"})


class LegacyTLSAdapter(HTTPAdapter):
    """SECLEVEL=1 + 인증서 검증 비활성화 어댑터. 구형 DEU 서버 전용."""

    def init_poolmanager(self, *args, **kwargs):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
        kwargs["ssl_context"] = context
        return super().init_poolmanager(*args, **kwargs)


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
        other=total_retries,
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
