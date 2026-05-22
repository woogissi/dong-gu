# crawler/auth/dap_auth_session.py

import os
import requests
from playwright.sync_api import sync_playwright
from contextlib import contextmanager

LOGIN_URL = "https://dap.deu.ac.kr/sso/login.aspx"


@contextmanager
def login_dap_with_playwright(headless: bool = True):
    user_id = os.getenv("DAP_USER_ID")
    user_pw = os.getenv("DAP_USER_PW")

    if not user_id or not user_pw:
        raise ValueError("DAP_USER_ID 또는 DAP_USER_PW 환경변수가 없습니다.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()

        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

        page.locator("input#id").fill(user_id)
        page.locator("input#pw").fill(user_pw)
        page.locator("input#btn-login").click(no_wait_after=True)

        page.wait_for_timeout(5000)

        yield page

        browser.close()


def build_dap_authenticated_session() -> requests.Session:
    user_id = os.getenv("DAP_USER_ID")
    user_pw = os.getenv("DAP_USER_PW")

    if not user_id or not user_pw:
        raise ValueError("DAP_USER_ID 또는 DAP_USER_PW 환경변수가 없습니다.")

    session = requests.Session()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto(LOGIN_URL, wait_until="networkidle")

        # selector 페이지 구조에 따라 수정해야하는 부분
        page.locator("input#id").fill(user_id)
        page.locator("input#pw").fill(user_pw)
        page.locator("input#btn-login").click()
        page.wait_for_load_state("networkidle")

        cookies = context.cookies()
        browser.close()

    for cookie in cookies:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )

    return session