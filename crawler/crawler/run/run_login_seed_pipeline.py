# crawler/run/run_login_seed_pipeline.py

import hashlib
import os
import re
import time
from datetime import datetime, timezone, timedelta
from itertools import product
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

from crawler.auth.dap_auth_session import (
    build_dap_authenticated_session,
    login_dap_with_playwright,
)
from crawler.config.domains import ALLOWED_HOSTS
from crawler.config.login_seeds import LOGIN_SEEDS
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.image_text_extractor import ImageTextExtractor
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.parsers.file_text_router import FileTextRouter
from crawler.run.run_full_pipeline import (
    allow_needs_review_attachment_chunks,
    attachment_parse_note,
    classify_attachment_parse_result,
    save_document_bundle,
)
from crawler.utils.content_hash import build_content_hash
from crawler.utils.text_quality import attachment_text_quality_report


TAB_SOURCE_TYPE_MAP = {
    "학사공지": "arc",
    "취업공지": "emp",
    "장학공지": "scsh",
    "교육/모집": "edu",
    "기숙사공지": "home",
    "비교과프로그램공지": "other",
    "개인정보활용공지": "person",
}

DEFAULT_EXCLUDE_SELECTORS = [
    "#CP1_commandbar",
    "select",
    "option",
    "input",
    "button",
    "script",
    "style",
]

KST = timezone(timedelta(hours=9))

pgv_loader = None

try:
    pgv_loader = PGVectorLoader()
except Exception as e:
    print(f"[DB DISABLED] crawl log DB connection failed: {e}")


# ---------------------------------------------------------------------
# Common utilities
# ---------------------------------------------------------------------

def goto_with_retry(
    page,
    url: str,
    wait_until: str = "domcontentloaded",
    timeout: int = 60000,
    retries: int = 3,
):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return
        except Exception as e:
            last_error = e
            print(f"[PAGE GOTO RETRY] attempt={attempt}/{retries} url={url} error={e}")
            time.sleep(2)

    raise last_error


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_multiline_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clean_option_text(text: str) -> str:
    return re.sub(r"^\d+\s*", "", text or "").strip()


def safe_filename(text: str, max_len: int = 120) -> str:
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text or "")
    text = re.sub(r"\s+", "_", text).strip("_")

    if not text:
        return ""

    if len(text.encode("utf-8")) <= max_len:
        return text

    result = ""
    size = 0

    for ch in text:
        ch_size = len(ch.encode("utf-8"))
        if size + ch_size > max_len:
            break
        result += ch
        size += ch_size

    return result.strip("_")


def remove_nodes(soup: BeautifulSoup, selectors: list[str] | None) -> None:
    for selector in selectors or []:
        for node in soup.select(selector):
            node.decompose()


def log_crawl_error(
    stage: str,
    error: Exception,
    source_type: str | None = None,
    doc_id: str | None = None,
    url: str | None = None,
    context: dict | None = None,
) -> None:
    print(f"[LOGIN PIPELINE ERROR] stage={stage} url={url} error={error}")

    if not pgv_loader:
        return

    try:
        pgv_loader.insert_crawl_job_error(
            run_type="login_seed_pipeline",
            stage=stage,
            error=error,
            source_type=source_type,
            doc_id=doc_id,
            url=url,
            context=context or {},
        )
    except Exception as db_error:
        print(f"[DB LOG SKIP] {db_error}")


def build_login_session(login_seed: dict):
    login_type = login_seed.get("login_type")

    if login_type == "dap":
        return build_dap_authenticated_session()

    raise ValueError(f"Unsupported login_type: {login_type}")


def is_login_image_ocr_enabled(seed: dict) -> bool:
    return (
        bool(seed.get("enable_image_ocr"))
        or os.getenv("CRAWLER_ENABLE_LOGIN_IMAGE_OCR", "").strip().lower()
        in {"1", "true", "yes"}
    )


# ---------------------------------------------------------------------
# Image extraction for login-current DOM pages
# ---------------------------------------------------------------------

def extract_current_image_urls(soup: BeautifulSoup, page_url: str) -> list[str]:
    urls = []

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-path") or img.get("data-url")
        if not src:
            continue
        urls.append(urljoin(page_url, src))

    return sorted(set(urls))


def build_image_texts(image_urls: list[str], seed: dict) -> list[dict]:
    if not image_urls:
        return []

    if is_login_image_ocr_enabled(seed):
        return ImageTextExtractor().extract_many(image_urls)

    return [
        {
            "image_index": idx,
            "image_url": image_url,
            "image_text": "",
        }
        for idx, image_url in enumerate(image_urls, start=1)
    ]


def merged_image_text(image_texts: list[dict]) -> str | None:
    texts = [
        f"[IMAGE: {item.get('image_url')}]\n{item.get('image_text')}"
        for item in image_texts or []
        if item.get("image_text")
    ]
    merged = "\n\n".join(texts).strip()
    return merged if merged else None


# ---------------------------------------------------------------------
# Table/content extraction
# ---------------------------------------------------------------------

def extract_current_table_text(soup: BeautifulSoup) -> str:
    lines = []

    for idx, table in enumerate(soup.find_all("table"), start=1):
        lines.append(f"[TABLE {idx}]")

        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            cell_texts = [
                normalize_text(cell.get_text(" ", strip=True))
                for cell in cells
            ]
            cell_texts = [c for c in cell_texts if c]

            if cell_texts:
                lines.append(" | ".join(cell_texts))

    return "\n".join(lines).strip()


def extract_content_soup(page, seed: dict) -> tuple[str, BeautifulSoup]:
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    result_config = seed.get("result") or {}
    selector = result_config.get("selector") or "#content .pagecont"

    content_node = (
        soup.select_one(selector)
        or soup.select_one("#content .pagecont")
        or soup.select_one("#content")
        or soup.select_one(".pagecont")
        or soup.body
    )

    if content_node:
        content_soup = BeautifulSoup(str(content_node), "html.parser")
    else:
        content_soup = BeautifulSoup("", "html.parser")

    remove_nodes(
        content_soup,
        result_config.get("exclude_selectors", DEFAULT_EXCLUDE_SELECTORS),
    )

    return html, content_soup


def infer_title_from_soup(content_soup: BeautifulSoup, seed: dict) -> str:
    for selector in [
        "#divTitle h3",
        "#CP1_divContents .panel-heading .panel-title",
        "#CP1_divContents h2.panel-title",
        ".panel-heading .panel-title",
        ".panel-title",
        "h1",
        "h2",
        "h3",
        "title",
    ]:
        node = content_soup.select_one(selector)
        if node:
            title = normalize_text(node.get_text(" ", strip=True))
            if title and title != "동의대학교 DAP시스템":
                return title

    return seed.get("title") or seed.get("name") or seed.get("url") or "dap_page"


# ---------------------------------------------------------------------
# Seed-driven controls
# ---------------------------------------------------------------------

def normalize_control_spec(spec, default: dict | None = None) -> dict:
    if isinstance(spec, str):
        merged = dict(default or {})
        merged["selector"] = spec
        return merged

    merged = dict(default or {})
    merged.update(spec or {})
    return merged


def get_seed_controls(seed: dict) -> dict:
    controls = seed.get("controls") or {}

    selects = {}
    for logical_name, spec in (controls.get("selects") or {}).items():
        normalized = normalize_control_spec(
            spec,
            {
                "select_by": "value",
                "required": True,
                "skip_values": ["", "선택안함", "선택", "학기선택", "건물선택"],
            },
        )
        if not normalized.get("selector"):
            raise ValueError(f"select selector is required: {seed.get('name')} {logical_name}")
        selects[logical_name] = normalized

    inputs = {}
    for logical_name, spec in (controls.get("inputs") or {}).items():
        normalized = normalize_control_spec(
            spec,
            {
                "required": True,
                "skip_if_disabled": True,
            },
        )
        if not normalized.get("selector"):
            raise ValueError(f"input selector is required: {seed.get('name')} {logical_name}")
        inputs[logical_name] = normalized

    radios = {}
    for logical_name, spec in (controls.get("radios") or {}).items():
        normalized = normalize_control_spec(
            spec,
            {
                "required": True,
                "click": True,
            },
        )
        if not normalized.get("selector"):
            raise ValueError(f"radio selector is required: {seed.get('name')} {logical_name}")
        radios[logical_name] = normalized

    return {
        "selects": selects,
        "inputs": inputs,
        "radios": radios,
        "submit": controls.get("submit") or {"click": False},
        "iframe": controls.get("iframe"),
        "pdf_button": controls.get("pdf_button") or {},
        "lookup": controls.get("lookup") or {},
        "target_input": controls.get("target_input") or {},
    }


def option_allowed(option: dict, spec: dict) -> bool:
    value = str(option.get("value") or "").strip()
    text = str(option.get("text") or "").strip()

    skip_values = set(map(str, spec.get("skip_values") or []))
    if value in skip_values or text in skip_values:
        return False

    include_values = spec.get("include_values")
    if include_values is not None and value not in set(map(str, include_values)):
        return False

    exclude_values = spec.get("exclude_values")
    if exclude_values is not None and value in set(map(str, exclude_values)):
        return False

    include_texts = spec.get("include_texts")
    if include_texts is not None and not any(t in text for t in include_texts):
        return False

    exclude_texts = spec.get("exclude_texts")
    if exclude_texts is not None and any(t in text for t in exclude_texts):
        return False

    return True


def collect_seed_select_options(page, logical_name: str, spec: dict) -> list[dict]:
    selector = spec["selector"]
    locator = page.locator(selector)

    if locator.count() == 0:
        if spec.get("required", True):
            raise ValueError(f"required select not found: {logical_name} selector={selector}")
        return []

    first = locator.first
    tag_name = first.evaluate("el => el.tagName.toLowerCase()")

    if tag_name != "select":
        if spec.get("required", True):
            raise ValueError(f"control is not select: {logical_name} selector={selector}")
        return []

    is_disabled = first.evaluate("el => el.disabled || el.hasAttribute('disabled')")
    if is_disabled:
        print(f"[SEED SELECT SKIP] disabled logical_name={logical_name} selector={selector}")
        return []

    options = first.locator("option").evaluate_all(
        """els => els.map(e => ({
            value: e.value,
            text: e.textContent.trim()
        }))"""
    )

    options = [
        {
            "selector": selector,
            "value": opt["value"],
            "text": opt["text"],
            "select_by": spec.get("select_by", "value"),
            "fixed": False,
        }
        for opt in options
        if option_allowed(opt, spec)
    ]

    max_options = spec.get("max_options")
    if max_options:
        options = options[: int(max_options)]

    return options


def fill_seed_inputs(page, seed: dict) -> None:
    controls = get_seed_controls(seed)

    for logical_name, spec in controls["inputs"].items():
        selector = spec["selector"]
        value = spec.get("value")

        if value is None and spec.get("default_current_year"):
            value = str(datetime.now().year)

        if value is None:
            if spec.get("required", True):
                raise ValueError(f"input value is required: {logical_name} selector={selector}")
            continue

        locator = page.locator(selector).first

        if locator.count() == 0:
            if spec.get("required", True):
                raise ValueError(f"input not found: {logical_name} selector={selector}")
            continue

        is_disabled = locator.evaluate("el => el.disabled || el.hasAttribute('disabled')")
        if is_disabled and spec.get("skip_if_disabled", True):
            print(f"[SEED INPUT SKIP] disabled {logical_name} selector={selector}")
            continue

        locator.fill(str(value))
        print(f"[SEED INPUT] {logical_name} selector={selector} value={value}")
        page.wait_for_timeout(seed.get("post_input_wait_ms", 300))


def click_seed_radios(page, seed: dict) -> None:
    controls = get_seed_controls(seed)

    for logical_name, spec in controls["radios"].items():
        if not spec.get("click", True):
            continue

        selector = spec["selector"]
        locator = page.locator(selector).first

        if locator.count() == 0:
            if spec.get("required", True):
                raise ValueError(f"radio not found: {logical_name} selector={selector}")
            continue

        locator.click()
        print(f"[SEED RADIO] {logical_name} selector={selector}")
        page.wait_for_timeout(seed.get("post_radio_wait_ms", 300))


def apply_seed_select(page, logical_name: str, selected: dict, wait_ms: int = 1000) -> None:
    selector = selected["selector"]
    value = selected.get("value")
    text = selected.get("text")
    select_by = selected.get("select_by", "value")

    locator = page.locator(selector).first

    if locator.count() == 0:
        raise ValueError(f"select not found: {logical_name} selector={selector}")

    is_disabled = locator.evaluate("el => el.disabled || el.hasAttribute('disabled')")
    if is_disabled:
        raise ValueError(f"select disabled: {logical_name} selector={selector}")

    print(
        f"[SEED SELECT] "
        f"{logical_name} selector={selector} select_by={select_by} "
        f"value={value} text={text}"
    )

    if select_by == "label":
        locator.select_option(label=text)
    elif select_by == "index":
        locator.select_option(index=int(value))
    else:
        locator.select_option(value=value)

    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    page.wait_for_timeout(wait_ms)


def apply_seed_controls(page, seed: dict, combo: dict) -> None:
    fill_seed_inputs(page, seed)
    click_seed_radios(page, seed)

    for logical_name, selected in combo.items():
        apply_seed_select(
            page,
            logical_name,
            selected,
            wait_ms=seed.get("post_select_wait_ms", 1000),
        )


def click_seed_submit(page, seed: dict) -> None:
    controls = get_seed_controls(seed)
    submit = controls.get("submit") or {}

    if not submit or not submit.get("click", False):
        print(f"[SEED SUBMIT SKIP] name={seed.get('name')}")
        return

    selector = submit.get("selector")
    if not selector:
        raise ValueError(f"submit selector not configured: seed={seed.get('name')}")

    locator = page.locator(selector).first
    if locator.count() == 0:
        raise ValueError(f"submit not found: seed={seed.get('name')} selector={selector}")

    print(f"[SEED SUBMIT] name={seed.get('name')} selector={selector}")

    locator.click()

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    page.wait_for_timeout(seed.get("post_submit_wait_ms", 1500))


def build_independent_select_combinations(page, seed: dict, exclude_names: set[str] | None = None) -> list[dict]:
    controls = get_seed_controls(seed)
    exclude_names = exclude_names or set()
    option_groups = []

    for logical_name, spec in controls["selects"].items():
        if logical_name in exclude_names:
            continue

        options = collect_seed_select_options(page, logical_name, spec)

        if not options:
            if spec.get("required", True):
                raise ValueError(f"no options for required select: {logical_name}")
            continue

        option_groups.append({
            "logical_name": logical_name,
            "options": options,
        })

    if not option_groups:
        return [{}]

    combinations = []
    for combo in product(*[group["options"] for group in option_groups]):
        item = {}
        for group, selected in zip(option_groups, combo):
            item[group["logical_name"]] = selected
        combinations.append(item)

    return combinations


def build_dependent_select_combinations(page, seed: dict, chain: list[str]) -> list[dict]:
    controls = get_seed_controls(seed)
    combinations = []

    def walk(index: int, current: dict):
        if index >= len(chain):
            combinations.append(dict(current))
            return

        logical_name = chain[index]
        spec = controls["selects"].get(logical_name)

        if not spec:
            raise ValueError(f"dependent select is not configured: {logical_name}")

        options = collect_seed_select_options(page, logical_name, spec)

        if not options:
            print(
                f"[DEPENDENT SELECT EMPTY] "
                f"name={seed.get('name')} "
                f"logical_name={logical_name} "
                f"chain={chain} "
                f"current={current}"
            )
            return

        is_leaf = index == len(chain) - 1

        for selected in options:
            if not is_leaf:
                apply_seed_select(
                    page,
                    logical_name,
                    selected,
                    wait_ms=seed.get("post_select_wait_ms", 1000),
                )

            current[logical_name] = selected
            walk(index + 1, current)
            current.pop(logical_name, None)

            # Re-apply parent selections before trying the next sibling option.
            for parent_name in chain[:index]:
                if parent_name in current:
                    apply_seed_select(
                        page,
                        parent_name,
                        current[parent_name],
                        wait_ms=seed.get("post_select_wait_ms", 1000),
                    )

    walk(0, {})
    return combinations


def build_seed_select_combinations(page, seed: dict) -> list[dict]:
    dependent_selects = seed.get("dependent_selects") or []

    if not dependent_selects:
        return build_independent_select_combinations(page, seed)

    if len(dependent_selects) > 1:
        raise ValueError("Only one dependent_selects chain is supported in this pipeline version.")

    chain = list(dependent_selects[0])
    chain_names = set(chain)

    independent_combos = build_independent_select_combinations(page, seed, exclude_names=chain_names)
    dependent_combos = build_dependent_select_combinations(page, seed, chain)

    merged = []

    for independent in independent_combos:
        for dependent in dependent_combos:
            item = {}
            item.update(independent)
            item.update(dependent)
            merged.append(item)

    return merged or [{}]


def format_combo_label(combo: dict) -> str:
    parts = []

    for logical_name, selected in combo.items():
        text = clean_option_text(selected.get("text", ""))
        value = selected.get("value", "")

        if text:
            parts.append(f"{logical_name}={text}")
        elif value:
            parts.append(f"{logical_name}={value}")

    return ", ".join(parts) if parts else "default"


# ---------------------------------------------------------------------
# Static current DOM documents
# ---------------------------------------------------------------------

def build_current_static_raw_doc(page, seed: dict) -> dict:
    page_url = seed["url"]
    source_type = seed["source_type"]

    original_html, content_soup = extract_content_soup(page, seed)
    title = infer_title_from_soup(content_soup, seed)

    raw_text = normalize_multiline_text(content_soup.get_text("\n", strip=True))
    table_text = extract_current_table_text(content_soup)
    image_urls = extract_current_image_urls(content_soup, page_url)
    image_texts = build_image_texts(image_urls, seed)
    image_text = merged_image_text(image_texts)

    doc_key = (
        f"{page_url}_"
        f"{source_type}_"
        f"{seed.get('name')}_"
        f"{seed.get('tab_info', {}).get('tab_value', '')}_"
        f"current_static_dom"
    )
    doc_hash = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]
    doc_id = f"{source_type}_static_{doc_hash}"

    return {
        "doc_id": doc_id,
        "source_type": source_type,
        "page_kind": "login_static_dom",
        "department": None,
        "title": title,
        "source_url": page_url,
        "published_at": None,
        "updated_at": None,
        "raw_text": raw_text,
        "normalize": None,
        "table_text": table_text,
        "attachment_text": None,
        "version": 1,
        "change_type": None,
        "collected_at": now_kst_iso(),
        "content_hash": build_content_hash(
            raw_text=raw_text,
            table_text=table_text,
            attachment_text=None,
            image_text=image_text,
        ),
        "html": str(content_soup) if content_soup else original_html,
        "metadata": {
            "seed_name": seed.get("name"),
            "tab_info": seed.get("tab_info"),
            "collection_mode": "current_static_dom",
            "result_selector": (seed.get("result") or {}).get("selector"),
        },
        "views": None,
        "image_urls": image_urls,
        "image_texts": image_texts,
        "attachments": [],
        "downloaded_attachments": [],
        "outgoing_links": [],
    }


def save_current_static_page_from_page(page, seed: dict) -> None:
    raw_doc = build_current_static_raw_doc(page, seed)
    save_document_bundle(raw_doc, download_attachments=False)
    print(f"[CURRENT STATIC DOM OK] name={seed.get('name')} doc_id={raw_doc['doc_id']}")


def collect_login_page_once(login_seed: dict, auth_session) -> None:
    if not login_seed.get("collect_login_page", False):
        return

    extractor = StaticPageExtractor(
        allowed_hosts=ALLOWED_HOSTS,
        session=auth_session,
        enable_image_ocr=is_login_image_ocr_enabled(login_seed),
    )

    raw_doc = extractor.extract_static_page(
        source_type=login_seed["source_type"],
        page_url=login_seed["url"],
    )

    raw_doc["page_kind"] = "login_page"

    save_document_bundle(raw_doc, download_attachments=True)

    print(f"[LOGIN PAGE SAVE OK] doc_id={raw_doc['doc_id']}")


# ---------------------------------------------------------------------
# Postback DOM result documents
# ---------------------------------------------------------------------

def collect_seed_result(page, seed: dict, combo: dict) -> dict | None:
    result_config = seed.get("result") or {}
    selector = result_config.get("selector")

    if not selector:
        raise ValueError(f"result.selector not configured: seed={seed.get('name')}")

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    result_node = soup.select_one(selector)
    if not result_node:
        print(
            f"[SEED RESULT NOT FOUND] "
            f"name={seed.get('name')} selector={selector}"
        )
        return None

    result_soup = BeautifulSoup(str(result_node), "html.parser")

    remove_nodes(
        result_soup,
        result_config.get("exclude_selectors", DEFAULT_EXCLUDE_SELECTORS),
    )

    raw_text = normalize_multiline_text(result_soup.get_text("\n", strip=True))
    table_text = extract_current_table_text(result_soup)

    for no_data_text in result_config.get("no_data_texts", []):
        if no_data_text in raw_text or no_data_text in table_text:
            print(
                f"[SEED RESULT NO DATA] "
                f"name={seed.get('name')} "
                f"combo={format_combo_label(combo)} "
                f"text={no_data_text}"
            )
            return None

    if not raw_text.strip() and not table_text.strip():
        print(
            f"[SEED RESULT EMPTY] "
            f"name={seed.get('name')} combo={format_combo_label(combo)}"
        )
        return None

    combo_label = format_combo_label(combo)

    return {
        "combo_label": combo_label,
        "combo": combo,
        "raw_text": f"[{combo_label}]\n{raw_text}".strip(),
        "table_text": f"[{combo_label}]\n{table_text}".strip() if table_text else "",
        "html": str(result_soup),
        "has_result_table": bool(table_text),
        "source_url": page.url,
        "title": seed.get("title") or seed.get("name"),
    }


def create_merged_postback_raw_doc(
    seed: dict,
    page_url: str,
    source_type: str,
    merged_items: list[dict],
) -> dict:
    title = seed.get("title") or seed.get("name") or page_url

    raw_text = "\n\n".join(
        item.get("raw_text", "")
        for item in merged_items
        if item.get("raw_text")
    ).strip()

    table_text = "\n\n".join(
        item.get("table_text", "")
        for item in merged_items
        if item.get("table_text")
    ).strip()

    html = "\n\n".join(
        f"<h2>{item.get('combo_label')}</h2>\n{item.get('html', '')}"
        for item in merged_items
    )

    structured_sections = []

    for idx, item in enumerate(merged_items, start=1):
        section_text = "\n\n".join(
            part
            for part in (item.get("raw_text"), item.get("table_text"))
            if part
        ).strip()

        if not section_text:
            continue

        structured_sections.append(
            {
                "section_type": "body",
                "section_title": item.get("combo_label") or f"select_result_{idx}",
                "text": section_text,
                "metadata": {
                    "structure_type": "login_seed_select_result",
                    "combo_index": idx,
                    "combo": item.get("combo"),
                    "has_result_table": item.get("has_result_table"),
                },
            }
        )

    doc_key = (
        f"{page_url}_"
        f"{source_type}_"
        f"{seed.get('name')}_"
        f"merged_postback_result"
    )
    doc_hash = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]
    doc_id = f"{source_type}_merged_postback_{doc_hash}"

    return {
        "doc_id": doc_id,
        "source_type": source_type,
        "page_kind": "dynamic_postback_merged_page",
        "department": None,
        "title": title,
        "source_url": page_url,
        "published_at": None,
        "updated_at": None,
        "structured_sections": structured_sections,
        "raw_text": raw_text,
        "normalize": None,
        "table_text": table_text,
        "attachment_text": None,
        "version": 1,
        "change_type": None,
        "collected_at": now_kst_iso(),
        "content_hash": build_content_hash(
            raw_text=raw_text,
            table_text=table_text,
            attachment_text=None,
            image_text=None,
        ),
        "html": html,
        "metadata": {
            "seed_name": seed.get("name"),
            "report_type": seed.get("report_type"),
            "merged": True,
            "combo_count": len(merged_items),
            "combos": [
                {
                    "combo_label": item["combo_label"],
                    "combo": item["combo"],
                }
                for item in merged_items
            ],
        },
        "views": None,
        "image_urls": [],
        "image_texts": [],
        "attachments": [],
        "downloaded_attachments": [],
        "outgoing_links": [],
    }


def run_select_postback_result_from_current_page(page, seed: dict) -> None:
    page_url = seed["url"]

    combinations = build_seed_select_combinations(page, seed)

    max_combinations = seed.get("max_combinations")
    if max_combinations:
        combinations = combinations[: int(max_combinations)]

    print(f"[POSTBACK RESULT] select combination count={len(combinations)}")

    merged_items = []

    for idx, combo in enumerate(combinations, start=1):
        goto_with_retry(page, page_url)
        page.wait_for_timeout(seed.get("initial_wait_ms", 1000))

        if seed.get("tab_info"):
            switch_tab(page, seed["tab_info"])

        print(f"[POSTBACK RESULT COMBO] {combo}")

        apply_seed_controls(page, seed, combo)
        click_seed_submit(page, seed)

        item = collect_seed_result(page, seed, combo)
        if not item:
            continue

        merged_items.append(item)

        print(
            f"[POSTBACK RESULT COLLECT OK] "
            f"name={seed.get('name')} "
            f"index={idx} "
            f"combo={item.get('combo_label')} "
            f"raw_len={len(item.get('raw_text') or '')} "
            f"table_len={len(item.get('table_text') or '')}"
        )

    if not merged_items:
        print(f"[POSTBACK RESULT EMPTY ALL] name={seed.get('name')}")
        return

    raw_doc = create_merged_postback_raw_doc(
        seed=seed,
        page_url=page_url,
        source_type=seed["source_type"],
        merged_items=merged_items,
    )

    save_document_bundle(raw_doc, download_attachments=False)

    print(
        f"[POSTBACK RESULT MERGED FILE OK] "
        f"name={seed.get('name')} "
        f"combo_count={len(merged_items)} "
        f"doc_id={raw_doc.get('doc_id')}"
    )


# ---------------------------------------------------------------------
# File parsing / iframe report PDF documents
# ---------------------------------------------------------------------

def save_and_parse_existing_file(
    file_path: Path,
    source_type: str,
    doc_id: str,
    file_name: str,
    file_url: str,
) -> dict:
    raw_file_dir = Path("crawler/data/raw/files") / source_type / doc_id
    raw_file_dir.mkdir(parents=True, exist_ok=True)

    original_ext = file_path.suffix.lower()
    file_name = safe_filename(file_name) or f"{doc_id}{original_ext}"

    if original_ext and not file_name.lower().endswith(original_ext):
        file_name += original_ext

    target_path = raw_file_dir / file_name

    if file_path.resolve() != target_path.resolve():
        target_path.write_bytes(file_path.read_bytes())

    if target_path.suffix.lower() == ".pdf":
        pdf_bytes = target_path.read_bytes()
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError(
                f"file is not pdf: path={target_path.as_posix()} file_url={file_url}"
            )

    router = FileTextRouter()
    parse_result = router.extract_text(str(target_path))

    attachment_quality = attachment_text_quality_report(
        parse_result.get("attachment_text"),
        parser_name=parse_result.get("parser_type"),
        page_count=parse_result.get("page_count"),
        tables=parse_result.get("attachment_tables", []),
    )

    downloaded = {
        "attachment_index": 1,
        "file_name": file_name,
        "file_url": file_url,
        "file_ext": target_path.suffix.lower() or None,
        "saved_path": str(target_path.as_posix()),
        "file_size": target_path.stat().st_size,
        "content_type": None,
        "parser_type": parse_result.get("parser_type"),
        "parser_name": parse_result.get("parser_type"),
        "page_count": parse_result.get("page_count"),
        "pages": parse_result.get("pages", []),
        "attachment_tables": parse_result.get("attachment_tables", []),
        "raw_xml_files": parse_result.get("raw_xml_files", []),
        "extracted_files": parse_result.get("extracted_files", []),
        "file_count": parse_result.get("file_count"),
    }

    parse_status = classify_attachment_parse_result(
        downloaded,
        parse_result,
        attachment_quality,
    )

    quality_status = str(attachment_quality.get("quality_status") or "needs_review")
    quality_reason = str(attachment_quality.get("quality_reason") or parse_status)

    should_store_attachment_text = (
        parse_status == "parser_success"
        and (
            quality_status == "ok"
            or (
                quality_status == "needs_review"
                and allow_needs_review_attachment_chunks()
            )
        )
    )

    downloaded.update(
        {
            "parser_status": parse_status,
            "parse_status": parse_status,
            "attachment_text": (
                parse_result.get("attachment_text")
                if should_store_attachment_text
                else None
            ),
            "extracted_text_length": attachment_quality.get("extracted_text_length"),
            "text_per_page": attachment_quality.get("text_per_page"),
            "korean_ratio": attachment_quality.get("korean_ratio"),
            "digit_ratio": attachment_quality.get("digit_ratio"),
            "binary_marker_detected": attachment_quality.get("binary_marker_detected"),
            "table_detected": attachment_quality.get("table_detected"),
            "quality_status": quality_status,
            "quality_reason": quality_reason,
            "quality": attachment_quality,
            "note": attachment_parse_note(
                parse_status,
                parse_result,
            ),
        }
    )

    return downloaded


def save_and_parse_report_download(
    download,
    source_type: str,
    doc_id: str,
    file_name: str,
    source_url: str,
) -> dict:
    raw_file_dir = Path("crawler/data/raw/files") / source_type / doc_id
    raw_file_dir.mkdir(parents=True, exist_ok=True)

    suggested_name = download.suggested_filename or ""
    suggested_ext = Path(suggested_name).suffix.lower()
    base_name = safe_filename(file_name) or safe_filename(suggested_name) or doc_id

    if suggested_ext and not base_name.lower().endswith(suggested_ext):
        base_name += suggested_ext

    file_path = raw_file_dir / base_name
    download.save_as(str(file_path))

    return save_and_parse_existing_file(
        file_path=file_path,
        source_type=source_type,
        doc_id=doc_id,
        file_name=base_name,
        file_url=f"{source_url}#download={suggested_name or base_name}",
    )


def get_report_frame(page, seed: dict):
    controls = get_seed_controls(seed)
    iframe_spec = controls.get("iframe")

    if iframe_spec:
        selector = iframe_spec.get("selector") if isinstance(iframe_spec, dict) else iframe_spec
        locator = page.locator(selector).first

        if locator.count() > 0:
            frame = locator.content_frame()
            if frame:
                return frame

    report_frame = next(
        (
            frame
            for frame in page.frames
            if "CLIPreport4" in (frame.url or "")
            or "report.deu.ac.kr" in (frame.url or "")
        ),
        None,
    )

    return report_frame


def build_dynamic_report_html(title: str, source_url: str, report_url: str, combo: dict) -> str:
    select_rows = "\n".join(
        f"<li>{key}: {value.get('text')} ({value.get('value')})</li>"
        for key, value in combo.items()
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
</head>
<body>
  <h1>{title}</h1>
  <p>source_url: {source_url}</p>
  <p>report_url: {report_url}</p>
  <h2>selected_options</h2>
  <ul>
    {select_rows}
  </ul>
</body>
</html>
"""


def create_dynamic_report_raw_doc(
    seed: dict,
    source_type: str,
    page_url: str,
    doc_id: str,
    title: str,
    combo: dict,
    downloaded: dict,
    report_url: str,
) -> dict:
    html = build_dynamic_report_html(
        title=title,
        source_url=page_url,
        report_url=report_url,
        combo=combo,
    )

    combo_lines = [
        f"{key}: {value.get('text')} ({value.get('value')})"
        for key, value in combo.items()
    ]

    raw_text = "\n".join(
        [
            title,
            f"source_url: {page_url}",
            f"report_url: {report_url}",
            "[SELECT VALUES]",
            *combo_lines,
        ]
    ).strip()

    attachment_text = downloaded.get("attachment_text")

    return {
        "doc_id": doc_id,
        "source_type": source_type,
        "page_kind": "dynamic_report_page",
        "department": clean_option_text(combo.get("department", {}).get("text", "")),
        "title": title,
        "source_url": page_url,
        "published_at": None,
        "updated_at": None,
        "raw_text": raw_text,
        "normalize": None,
        "table_text": "",
        "attachment_text": attachment_text,
        "version": 1,
        "change_type": None,
        "collected_at": now_kst_iso(),
        "content_hash": build_content_hash(
            raw_text=raw_text,
            table_text="",
            attachment_text=attachment_text,
            image_text=None,
        ),
        "html": html,
        "metadata": {
            "seed_name": seed.get("name"),
            "tab_info": seed.get("tab_info"),
            "select_values": {
                key: {
                    "value": value.get("value"),
                    "text": value.get("text"),
                }
                for key, value in combo.items()
            },
            "report_url": report_url,
            "browser_download": True,
        },
        "attachments": [
            {
                "attachment_index": 1,
                "file_name": downloaded["file_name"],
                "file_url": downloaded["file_url"],
            }
        ],
        "downloaded_attachments": [downloaded],
        "image_urls": [],
        "image_texts": [],
        "outgoing_links": [],
        "views": None,
    }


def save_iframe_report_pdf_for_current_page(page, seed: dict, combo: dict) -> None:
    source_type = seed["source_type"]
    page_url = seed["url"]

    combo_text = "_".join(
        clean_option_text(selected.get("text", "")).replace(" ", "")
        for selected in combo.values()
        if selected.get("text")
    )
    combo_value = "_".join(
        str(selected.get("value", ""))
        for selected in combo.values()
        if selected.get("value") is not None
    ) or "default"

    tab_value = seed.get("tab_info", {}).get("tab_value", "")
    doc_key = f"{page_url}_{tab_value}_{combo_value}"
    doc_hash = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]
    doc_id = f"{source_type}_dynamic_report_{doc_hash}"

    title_prefix = seed.get("title") or seed.get("name") or "dynamic_report"
    title = f"{combo_text} {title_prefix}".strip()
    file_name = title

    report_frame = get_report_frame(page, seed)

    if not report_frame:
        raise ValueError("report iframe not found. configure controls.iframe.selector or use current_static_dom/select_postback_result")

    print(f"[REPORT FRAME URL] {report_frame.url}")

    controls = get_seed_controls(seed)
    pdf_button_selector = controls.get("pdf_button", {}).get("selector", ".report_menu_pdf_button")
    pdf_button = report_frame.locator(pdf_button_selector)

    if pdf_button.count() == 0:
        raise ValueError(f"PDF button not found: selector={pdf_button_selector}")

    pdf_button.first.wait_for(timeout=30000)
    print(f"[DYNAMIC REPORT EXPORT BUTTON COUNT] {pdf_button.count()}")

    try:
        with page.expect_download(timeout=15000) as download_info:
            pdf_button.first.click()
        download = download_info.value
    except Exception as download_error:
        raise ValueError(f"PDF download was not captured: {download_error}")

    report_url = f"{page_url}#download={download.suggested_filename}"

    print(
        f"[DYNAMIC REPORT DOWNLOAD] "
        f"suggested_filename={download.suggested_filename}"
    )

    downloaded = save_and_parse_report_download(
        download=download,
        source_type=source_type,
        doc_id=doc_id,
        file_name=file_name,
        source_url=page_url,
    )

    if not downloaded.get("attachment_text"):
        print(
            f"[DYNAMIC REPORT ATTACHMENT EMPTY] "
            f"doc_id={doc_id} "
            f"parse_status={downloaded.get('parse_status')} "
            f"quality_status={downloaded.get('quality_status')} "
            f"reason={downloaded.get('quality_reason')}"
        )

    raw_doc = create_dynamic_report_raw_doc(
        seed=seed,
        source_type=source_type,
        page_url=page_url,
        doc_id=doc_id,
        title=title,
        combo=combo,
        downloaded=downloaded,
        report_url=report_url,
    )

    save_document_bundle(raw_doc, download_attachments=False)

    print(f"[DYNAMIC REPORT FILE OK] doc_id={doc_id}")


def run_iframe_report_from_current_page(page, seed: dict) -> None:
    page_url = seed["url"]
    combinations = build_seed_select_combinations(page, seed)

    if not combinations:
        combinations = [{}]

    max_combinations = seed.get("max_combinations")
    if max_combinations:
        combinations = combinations[: int(max_combinations)]

    print(f"[IFRAME REPORT] select combination count={len(combinations)}")

    for idx, combo in enumerate(combinations, start=1):
        try:
            goto_with_retry(page, page_url)
            page.wait_for_timeout(seed.get("initial_wait_ms", 1000))

            if seed.get("tab_info"):
                switch_tab(page, seed["tab_info"])

            apply_seed_controls(page, seed, combo)
            click_seed_submit(page, seed)

            print(
                f"[IFRAME REPORT] {idx}/{len(combinations)} "
                f"combo={format_combo_label(combo)}"
            )

            save_iframe_report_pdf_for_current_page(page=page, seed=seed, combo=combo)

        except Exception as e:
            log_crawl_error(
                stage="iframe_report",
                error=e,
                source_type=seed.get("source_type"),
                url=page_url,
                context={
                    "seed_name": seed.get("name"),
                    "combo": combo,
                    "tab_info": seed.get("tab_info"),
                },
            )
            continue


# ---------------------------------------------------------------------
# Popup lookup -> parent input -> iframe PDF reports
# ---------------------------------------------------------------------

def open_lookup_popup(page, lookup: dict):
    open_button = lookup.get("open_button")
    if not open_button:
        raise ValueError("lookup.open_button is required")

    with page.expect_popup(timeout=15000) as popup_info:
        page.locator(open_button).click()

    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded")
    popup.wait_for_timeout(1000)

    expected_url = lookup.get("popup_url_contains")
    if expected_url and expected_url not in popup.url:
        print(f"[LOOKUP POPUP WARN] expected_url_contains={expected_url} actual={popup.url}")

    return popup


def extract_lookup_rows(popup, lookup: dict) -> list[dict]:
    table_selector = lookup["result_table"]
    value_idx = int(lookup.get("value_column_index", 0))
    text_idx = int(lookup.get("text_column_index", 1))

    rows = popup.locator(f"{table_selector} tbody tr")
    results = []

    for i in range(rows.count()):
        cells = rows.nth(i).locator("td").all_inner_texts()
        cells = [c.strip() for c in cells]

        if len(cells) <= value_idx:
            continue

        value = cells[value_idx]
        text = cells[text_idx] if len(cells) > text_idx else value

        if value:
            results.append({
                "value": value,
                "text": text,
                "row_index": i + 1,
            })

    return results


def goto_lookup_page(popup, lookup: dict, target_page_no: int) -> bool:
    pager = lookup.get("pager") or {}

    # First, try visible page text.
    page_link = popup.locator("ul.pagination a").filter(has_text=str(target_page_no)).first
    if page_link.count() > 0:
        page_link.click()
        try:
            popup.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        popup.wait_for_timeout(800)
        return True

    # Then, try direct ASP.NET id prefix.
    prefix = pager.get("page_link_prefix")
    if prefix:
        direct_selector = f"{prefix}{target_page_no}"
        if popup.locator(direct_selector).count() > 0:
            popup.locator(direct_selector).click()
            try:
                popup.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            popup.wait_for_timeout(800)
            return True

    # Finally, try next block.
    next_selector = pager.get("next_selector") or "#CP1_COM_Page_Controllor_lbtnNext10"
    if popup.locator(next_selector).count() > 0:
        popup.locator(next_selector).click()
        try:
            popup.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        popup.wait_for_timeout(800)
        return True

    return False


def collect_lookup_values_from_popup(popup, lookup: dict) -> list[dict]:
    values = []
    seen = set()

    search_button = lookup.get("search_button")
    if search_button:
        popup.locator(search_button).click()
        try:
            popup.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        popup.wait_for_timeout(1000)

    pager = lookup.get("pager") or {}
    page_count = 1

    if pager.get("page_count_selector") and popup.locator(pager["page_count_selector"]).count() > 0:
        raw_count = popup.locator(pager["page_count_selector"]).input_value()
        if raw_count.isdigit():
            page_count = int(raw_count)

    max_pages = lookup.get("max_pages")
    if max_pages:
        page_count = min(page_count, int(max_pages))

    for page_no in range(1, page_count + 1):
        page_rows = extract_lookup_rows(popup, lookup)
        print(f"[LOOKUP PAGE] page={page_no}/{page_count} rows={len(page_rows)}")

        for row in page_rows:
            if row["value"] in seen:
                continue
            seen.add(row["value"])
            values.append(row)

        if page_no >= page_count:
            break

        if not goto_lookup_page(popup, lookup, page_no + 1):
            print(f"[LOOKUP PAGE END] failed_to_move_next target_page={page_no + 1}")
            break

    print(f"[LOOKUP VALUES] count={len(values)}")
    return values


def run_popup_lookup_iframe_report(page, seed: dict) -> None:
    page_url = seed["url"]
    controls = get_seed_controls(seed)
    lookup = controls["lookup"]
    target_input = controls["target_input"]

    if not lookup:
        raise ValueError("controls.lookup is required for popup_lookup_iframe_report")
    if not target_input.get("selector"):
        raise ValueError("controls.target_input.selector is required for popup_lookup_iframe_report")

    goto_with_retry(page, page_url)
    page.wait_for_timeout(seed.get("initial_wait_ms", 1000))

    # Apply static inputs/radios before opening the lookup popup if necessary.
    fill_seed_inputs(page, seed)
    click_seed_radios(page, seed)

    popup = open_lookup_popup(page, lookup)
    lookup_values = collect_lookup_values_from_popup(popup, lookup)
    popup.close()

    if not lookup_values:
        print(f"[LOOKUP EMPTY] name={seed.get('name')}")
        return

    combinations = build_seed_select_combinations(page, seed)

    max_lookup_values = seed.get("max_lookup_values")
    if max_lookup_values:
        lookup_values = lookup_values[: int(max_lookup_values)]

    max_combinations = seed.get("max_combinations")
    if max_combinations:
        combinations = combinations[: int(max_combinations)]

    print(
        f"[POPUP LOOKUP IFRAME] "
        f"base_combinations={len(combinations)} lookup_values={len(lookup_values)}"
    )

    for combo in combinations:
        for item_idx, item in enumerate(lookup_values, start=1):
            try:
                goto_with_retry(page, page_url)
                page.wait_for_timeout(seed.get("initial_wait_ms", 1000))

                if seed.get("tab_info"):
                    switch_tab(page, seed["tab_info"])

                apply_seed_controls(page, seed, combo)

                page.locator(target_input["selector"]).fill(item["value"])
                print(
                    f"[LOOKUP APPLY] "
                    f"name={seed.get('name')} "
                    f"target={target_input['selector']} "
                    f"value={item['value']} text={item.get('text')}"
                )

                click_seed_submit(page, seed)

                full_combo = dict(combo)
                full_combo["lookup"] = {
                    "selector": target_input["selector"],
                    "value": item["value"],
                    "text": item.get("text") or item["value"],
                }

                print(
                    f"[POPUP LOOKUP REPORT] "
                    f"{item_idx}/{len(lookup_values)} combo={format_combo_label(full_combo)}"
                )

                save_iframe_report_pdf_for_current_page(
                    page=page,
                    seed=seed,
                    combo=full_combo,
                )

            except Exception as e:
                log_crawl_error(
                    stage="popup_lookup_iframe_report",
                    error=e,
                    source_type=seed.get("source_type"),
                    url=page_url,
                    context={
                        "seed_name": seed.get("name"),
                        "combo": combo,
                        "lookup_item": item,
                    },
                )
                continue


# ---------------------------------------------------------------------
# Click modal table pages
# ---------------------------------------------------------------------

def collect_dap_click_modal_table(page, seed: dict) -> list[dict]:
    row_selector = seed.get("row_selector") or "#CP1_dt_list tr[onclick*='__doPostBack']"

    rows = page.locator(row_selector)
    results = []

    for i in range(rows.count()):
        row = rows.nth(i)

        try:
            cells = row.locator("td").all_inner_texts()
            row_text = " | ".join(t.strip() for t in cells if t.strip())

            row.click(no_wait_after=True)
            page.wait_for_timeout(seed.get("post_click_wait_ms", 2000))

            title_selector = seed.get("modal_title_selector") or "#CP1_lbl_title"
            content_selector = seed.get("modal_content_selector") or "#CP1_txt_contents_pop"
            close_selector = seed.get("modal_close_selector") or "#mymodal button[data-dismiss='modal']"

            title = page.locator(title_selector).inner_text(timeout=5000).strip()
            content_locator = page.locator(content_selector)
            try:
                content = content_locator.input_value(timeout=5000).strip()
            except Exception:
                content = content_locator.inner_text(timeout=5000).strip()

            results.append({
                "row_index": i + 1,
                "row_text": row_text,
                "modal_title": title,
                "modal_content": content,
            })

            close_btn = page.locator(close_selector).first
            if close_btn.count() > 0:
                close_btn.click()
                page.wait_for_timeout(500)

        except Exception as e:
            results.append({
                "row_index": i + 1,
                "error": str(e),
            })

    return results


def save_modal_table_from_current_page(page, seed: dict) -> None:
    source_type = seed["source_type"]
    page_url = seed["url"]

    modal_items = collect_dap_click_modal_table(page, seed)

    raw_text = "\n\n".join(
        f"[{item.get('modal_title', '')}]\n"
        f"{item.get('row_text', '')}\n"
        f"{item.get('modal_content', '')}"
        for item in modal_items
        if item.get("modal_content")
    )

    doc_hash = hashlib.sha1(
        f"{page_url}_{source_type}_{seed.get('tab_info', {}).get('tab_value', '')}".encode("utf-8")
    ).hexdigest()[:16]
    doc_id = f"{source_type}_modal_table_{doc_hash}"

    raw_doc = {
        "doc_id": doc_id,
        "source_type": source_type,
        "page_kind": "dynamic_modal_page",
        "title": seed.get("title") or seed.get("name"),
        "source_url": page_url,
        "published_at": None,
        "updated_at": None,
        "raw_text": raw_text,
        "table_text": "",
        "attachment_text": None,
        "version": 1,
        "collected_at": now_kst_iso(),
        "content_hash": build_content_hash(
            raw_text=raw_text,
            table_text="",
            attachment_text=None,
            image_text=None,
        ),
        "metadata": {
            "seed_name": seed.get("name"),
            "report_type": "click_modal_table",
            "tab_info": seed.get("tab_info"),
            "modal_items": modal_items,
        },
        "attachments": [],
        "downloaded_attachments": [],
        "image_urls": [],
        "image_texts": [],
        "outgoing_links": [],
        "views": None,
    }

    save_document_bundle(raw_doc, download_attachments=False)
    print(f"[CLICK MODAL TABLE OK] doc_id={doc_id} count={len(modal_items)}")


# ---------------------------------------------------------------------
# Seed runners
# ---------------------------------------------------------------------

def run_click_modal_table_seed(seed: dict) -> None:
    with login_dap_with_playwright(headless=True) as page:
        goto_with_retry(page, seed["url"])
        page.wait_for_timeout(seed.get("initial_wait_ms", 3000))
        save_modal_table_from_current_page(page, seed)


def run_current_static_dom_seed(seed: dict) -> None:
    with login_dap_with_playwright(headless=True) as page:
        goto_with_retry(page, seed["url"])
        page.wait_for_timeout(seed.get("initial_wait_ms", 1500))

        if seed.get("tab_info"):
            switch_tab(page, seed["tab_info"])

        save_current_static_page_from_page(page, seed)


def run_authenticated_postback_result_seed(seed: dict) -> None:
    with login_dap_with_playwright(headless=True) as page:
        goto_with_retry(page, seed["url"])
        page.wait_for_timeout(seed.get("initial_wait_ms", 3000))
        run_select_postback_result_from_current_page(page, seed)


def run_authenticated_iframe_report_seed(seed: dict) -> None:
    with login_dap_with_playwright(headless=True) as page:
        goto_with_retry(page, seed["url"])
        page.wait_for_timeout(seed.get("initial_wait_ms", 3000))
        run_iframe_report_from_current_page(page, seed)


def run_authenticated_popup_lookup_iframe_report_seed(seed: dict) -> None:
    with login_dap_with_playwright(headless=True) as page:
        run_popup_lookup_iframe_report(page, seed)


def run_authenticated_static_seed(seed: dict, auth_session) -> None:
    extractor = StaticPageExtractor(
        allowed_hosts=ALLOWED_HOSTS,
        session=auth_session,
        enable_image_ocr=is_login_image_ocr_enabled(seed),
    )

    raw_doc = extractor.extract_static_page(
        source_type=seed["source_type"],
        page_url=seed["url"],
    )

    save_document_bundle(raw_doc, download_attachments=True)

    print(f"[AUTH STATIC OK] name={seed.get('name')} doc_id={raw_doc['doc_id']}")


# ---------------------------------------------------------------------
# DAP board list/detail handling
# ---------------------------------------------------------------------

def normalize_dap_date(text: str | None) -> str | None:
    if not text:
        return None

    text = text.strip()
    m = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})$", text)

    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    return text


def parse_dap_notice_list_html(html: str, list_url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table.table.table-hover tbody tr")
    items = []

    for row in rows:
        cols = row.select("td")

        if len(cols) < 5:
            continue

        link = cols[1].select_one("a[href]")

        if not link:
            continue

        href = link.get("href", "").strip()
        detail_url = urljoin(list_url, href)

        parsed = urlparse(detail_url)
        qs = parse_qs(parsed.query)

        notice_no = (qs.get("NoticeNo") or [None])[0]
        notice_mst = (qs.get("NoticeMst") or [None])[0]

        title = link.get_text(" ", strip=True)
        author = cols[2].get_text(" ", strip=True)
        published_at = normalize_dap_date(cols[3].get_text(" ", strip=True))
        views_text = cols[4].get_text(" ", strip=True)

        try:
            views = int(views_text.replace(",", ""))
        except Exception:
            views = None

        items.append({
            "article_no": notice_no,
            "notice_mst": notice_mst,
            "title_hint": title,
            "detail_url": detail_url,
            "author": author,
            "published_at_hint": published_at,
            "views": views,
        })

    return {
        "count": len(items),
        "items": items,
    }


def detect_tabbed_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    tabs = []

    for li in soup.select("ul.nav.nav-tabs li[onclick*='tabChange']"):
        onclick = li.get("onclick", "")
        m = re.search(r"tabChange\(['\"]([^'\"]+)['\"]\)", onclick)

        if not m:
            continue

        title = li.get_text(" ", strip=True)
        source_type = TAB_SOURCE_TYPE_MAP.get(title)

        if not source_type:
            continue

        tabs.append({
            "tab_title": title,
            "tab_value": m.group(1),
            "source_type": source_type,
            "hidden_selector": "#CP1_hdnNoticeCd",
            "submit_selector": "#CP1_BtnOk",
            "search_input_selector": "#CP1_txtSearchValue",
        })

    return tabs


def switch_tab(page, tab: dict) -> None:
    page.wait_for_selector(tab["hidden_selector"], state="attached", timeout=10000)
    page.wait_for_selector(tab["submit_selector"], timeout=10000)

    page.evaluate(
        """tab => {
            const hidden = document.querySelector(tab.hidden_selector);
            const submit = document.querySelector(tab.submit_selector);
            const search = document.querySelector(tab.search_input_selector);

            if (!hidden) throw new Error('tab hidden input not found');
            if (!submit) throw new Error('tab submit button not found');

            hidden.value = tab.tab_value;
            if (search) search.value = '';

            submit.click();
        }""",
        tab,
    )

    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    page.wait_for_timeout(1000)


def build_tab_seed(seed: dict, tab: dict) -> dict:
    tab_seed = dict(seed)
    tab_seed["name"] = f"{seed.get('name')}_{tab['source_type']}"
    tab_seed["source_type"] = tab["source_type"]
    tab_seed["_tab_expanded"] = True
    tab_seed["tab_info"] = tab
    return tab_seed


def crawl_board_pages_from_current_page(page, seed: dict, auth_session) -> None:
    detail_extractor = BoardDetailExtractor(session=auth_session)

    source_type = seed["source_type"]
    list_url = seed["url"]
    pages = seed.get("pages", 50)

    current_year_start = f"{datetime.now().year}-01-01"
    seen_doc_ids = set()
    stop_crawling = False

    for page_no in range(1, pages + 1):
        if stop_crawling:
            break

        try:
            if page_no > 1:
                pager_selector = f"#CP1_COM_Page_Controllor1_lbtnPage{page_no}"

                if page.locator(pager_selector).count() == 0:
                    print(f"[AUTH BOARD PAGE END] source={source_type} page={page_no}")
                    break

                page.locator(pager_selector).click()

                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                page.wait_for_timeout(1000)

            html = page.content()
            list_result = parse_dap_notice_list_html(html, list_url)

            print(
                f"[AUTH BOARD LIST] "
                f"name={seed.get('name')} source={source_type} "
                f"page={page_no} count={list_result['count']}"
            )

            if list_result["count"] == 0:
                break

            for item in list_result["items"]:
                try:
                    published_at = item.get("published_at_hint")

                    if published_at and published_at < current_year_start:
                        print(
                            f"[AUTH BOARD STOP] source={source_type} "
                            f"{published_at} < {current_year_start}"
                        )
                        stop_crawling = True
                        break

                    raw_doc = detail_extractor.extract_detail(
                        source_type=source_type,
                        detail_url=item["detail_url"],
                        title_hint=item.get("title_hint"),
                    )

                    if item.get("published_at_hint"):
                        raw_doc["published_at"] = item["published_at_hint"]

                    if item.get("views") is not None:
                        raw_doc["views"] = item["views"]

                    if raw_doc["doc_id"] in seen_doc_ids:
                        continue

                    seen_doc_ids.add(raw_doc["doc_id"])
                    save_document_bundle(raw_doc, download_attachments=True)

                    print(
                        f"[AUTH BOARD DETAIL OK] "
                        f"source={source_type} doc_id={raw_doc['doc_id']}"
                    )

                    time.sleep(0.3)

                except Exception as e:
                    log_crawl_error(
                        stage="auth_board_detail",
                        error=e,
                        source_type=source_type,
                        doc_id=(
                            f"deu_{source_type}_{item.get('article_no')}"
                            if item.get("article_no")
                            else None
                        ),
                        url=item.get("detail_url"),
                        context={
                            "seed_name": seed.get("name"),
                            "list_url": list_url,
                            "page_no": page_no,
                            "item": item,
                            "tab_info": seed.get("tab_info"),
                        },
                    )

        except Exception as e:
            log_crawl_error(
                stage="auth_board_list",
                error=e,
                source_type=source_type,
                url=list_url,
                context={
                    "seed_name": seed.get("name"),
                    "page_no": page_no,
                    "tab_info": seed.get("tab_info"),
                },
            )
            break


def run_authenticated_board_seed(seed: dict, auth_session) -> None:
    list_url = seed["url"]

    with login_dap_with_playwright(headless=True) as page:
        goto_with_retry(page, list_url)
        page.wait_for_timeout(2000)

        crawl_board_pages_from_current_page(
            page=page,
            seed=seed,
            auth_session=auth_session,
        )


# ---------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------

def process_dynamic_seed_from_current_page(page, seed: dict, auth_session=None) -> None:
    report_type = seed.get("report_type")

    if report_type == "click_modal_table":
        save_modal_table_from_current_page(page, seed)
    elif report_type == "select_postback_result":
        run_select_postback_result_from_current_page(page, seed)
    elif report_type == "current_static_dom":
        save_current_static_page_from_page(page, seed)
    elif report_type in {"select_iframe_report", "postback_iframe_report"}:
        run_iframe_report_from_current_page(page, seed)
    elif report_type == "popup_lookup_iframe_report":
        run_popup_lookup_iframe_report(page, seed)
    else:
        raise ValueError(f"Unsupported report_type: {report_type}")


def process_tabbed_seed_from_current_page(page, seed: dict, auth_session) -> None:
    page_kind = seed.get("page_kind")

    if page_kind == "board_list":
        crawl_board_pages_from_current_page(
            page=page,
            seed=seed,
            auth_session=auth_session,
        )
        return

    if page_kind == "static_page":
        save_current_static_page_from_page(page, seed)
        return

    if page_kind == "dynamic_report_page":
        process_dynamic_seed_from_current_page(page, seed, auth_session=auth_session)
        return

    raise ValueError(f"Unsupported tabbed page_kind: {page_kind}")


def try_process_tabbed_seed(seed: dict, auth_session) -> bool:
    if seed.get("_tab_expanded"):
        return False

    page_url = seed["url"]

    with login_dap_with_playwright(headless=True) as page:
        goto_with_retry(page, page_url)
        page.wait_for_timeout(2000)

        html = page.content()
        tabs = detect_tabbed_page(html)

        if not tabs:
            return False

        print(f"[TABBED PAGE DETECTED] url={page_url} count={len(tabs)}")

        for tab in tabs:
            tab_seed = build_tab_seed(seed, tab)

            try:
                print(
                    f"[TAB START] title={tab['tab_title']} "
                    f"source={tab['source_type']} value={tab['tab_value']}"
                )

                goto_with_retry(page, page_url)
                page.wait_for_timeout(1000)

                switch_tab(page, tab)

                process_tabbed_seed_from_current_page(
                    page=page,
                    seed=tab_seed,
                    auth_session=auth_session,
                )

            except Exception as e:
                log_crawl_error(
                    stage="tabbed_page",
                    error=e,
                    source_type=tab.get("source_type"),
                    url=page_url,
                    context={
                        "seed_name": seed.get("name"),
                        "tab": tab,
                    },
                )

        return True


def process_child_seed(child_seed: dict, auth_session) -> None:
    if try_process_tabbed_seed(child_seed, auth_session):
        return

    page_kind = child_seed.get("page_kind")

    if page_kind == "board_list":
        run_authenticated_board_seed(child_seed, auth_session)
        return

    if page_kind == "static_page":
        run_authenticated_static_seed(child_seed, auth_session)
        return

    if page_kind == "dynamic_report_page":
        report_type = child_seed.get("report_type")

        if report_type == "click_modal_table":
            run_click_modal_table_seed(child_seed)
        elif report_type == "select_postback_result":
            run_authenticated_postback_result_seed(child_seed)
        elif report_type == "current_static_dom":
            run_current_static_dom_seed(child_seed)
        elif report_type in {"select_iframe_report", "postback_iframe_report"}:
            run_authenticated_iframe_report_seed(child_seed)
        elif report_type == "popup_lookup_iframe_report":
            run_authenticated_popup_lookup_iframe_report_seed(child_seed)
        else:
            raise ValueError(f"Unsupported report_type: {report_type}")

        return

    raise ValueError(f"Unsupported child page_kind: {page_kind}")


def run_login_seed(login_seed: dict) -> None:
    if login_seed.get("page_kind") != "login_page":
        raise ValueError(f"LOGIN_SEEDS only accepts page_kind=login_page: {login_seed}")

    print(f"[LOGIN START] name={login_seed.get('name')} url={login_seed.get('url')}")

    auth_session = build_login_session(login_seed)

    print(f"[LOGIN OK] name={login_seed.get('name')}")

    if login_seed.get("collect_login_page", False):
        try:
            collect_login_page_once(login_seed, auth_session)
        except Exception as e:
            log_crawl_error(
                stage="login_page_collect",
                error=e,
                source_type=login_seed.get("source_type"),
                url=login_seed.get("url"),
                context={
                    "seed_name": login_seed.get("name"),
                    "login_type": login_seed.get("login_type"),
                },
            )

    for child_seed in login_seed.get("children", []):
        try:
            process_child_seed(child_seed, auth_session)
        except Exception as e:
            log_crawl_error(
                stage="login_child_seed",
                error=e,
                source_type=child_seed.get("source_type"),
                url=child_seed.get("url"),
                context={
                    "login_seed_name": login_seed.get("name"),
                    "child_seed": child_seed,
                },
            )


def main() -> None:
    if os.getenv("USE_DAP_LOGIN") != "1":
        print("[SKIP] USE_DAP_LOGIN != 1")
        return

    for login_seed in LOGIN_SEEDS:
        run_login_seed(login_seed)


if __name__ == "__main__":
    try:
        main()
    finally:
        if pgv_loader:
            pgv_loader.close()
