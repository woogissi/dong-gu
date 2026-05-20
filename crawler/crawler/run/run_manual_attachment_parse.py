# crawler/run/run_manual_attachment_parse.py

import json
import os
from pathlib import Path

from crawler.parsers.file_text_router import FileTextRouter
from crawler.paths import CURATED_DOC_DIR, LOG_DIR, RAW_DOC_DIR, RAW_FILE_DIR
from crawler.utils.content_hash import build_content_hash
from crawler.utils.text_quality import attachment_text_quality_report


LOG_DIR.mkdir(parents=True, exist_ok=True)


def allow_needs_review_attachment_chunks() -> bool:
    return os.getenv("CRAWLER_ALLOW_NEEDS_REVIEW_ATTACHMENT_CHUNKS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def log_error(message: str) -> None:
    print(message)
    with open(LOG_DIR / "manual_attachment_parse_errors.log", "a", encoding="utf-8") as f:
        f.write(message + "\n")


def merge_attachment_texts(downloaded_attachments: list[dict]) -> str | None:
    texts = []

    for item in downloaded_attachments:
        text = item.get("attachment_text")
        file_name = item.get("file_name")

        if text:
            quality = attachment_text_quality_report(
                text,
                parser_name=item.get("parser_type"),
                parser_status=item.get("parse_status"),
                page_count=item.get("page_count"),
                tables=item.get("attachment_tables", []),
            )
            if quality["quality_status"] == "parse_failed" or (
                quality["quality_status"] == "needs_review"
                and not allow_needs_review_attachment_chunks()
            ):
                item["attachment_text"] = None
                item["quality_status"] = quality["quality_status"]
                item["quality"] = quality
                item["note"] = f"attachment text skipped before curated merge: {quality['quality_reason']}"
                continue
            texts.append(f"[ATTACHMENT: {file_name}]\n{text}")

    merged = "\n\n".join(texts).strip()
    return merged if merged else None


def collect_manual_file_dirs() -> list[tuple[str, str, Path]]:
    """
    crawler/data/raw/files/{source_type}/{doc_id}/ 구조 전체 탐색
    """
    targets = []

    if not RAW_FILE_DIR.exists():
        return targets

    for source_type_dir in RAW_FILE_DIR.iterdir():
        if not source_type_dir.is_dir():
            continue

        source_type = source_type_dir.name

        for doc_dir in source_type_dir.iterdir():
            if not doc_dir.is_dir():
                continue

            doc_id = doc_dir.name
            targets.append((source_type, doc_id, doc_dir))

    return sorted(targets, key=lambda x: (x[0], x[1]))


def collect_files(doc_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in doc_dir.iterdir()
        if path.is_file()
    )


def already_registered(file_path: Path, downloaded_attachments: list[dict]) -> bool:
    """
    이미 raw_doc["downloaded_attachments"]에 저장된 파일인지 확인
    saved_path 또는 file_name 기준으로 검사
    """
    file_name = file_path.name
    saved_path = file_path.as_posix()

    for item in downloaded_attachments:
        existing_name = item.get("file_name")
        existing_path = item.get("saved_path")

        if existing_name == file_name:
            return True

        if existing_path:
            normalized_existing_path = Path(existing_path).as_posix()
            if normalized_existing_path == saved_path:
                return True

    return False


def next_attachment_index(downloaded_attachments: list[dict]) -> int:
    indexes = [
        item.get("attachment_index")
        for item in downloaded_attachments
        if isinstance(item.get("attachment_index"), int)
    ]

    return max(indexes, default=0) + 1


def parse_missing_attachments_for_doc(
    source_type: str,
    doc_id: str,
    doc_dir: Path,
    router: FileTextRouter,
) -> tuple[int, int]:
    """
    반환값:
    (parsed_count, skipped_count)
    """
    raw_doc_path = RAW_DOC_DIR / source_type / f"{doc_id}.json"
    curated_doc_path = CURATED_DOC_DIR / source_type / f"{doc_id}.json"

    if not raw_doc_path.exists():
        print(f"[SKIP] raw document not found: {raw_doc_path}")
        return 0, 1

    if not curated_doc_path.exists():
        print(f"[SKIP] curated document not found: {curated_doc_path}")
        return 0, 1

    files = collect_files(doc_dir)
    if not files:
        return 0, 0

    raw_doc = load_json(raw_doc_path)
    curated_doc = load_json(curated_doc_path)

    downloaded_attachments = raw_doc.get("downloaded_attachments") or []

    parsed_count = 0
    skipped_count = 0
    changed = False

    for file_path in files:
        if already_registered(file_path, downloaded_attachments):
            skipped_count += 1
            continue

        try:
            parse_result = router.extract_text(str(file_path))
            attachment_text = parse_result.get("attachment_text")
            attachment_quality = attachment_text_quality_report(
                attachment_text,
                parser_name=parse_result.get("parser_type"),
                page_count=parse_result.get("page_count"),
                tables=parse_result.get("attachment_tables", []),
            )
            quality_status = str(attachment_quality.get("quality_status") or "needs_review")
            parse_status = str(attachment_quality.get("parser_status") or "parser_success")
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
            if not should_store_attachment_text:
                attachment_text = None

            attachment_index = next_attachment_index(downloaded_attachments)

            downloaded = {
                "attachment_index": attachment_index,
                "file_name": file_path.name,
                "file_url": f"manual://{file_path.name}",
                "file_ext": file_path.suffix.lower(),
                "saved_path": str(file_path.as_posix()),
                "file_size": file_path.stat().st_size,
                "content_type": None,
                "parser_type": parse_result.get("parser_type"),
                "parser_name": parse_result.get("parser_type"),
                "parser_status": parse_status,
                "attachment_text": attachment_text,
                "page_count": parse_result.get("page_count"),
                "pages": parse_result.get("pages", []),
                "attachment_tables": parse_result.get("attachment_tables", []),
                "parse_status": parse_status,
                "extracted_text_length": attachment_quality.get("extracted_text_length"),
                "text_per_page": attachment_quality.get("text_per_page"),
                "korean_ratio": attachment_quality.get("korean_ratio"),
                "digit_ratio": attachment_quality.get("digit_ratio"),
                "binary_marker_detected": attachment_quality.get("binary_marker_detected"),
                "table_detected": attachment_quality.get("table_detected"),
                "note": (
                    f"attachment text skipped after parse: {attachment_quality['quality_reason']}"
                    if not should_store_attachment_text
                    else parse_result.get("note") or "manually parsed attachment"
                ),
                "quality_status": quality_status,
                "quality_reason": attachment_quality.get("quality_reason"),
                "quality": attachment_quality,
                "raw_xml_files": parse_result.get("raw_xml_files", []),
            }

            downloaded_attachments.append(downloaded)
            parsed_count += 1
            changed = True

            print(
                f"[PARSE OK] doc_id={doc_id} "
                f"file={file_path.name} "
                f"parser={parse_result.get('parser_type')} "
                f"text_len={len(attachment_text or '')}"
            )

        except Exception as e:
            message = f"[PARSE ERROR] doc_id={doc_id} file={file_path.as_posix()} error={e}"
            log_error(message)

    if not changed:
        return parsed_count, skipped_count

    attachment_text = merge_attachment_texts(downloaded_attachments)

    raw_doc["downloaded_attachments"] = downloaded_attachments
    raw_doc["attachment_text"] = attachment_text

    curated_doc["attachment_text"] = attachment_text

    new_hash = build_content_hash(
        raw_text=curated_doc.get("raw_text"),
        table_text=curated_doc.get("table_text"),
        attachment_text=curated_doc.get("attachment_text"),
        image_text=curated_doc.get("image_text"),
    )

    old_hash = curated_doc.get("content_hash")
    old_version = curated_doc.get("version", 1)

    raw_doc["content_hash"] = new_hash
    curated_doc["content_hash"] = new_hash

    if old_hash != new_hash:
        new_version = old_version + 1
        raw_doc["version"] = new_version
        curated_doc["version"] = new_version
        raw_doc["change_type"] = "updated"
        curated_doc["change_type"] = "updated"
    else:
        raw_doc["version"] = old_version
        curated_doc["version"] = old_version
        raw_doc["change_type"] = raw_doc.get("change_type", "unchanged")
        curated_doc["change_type"] = curated_doc.get("change_type", "unchanged")

    save_json(raw_doc_path, raw_doc)
    save_json(curated_doc_path, curated_doc)

    print(
        f"[DOC UPDATED] doc_id={doc_id} "
        f"parsed={parsed_count} skipped={skipped_count} "
        f"version={old_version}->{curated_doc.get('version')}"
    )

    return parsed_count, skipped_count


def main():
    router = FileTextRouter()
    targets = collect_manual_file_dirs()

    print(f"[INFO] raw file document dirs found: {len(targets)}")

    total_parsed = 0
    total_skipped = 0

    for source_type, doc_id, doc_dir in targets:
        parsed_count, skipped_count = parse_missing_attachments_for_doc(
            source_type=source_type,
            doc_id=doc_id,
            doc_dir=doc_dir,
            router=router,
        )

        total_parsed += parsed_count
        total_skipped += skipped_count

    print(
        f"[DONE] manual attachment parse finished "
        f"parsed={total_parsed} skipped={total_skipped}"
    )


if __name__ == "__main__":
    main()
