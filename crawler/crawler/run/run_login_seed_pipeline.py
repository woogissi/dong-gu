# crawler/run/run_login_seed_pipeline.py

import hashlib
import os
import re
import time
from datetime import datetime, timezone, timedelta
from itertools import product
from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs
from crawler.auth.dap_auth_session import (
    build_dap_authenticated_session,
    login_dap_with_playwright,
)
from crawler.config.domains import ALLOWED_HOSTS
from crawler.config.login_seeds import LOGIN_SEEDS
from crawler.extractors.board_detail_extractor import BoardDetailExtractor
from crawler.extractors.board_list_extractor import BoardListExtractor
from crawler.extractors.static_page_extractor import StaticPageExtractor
from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.parsers.file_text_router import FileTextRouter
from crawler.run.run_full_pipeline import save_document_bundle
from crawler.utils.content_hash import build_content_hash


KST = timezone(timedelta(hours=9))

pgv_loader = None

try:
    pgv_loader = PGVectorLoader()
except Exception as e:
    print(f"[DB DISABLED] crawl log DB connection failed: {e}")


def clean_option_text(text: str) -> str:
    return re.sub(r"^\d+\s*", "", text or "").strip()


def now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def collect_select_options(page, selector: str) -> list[dict]:
    locator = page.locator(selector)

    if locator.count() == 0:
        return []

    is_disabled = locator.evaluate(
        """el => el.disabled || el.hasAttribute('disabled')"""
    )

    if is_disabled:
        value = locator.input_value()
        text = page.locator(f"{selector} option:checked").inner_text()

        if not value:
            return []

        return [{"value": value, "text": text.strip(), "fixed": True}]

    return page.locator(f"{selector} option").evaluate_all(
        """els => els.map(e => ({
            value: e.value,
            text: e.textContent.trim(),
            fixed: false
        })).filter(x => x.value !== '')"""
    )


def build_select_combinations(page, selects: dict) -> list[dict]:
    option_groups = []

    for logical_name, selector in selects.items():
        options = collect_select_options(page, selector)
        if not options:
            continue

        option_groups.append(
            {
                "logical_name": logical_name,
                "selector": selector,
                "options": options,
            }
        )

    if not option_groups:
        return []

    combinations = []

    for combo in product(*[group["options"] for group in option_groups]):
        item = {}
        for group, option in zip(option_groups, combo):
            item[group["logical_name"]] = {
                "selector": group["selector"],
                "value": option["value"],
                "text": option["text"],
                "fixed": option.get("fixed", False),
            }
        combinations.append(item)

    return combinations


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


def collect_login_page_once(login_seed: dict, auth_session) -> None:
    if not login_seed.get("collect_login_page", True):
        return

    extractor = StaticPageExtractor(
        allowed_hosts=ALLOWED_HOSTS,
        session=auth_session,
    )

    raw_doc = extractor.extract_static_page(
        source_type=login_seed["source_type"],
        page_url=login_seed["url"],
    )

    raw_doc["page_kind"] = "login_page"

    save_document_bundle(
        raw_doc,
        download_attachments=True,
    )

    print(f"[LOGIN PAGE SAVE OK] doc_id={raw_doc['doc_id']}")


def build_dynamic_report_html(
    title: str,
    source_url: str,
    report_url: str,
    combo: dict,
) -> str:
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


def save_and_parse_existing_pdf(
    file_path: Path,
    source_type: str,
    doc_id: str,
    file_name: str,
    file_url: str,
) -> dict:
    raw_file_dir = Path("crawler/data/raw/files") / source_type / doc_id
    raw_file_dir.mkdir(parents=True, exist_ok=True)

    file_name = safe_filename(file_name) or f"{doc_id}.pdf"
    if not file_name.lower().endswith(".pdf"):
        file_name += ".pdf"

    target_path = raw_file_dir / file_name

    if file_path.resolve() != target_path.resolve():
        target_path.write_bytes(file_path.read_bytes())

    pdf_bytes = target_path.read_bytes()

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError(
            f"file is not pdf: path={target_path.as_posix()} file_url={file_url}"
        )

    router = FileTextRouter()
    parse_result = router.extract_text(str(target_path))

    return {
        "attachment_index": 1,
        "file_name": file_name,
        "file_url": file_url,
        "file_ext": ".pdf",
        "saved_path": str(target_path.as_posix()),
        "file_size": target_path.stat().st_size,
        "content_type": "application/pdf",
        "parser_type": parse_result.get("parser_type"),
        "attachment_text": parse_result.get("attachment_text"),
        "page_count": parse_result.get("page_count"),
        "pages": parse_result.get("pages", []),
        "note": parse_result.get("note"),
        "raw_xml_files": parse_result.get("raw_xml_files", []),
    }


def save_and_parse_report_download(
    download,
    source_type: str,
    doc_id: str,
    file_name: str,
) -> dict:
    raw_file_dir = Path("crawler/data/raw/files") / source_type / doc_id
    raw_file_dir.mkdir(parents=True, exist_ok=True)

    suggested_name = download.suggested_filename
    file_name = (
        safe_filename(file_name)
        or safe_filename(suggested_name)
        or f"{doc_id}.pdf"
    )

    if not file_name.lower().endswith(".pdf"):
        file_name += ".pdf"

    file_path = raw_file_dir / file_name
    download.save_as(str(file_path))

    return save_and_parse_existing_pdf(
        file_path=file_path,
        source_type=source_type,
        doc_id=doc_id,
        file_name=file_name,
        file_url=f"download://{suggested_name}",
    )


def get_report_frame(page):
    report_frame = next(
        (
            frame
            for frame in page.frames
            if "CLIPreport4" in (frame.url or "")
        ),
        None,
    )

    if report_frame:
        return report_frame

    # fallback: seed iframe 자체
    outer = next(
        (
            frame
            for frame in page.frames
            if frame.name == "ifrm_rpt" or frame.url.endswith("#")
        ),
        None,
    )

    return outer


def save_debug_html(name: str, html: str) -> None:
    debug_dir = Path("crawler/data/logs/dynamic_report_debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / name
    debug_path.write_text(html, encoding="utf-8", errors="ignore")
    print(f"[DYNAMIC REPORT DEBUG HTML] {debug_path.as_posix()}")


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
    attachment_text = downloaded.get("attachment_text")

    return {
        "doc_id": doc_id,
        "source_type": source_type,
        "page_kind": "dynamic_report_page",
        "department": clean_option_text(
            combo.get("department", {}).get("text", "")
        ),
        "title": title,
        "source_url": page_url,
        "published_at": None,
        "updated_at": None,
        "raw_text": "",
        "normalize": None,
        "table_text": "",
        "attachment_text": attachment_text,
        "version": 1,
        "change_type": None,
        "collected_at": now_kst_iso(),
        "content_hash": build_content_hash(
            raw_text="",
            table_text="",
            attachment_text=attachment_text,
            image_text=None,
        ),
        "html": build_dynamic_report_html(
            title=title,
            source_url=page_url,
            report_url=report_url,
            combo=combo,
        ),
        "metadata": {
            "seed_name": seed.get("name"),
            "select_values": {
                key: {
                    "value": value["value"],
                    "text": value["text"],
                }
                for key, value in combo.items()
            },
            "report_url": report_url,
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


def run_authenticated_dynamic_report_seed(seed: dict) -> None:
    source_type = seed["source_type"]
    page_url = seed["url"]
    submit_selector = seed["submit"]

    with login_dap_with_playwright(headless=True) as page:
        page.goto(page_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        combinations = build_select_combinations(page, seed.get("selects", {}))

        print(f"[DYNAMIC REPORT] select combination count={len(combinations)}")

        for idx, combo in enumerate(combinations, start=1):
            print(f"[DYNAMIC REPORT COMBO] {combo}")

            try:
                for logical_name, selected in combo.items():
                    selector = selected["selector"]
                    value = selected["value"]

                    is_disabled = page.locator(selector).evaluate(
                        """el => el.disabled || el.hasAttribute('disabled')"""
                    )

                    if is_disabled:
                        print(
                            f"[DYNAMIC REPORT SELECT SKIP] disabled "
                            f"{logical_name}={selected.get('text')} value={value}"
                        )
                        continue

                    print(
                        f"[DYNAMIC REPORT SELECT] "
                        f"{logical_name}={selected.get('text')} value={value}"
                    )

                    page.select_option(selector, value)

                combo_text = "_".join(
                    clean_option_text(selected["text"]).replace(" ", "")
                    for selected in combo.values()
                )

                combo_value = "_".join(
                    selected["value"]
                    for selected in combo.values()
                )

                doc_key = f"{page_url}_{combo_value}"
                doc_hash = hashlib.sha1(doc_key.encode("utf-8")).hexdigest()[:16]
                doc_id = f"{source_type}_dynamic_report_{doc_hash}"

                title = f"{combo_text} 학과별 수업시간표"
                file_name = f"{title}.pdf"

                print(f"[DYNAMIC REPORT] {idx}/{len(combinations)} title={title}")

                page.locator(submit_selector).click(no_wait_after=True)
                page.wait_for_timeout(5000)

                print(
                    "[DYNAMIC REPORT IFRAMES] ",
                    [
                        {
                            "name": frame.name,
                            "url": frame.url,
                        }
                        for frame in page.frames
                    ],
                )

                report_frame = get_report_frame(page)

                if not report_frame:
                    raise ValueError("report frame not found")

                print(f"[REPORT FRAME URL] {report_frame.url}")

                try:
                    save_debug_html(
                        f"{doc_id}_report_frame.html",
                        report_frame.content(),
                    )
                except Exception as debug_error:
                    print(f"[REPORT FRAME DEBUG SKIP] {debug_error}")

                pdf_button = report_frame.locator(".report_menu_pdf_button")
                pdf_button.wait_for(timeout=30000)

                print(
                    "[DYNAMIC REPORT PDF BUTTON COUNT] "
                    f"{pdf_button.count()}"
                )

                network_logs: list[dict] = []

                def on_response(res):
                    try:
                        url = res.url
                        if "report.deu.ac.kr" not in url and "CLIPreport4" not in url:
                            return

                        network_logs.append(
                            {
                                "status": res.status,
                                "url": url,
                                "content_type": res.headers.get("content-type"),
                            }
                        )

                        print(
                            f"[NETWORK] {res.status} {url} "
                            f"{res.headers.get('content-type')}"
                        )
                    except Exception:
                        return

                page.on("response", on_response)

                try:
                    download = None

                    try:
                        with page.expect_download(timeout=5000) as download_info:
                            pdf_button.click()
                        download = download_info.value
                    except Exception as download_error:
                        print(f"[DOWNLOAD EVENT SKIP] {download_error}")

                    page.wait_for_timeout(10000)

                    if download:
                        report_url = f"download://{download.suggested_filename}"

                        print(
                            f"[DYNAMIC REPORT DOWNLOAD] "
                            f"suggested_filename={download.suggested_filename}"
                        )

                        downloaded = save_and_parse_report_download(
                            download=download,
                            source_type=source_type,
                            doc_id=doc_id,
                            file_name=file_name,
                        )
                    else:
                        # 다운로드 이벤트가 없으면 여기서는 저장하지 않고,
                        # 네트워크 로그를 기반으로 다음 단계 URL을 확인한다.
                        raise ValueError(
                            "PDF download was not captured. "
                            f"network_logs={network_logs[:20]}"
                        )

                finally:
                    page.remove_listener("response", on_response)

                if not downloaded.get("attachment_text"):
                    print(f"[DYNAMIC REPORT SKIP] empty pdf text doc_id={doc_id}")
                    continue

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

                save_document_bundle(
                    raw_doc,
                    download_attachments=True,
                )

                print(f"[DYNAMIC REPORT PDF OK] doc_id={doc_id}")

            except Exception as e:
                log_crawl_error(
                    stage="dynamic_report_pdf",
                    error=e,
                    source_type=source_type,
                    url=page_url,
                    context={
                        "seed_name": seed.get("name"),
                        "combo": combo,
                    },
                )
                continue


def run_authenticated_static_seed(seed: dict, auth_session) -> None:
    extractor = StaticPageExtractor(
        allowed_hosts=ALLOWED_HOSTS,
        session=auth_session,
    )

    raw_doc = extractor.extract_static_page(
        source_type=seed["source_type"],
        page_url=seed["url"],
    )

    save_document_bundle(
        raw_doc,
        download_attachments=True,
    )

    print(f"[AUTH STATIC OK] name={seed.get('name')} doc_id={raw_doc['doc_id']}")


def run_authenticated_board_seed(seed: dict, auth_session) -> None:
    detail_extractor = BoardDetailExtractor(session=auth_session)

    source_type = seed["source_type"]
    list_url = seed["url"]
    pages = seed.get("pages", 50)

    current_year_start = f"{datetime.now().year}-01-01"
    seen_doc_ids = set()
    stop_crawling = False

    with login_dap_with_playwright(headless=True) as page:
        page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)

        for page_no in range(1, pages + 1):
            if stop_crawling:
                break

            try:
                if page_no > 1:
                    pager_selector = f"#CP1_COM_Page_Controllor1_lbtnPage{page_no}"

                    if page.locator(pager_selector).count() == 0:
                        print(f"[AUTH BOARD PAGE END] page={page_no}")
                        break

                    page.locator(pager_selector).click()
                    page.wait_for_timeout(1500)

                html = page.content()
                list_result = parse_dap_notice_list_html(html, list_url)

                print(
                    f"[AUTH BOARD LIST] "
                    f"name={seed.get('name')} page={page_no} count={list_result['count']}"
                )

                if list_result["count"] == 0:
                    break

                for item in list_result["items"]:
                    try:
                        published_at = item.get("published_at_hint")

                        if published_at and published_at < current_year_start:
                            print(
                                f"[AUTH BOARD STOP] "
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

                        save_document_bundle(
                            raw_doc,
                            download_attachments=True,
                        )

                        print(f"[AUTH BOARD DETAIL OK] doc_id={raw_doc['doc_id']}")

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
                    },
                )
                break


def process_child_seed(child_seed: dict, auth_session) -> None:
    page_kind = child_seed.get("page_kind")

    if page_kind == "board_list":
        run_authenticated_board_seed(child_seed, auth_session)
        return

    if page_kind == "static_page":
        run_authenticated_static_seed(child_seed, auth_session)
        return

    if page_kind == "dynamic_report_page":
        run_authenticated_dynamic_report_seed(child_seed)
        return

    raise ValueError(f"Unsupported child page_kind: {page_kind}")


def run_login_seed(login_seed: dict) -> None:
    if login_seed.get("page_kind") != "login_page":
        raise ValueError(f"LOGIN_SEEDS only accepts page_kind=login_page: {login_seed}")

    print(f"[LOGIN START] name={login_seed.get('name')} url={login_seed.get('url')}")

    auth_session = build_login_session(login_seed)

    print(f"[LOGIN OK] name={login_seed.get('name')}")

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


def normalize_dap_date(text: str | None) -> str | None:
    if not text:
        return None

    text = text.strip()

    # 2026.05.20 -> 2026-05-20
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

        items.append(
            {
                "article_no": notice_no,
                "notice_mst": notice_mst,
                "title_hint": title,
                "detail_url": detail_url,
                "author": author,
                "published_at_hint": published_at,
                "views": views,
            }
        )

    return {
        "count": len(items),
        "items": items,
    }

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