"""헤드리스 브라우저(Playwright) 기반 JS 렌더링 HTML 페치.

동의대 일부 페이지(`*.do`, `*.aspx`, SPA 형태)는 본문을 JavaScript로 렌더링하기
때문에 정적 HTTP 페치로는 빈 HTML만 받는다. 이 모듈은 그런 페이지에 한해
Chromium으로 실제 렌더링한 HTML을 반환한다.

설계 원칙
- **env 게이트**: ``CRAWLER_ENABLE_JS_RENDER=1`` 일 때만 동작. 기본값은 비활성이라
  기존 정적 크롤 동작/이미지 의존성에 영향이 없다.
- **지연 import + graceful degrade**: Playwright 미설치/브라우저 미설치 시 예외를
  내지 않고 ``None`` 을 반환한다. 호출부는 정적 결과를 그대로 유지하면 된다.
- **stateless**: 호출마다 브라우저를 띄우고 닫는다. 재크롤 배치에서 단발성으로
  쓰기에 충분하며, 누수 위험이 없다.
"""

from __future__ import annotations

import os

# 본문이 이 길이(문자) 미만이면 "빈 페이지"로 보고 렌더링 폴백을 시도한다.
DEFAULT_RENDER_MIN_CHARS = 150

# 렌더링 대기/타임아웃 (밀리초)
_NAV_TIMEOUT_MS = int(os.getenv("CRAWLER_JS_RENDER_TIMEOUT_MS", "20000"))
_SETTLE_MS = int(os.getenv("CRAWLER_JS_RENDER_SETTLE_MS", "1200"))

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)


def js_render_enabled() -> bool:
    """JS 렌더링 폴백이 켜져 있는지 여부."""
    return os.getenv("CRAWLER_ENABLE_JS_RENDER") == "1"


def render_min_chars() -> int:
    """렌더링 폴백 트리거 임계값(문자 수)."""
    try:
        return int(os.getenv("CRAWLER_JS_RENDER_MIN_CHARS", str(DEFAULT_RENDER_MIN_CHARS)))
    except (TypeError, ValueError):
        return DEFAULT_RENDER_MIN_CHARS


def render_html(url: str, *, ignore_https_errors: bool = False) -> str | None:
    """``url`` 을 Chromium으로 렌더링한 최종 HTML을 반환한다.

    Playwright 가 없거나 렌더링에 실패하면 ``None`` 을 반환한다(예외를 던지지 않음).
    """
    if not js_render_enabled():
        return None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                context = browser.new_context(
                    user_agent=_USER_AGENT,
                    ignore_https_errors=ignore_https_errors,
                )
                page = context.new_page()
                page.set_default_navigation_timeout(_NAV_TIMEOUT_MS)
                page.goto(url, wait_until="networkidle")
                # 일부 페이지는 networkidle 이후에도 지연 렌더링하므로 약간 더 대기
                page.wait_for_timeout(_SETTLE_MS)
                return page.content()
            finally:
                browser.close()
    except Exception:
        # 타임아웃/네비게이션 실패/브라우저 미설치 등은 정적 결과 유지로 폴백
        return None
