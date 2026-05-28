# crawler/discovery/tabbed_page_detector.py

import re
from bs4 import BeautifulSoup


TAB_SOURCE_TYPE_MAP = {
    "학사공지": "arc",
    "취업공지": "emp",
    "장학공지": "scsh",
}


def detect_tabbed_board(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    tabs = []

    for li in soup.select("ul.nav.nav-tabs li[onclick*='tabChange']"):
        onclick = li.get("onclick", "")
        m = re.search(r"tabChange\(['\"]([^'\"]+)['\"]\)", onclick)

        if not m:
            continue

        tab_value = m.group(1)
        tab_title = li.get_text(" ", strip=True)
        source_type = TAB_SOURCE_TYPE_MAP.get(tab_title)

        if not source_type:
            continue

        tabs.append({
            "tab_title": tab_title,
            "tab_value": tab_value,
            "source_type": source_type,
            "tab_method": "hidden_input_submit",
            "hidden_selector": "#CP1_hdnNoticeCd",
            "submit_selector": "#CP1_BtnOk",
            "search_input_selector": "#CP1_txtSearchValue",
        })

    return tabs