from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from crawler.utils.text_quality import attachment_text_quality_report, text_quality_report


DEFAULT_REPORT_PATH = Path("reports/live_deu_integration_smoke.json")
NOISE_TERMS = (
    "HOME",
    "로그인",
    "공유",
    "페이스북",
    "트위터",
    "카카오톡 공유",
    "URL 복사",
    "프린트",
    "게시물 검색",
    "게시판 목록",
    "번호 제목 작성자 작성일 조회수",
    "이전글 다음글",
)


@dataclass(frozen=True)
class SmokeSample:
    name: str
    sample_type: str
    url: str
    source_type: str


DEFAULT_SAMPLES = (
    SmokeSample(
        name="p0_board_notice_dormitory",
        sample_type="board_notice",
        source_type="dormitory",
        url=(
            "https://www.deu.ac.kr/www/deu-dormitory.do?"
            "articleNo=79843&mode=view&title=2026%ED%95%99%EB%85%84%EB%8F%84+1%ED%95%99%EA%B8%B0+"
            "%ED%9A%A8%EB%AF%BC%EC%83%9D%ED%99%9C%EA%B4%80+%EB%B0%8F+%ED%96%89%EB%B3%B5"
            "%EA%B8%B0%EC%88%99%EC%82%AC+%EA%B4%80%EC%83%9D+%ED%86%B5%ED%95%A9%EB%AA%A8"
            "%EC%A7%91+%EC%95%88%EB%82%B4"
        ),
    ),
    SmokeSample(
        name="static_main_www",
        sample_type="static_main",
        source_type="homepage",
        url="https://www.deu.ac.kr/www/index.do",
    ),
    SmokeSample(
        name="department_attachment_police",
        sample_type="department_attachment_page",
        source_type="department",
        url=(
            "https://www.deu.ac.kr/police/sub03_02.do?"
            "articleNo=68647&mode=view&title=%5B%EB%8F%99%EC%9D%98%EB%8C%80%ED%95%99%EA%B5%90%5D+"
            "%EA%B5%90%EC%9C%A1%ED%98%81%EC%8B%A0%EC%9B%90+%EC%A0%84%EA%B3%B5%EC%84%A4"
            "%EA%B3%84%EC%A7%80%EC%9B%90%EC%84%BC%ED%84%B0+%ED%99%8D%EB%B3%B4"
        ),
    ),
    SmokeSample(
        name="admission_guide_pdf",
        sample_type="admission_pdf",
        source_type="admission",
        url=(
            "https://ipsi.deu.ac.kr/file/pdfDown.pdf?"
            "ofn=2026%ED%95%99%EB%85%84%EB%8F%84+%EC%88%98%EC%8B%9C+%EB%AA%A8%EC%A7%91"
            "%EC%9A%94%EA%B0%95%28%EB%8F%99%EC%9D%98%EB%8C%80%29.pdf&"
            "sfn=20251014062047048_2026%ED%95%99%EB%85%84%EB%8F%84+%EC%88%98%EC%8B%9C+"
            "%EB%AA%A8%EC%A7%91%EC%9A%94%EA%B0%95%28%EB%8F%99%EC%9D%98%EB%8C%80%29.pdf&"
            "sfp=common%2F"
        ),
    ),
)


def host_for(url: str) -> str:
    return urlparse(url).netloc.lower()


def ok_step(name: str, **details) -> dict:
    return {"name": name, "ok": True, "details": details}


def fail_step(name: str, error: str, **details) -> dict:
    return {"name": name, "ok": False, "error": error, "details": details}


def text_noise_hits(text: str | None) -> list[str]:
    if not text:
        return []
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return [term for term in NOISE_TERMS if term in compact]


def chunk_summary(doc: dict) -> dict:
    from crawler.ingestion.chunker import DocumentChunker

    chunks = DocumentChunker(max_chars=900).chunk_document(doc)
    attachment_chunks = [chunk for chunk in chunks if chunk.get("section_type") == "attachment"]
    return {
        "chunk_count": len(chunks),
        "attachment_chunk_count": len(attachment_chunks),
        "chunk_target": bool(chunks),
    }


def document_gate_summary(doc: dict) -> dict:
    fields = {
        "raw": doc.get("raw_text"),
        "clean": doc.get("normalize") or doc.get("raw_text"),
        "table": doc.get("table_text"),
        "attachment": doc.get("attachment_text"),
    }
    report = {
        name: text_quality_report(value)
        for name, value in fields.items()
        if value and str(value).strip()
    }
    bad_fields = [name for name, item in report.items() if item["is_binary_like"]]
    return {
        "quality_gate_passed": not bool(bad_fields),
        "bad_fields": bad_fields,
        "quality": report,
    }


def parse_downloaded_attachment(downloaded: dict) -> dict:
    from crawler.parsers.file_text_router import FileTextRouter

    parse_result = FileTextRouter().extract_text(downloaded["saved_path"])
    quality = attachment_text_quality_report(
        parse_result.get("attachment_text"),
        parser_name=parse_result.get("parser_type"),
        page_count=parse_result.get("page_count"),
        tables=parse_result.get("attachment_tables", []),
    )
    content_eligible = quality["quality_status"] == "ok"
    return {
        "parser_name": parse_result.get("parser_type"),
        "parser_ran": bool(parse_result.get("parser_type")),
        "parser_note": parse_result.get("note"),
        "extracted_text_exists": bool((parse_result.get("attachment_text") or "").strip()),
        "extracted_text_length": quality["extracted_text_length"],
        "page_count": quality["page_count"],
        "text_per_page": quality["text_per_page"],
        "table_detected": quality["table_detected"],
        "binary_marker_detected": quality["binary_marker_detected"],
        "quality_status": quality["quality_status"],
        "quality_reason": quality["quality_reason"],
        "document_contents_eligible": content_eligible,
        "chunk_embedding_eligible": content_eligible,
        "quality": quality,
    }


def attachment_smoke(
    *,
    sample: SmokeSample,
    attachment: dict,
    temp_dir: Path,
    timeout: tuple[float, float],
) -> dict:
    from crawler.extractors.attachment_downloader import AttachmentDownloader

    steps = []
    downloader = AttachmentDownloader(base_save_dir=temp_dir, timeout=timeout)
    try:
        downloaded = downloader.download(sample.source_type, sample.name, attachment)
        steps.append(
            ok_step(
                "attachment_download",
                file_url=downloaded.get("file_url"),
                content_type=downloaded.get("content_type"),
                content_disposition=downloaded.get("content_disposition"),
                file_ext=downloaded.get("file_ext"),
                extension_source=downloaded.get("extension_source"),
                file_size=downloaded.get("file_size"),
            )
        )
    except Exception as exc:
        steps.append(fail_step("attachment_download", str(exc), file_url=attachment.get("file_url")))
        return {"steps": steps, "ok": False}

    try:
        parsed = parse_downloaded_attachment(downloaded)
        steps.append(ok_step("attachment_parse", **parsed))
    except Exception as exc:
        steps.append(fail_step("attachment_parse", str(exc), file_url=attachment.get("file_url")))
        return {"steps": steps, "ok": False, "downloaded": downloaded}

    ext_ok = bool(downloaded.get("file_ext"))
    if not ext_ok:
        steps.append(fail_step("extension_inference", "missing_extension", file_url=attachment.get("file_url")))
    else:
        steps.append(
            ok_step(
                "extension_inference",
                file_ext=downloaded.get("file_ext"),
                extension_source=downloaded.get("extension_source"),
            )
        )

    blocked_binary = (
        parsed["binary_marker_detected"]
        and not parsed["document_contents_eligible"]
        and not parsed["chunk_embedding_eligible"]
    )
    if parsed["binary_marker_detected"] and not blocked_binary:
        steps.append(fail_step("binary_marker_gate", "binary-like attachment would be stored", quality=parsed["quality"]))
    else:
        steps.append(
            ok_step(
                "binary_marker_gate",
                binary_marker_detected=parsed["binary_marker_detected"],
                document_contents_eligible=parsed["document_contents_eligible"],
                chunk_embedding_eligible=parsed["chunk_embedding_eligible"],
            )
        )

    return {
        "ok": all(step["ok"] for step in steps),
        "downloaded": downloaded,
        "steps": steps,
    }


def html_sample_smoke(sample: SmokeSample, temp_dir: Path, timeout: tuple[float, float]) -> dict:
    from crawler.extractors.board_detail_extractor import BoardDetailExtractor
    from crawler.extractors.static_page_extractor import StaticPageExtractor

    steps = []
    extractor = (
        BoardDetailExtractor(timeout=timeout)
        if sample.sample_type == "board_notice"
        else StaticPageExtractor(allowed_hosts={host_for(sample.url)}, timeout=timeout)
    )
    try:
        doc = (
            extractor.extract_detail(sample.source_type, sample.url)
            if sample.sample_type == "board_notice"
            else extractor.extract_static_page(sample.source_type, sample.url)
        )
        fetch = (doc.get("metadata") or {}).get("fetch", {})
        steps.append(
            ok_step(
                "http_download",
                status_code=fetch.get("status_code"),
                final_url=fetch.get("final_url"),
                content_type=(fetch.get("headers") or {}).get("Content-Type"),
            )
        )
    except Exception as exc:
        steps.append(fail_step("html_extract", str(exc), url=sample.url))
        return {"sample": asdict(sample), "ok": False, "steps": steps}

    raw_text = doc.get("raw_text") or ""
    if raw_text.strip():
        steps.append(ok_step("html_body_extract", title=doc.get("title"), text_length=len(raw_text)))
    else:
        steps.append(fail_step("html_body_extract", "empty_raw_text", title=doc.get("title")))

    noise_hits = text_noise_hits(raw_text)
    if noise_hits:
        steps.append(fail_step("noise_filter", "noise_terms_found", noise_hits=noise_hits))
    else:
        steps.append(ok_step("noise_filter", checked_terms=list(NOISE_TERMS)))

    gate = document_gate_summary(doc)
    if gate["quality_gate_passed"]:
        steps.append(ok_step("document_quality_gate", **gate))
    else:
        steps.append(fail_step("document_quality_gate", "binary_like_html_or_text", **gate))

    chunks = chunk_summary({**doc, "normalize": doc.get("normalize") or doc.get("raw_text")})
    if chunks["chunk_target"]:
        steps.append(ok_step("chunk_target", **chunks))
    else:
        steps.append(fail_step("chunk_target", "no_chunks_created", **chunks))

    attachment_results = []
    attachments = doc.get("attachments") or []
    if sample.sample_type in {"board_notice", "department_attachment_page"}:
        if not attachments:
            steps.append(fail_step("attachment_discovery", "no_attachments_found"))
        else:
            steps.append(ok_step("attachment_discovery", attachment_count=len(attachments), first=attachments[0]))
            attachment_results.append(
                attachment_smoke(
                    sample=sample,
                    attachment=attachments[0],
                    temp_dir=temp_dir,
                    timeout=timeout,
                )
            )

    return {
        "sample": asdict(sample),
        "ok": all(step["ok"] for step in steps) and all(item["ok"] for item in attachment_results),
        "steps": steps,
        "attachments": attachment_results,
    }


def pdf_sample_smoke(sample: SmokeSample, temp_dir: Path, timeout: tuple[float, float]) -> dict:
    attachment = {
        "attachment_index": 1,
        "file_name": sample.name,
        "file_url": sample.url,
    }
    result = attachment_smoke(sample=sample, attachment=attachment, temp_dir=temp_dir, timeout=timeout)
    return {
        "sample": asdict(sample),
        "ok": result["ok"],
        "steps": result["steps"],
        "attachments": [result],
    }


def run_smoke(
    *,
    samples: tuple[SmokeSample, ...] = DEFAULT_SAMPLES,
    report_path: Path = DEFAULT_REPORT_PATH,
    timeout: tuple[float, float] = (5, 30),
) -> dict:
    with tempfile.TemporaryDirectory(prefix="deu_live_smoke_") as tmp:
        temp_dir = Path(tmp)
        results = []
        for sample in samples:
            if sample.sample_type == "admission_pdf":
                results.append(pdf_sample_smoke(sample, temp_dir, timeout))
            else:
                results.append(html_sample_smoke(sample, temp_dir, timeout))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(result["ok"] for result in results),
        "sample_count": len(results),
        "samples": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opt-in live integration smoke test for selected DEU crawler URLs.")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Required guard flag. Without this, no network request is made.",
    )
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--connect-timeout", type=float, default=5)
    parser.add_argument("--read-timeout", type=float, default=30)
    return parser.parse_args()


def print_human_summary(report: dict) -> None:
    status = "OK" if report["ok"] else "FAILED"
    print(f"[DEU LIVE SMOKE {status}] samples={report['sample_count']}")
    for sample in report["samples"]:
        sample_status = "OK" if sample["ok"] else "FAILED"
        print(f"- {sample['sample']['name']} ({sample['sample']['sample_type']}): {sample_status}")
        for step in sample.get("steps", []):
            if not step["ok"]:
                print(f"  * {step['name']}: {step.get('error')} {step.get('details')}")
        for attachment in sample.get("attachments", []):
            for step in attachment.get("steps", []):
                if not step["ok"]:
                    print(f"  * attachment {step['name']}: {step.get('error')} {step.get('details')}")


def main() -> None:
    args = parse_args()
    if not args.execute_live:
        print("[DEU LIVE SMOKE SKIP] pass --execute-live to fetch real DEU pages")
        return

    report = run_smoke(
        report_path=Path(args.report_path),
        timeout=(args.connect_timeout, args.read_timeout),
    )
    print_human_summary(report)
    print(f"[DEU LIVE SMOKE REPORT] {Path(args.report_path).as_posix()}")
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
