from __future__ import annotations

from urllib.parse import urldefrag


def canonical_attachment_url(url: str | None) -> str:
    if not url:
        return ""
    canonical, _fragment = urldefrag(str(url).strip())
    return canonical


def dedupe_attachments_by_url(attachments: list[dict]) -> list[dict]:
    deduped = []
    seen_urls: set[str] = set()

    for attachment in attachments:
        canonical_url = canonical_attachment_url(attachment.get("file_url"))
        if not canonical_url or canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        item = dict(attachment)
        item["file_url"] = canonical_url
        item["attachment_index"] = len(deduped) + 1
        deduped.append(item)

    return deduped
