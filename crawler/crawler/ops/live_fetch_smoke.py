from __future__ import annotations

import argparse

from crawler.extractors.base import GenericExtractor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opt-in live network smoke test for one crawler URL.")
    parser.add_argument("--url", required=True, help="URL to fetch.")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="Required guard flag. Without this, no network request is made.",
    )
    parser.add_argument("--connect-timeout", type=float, default=5)
    parser.add_argument("--read-timeout", type=float, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.execute_live:
        print("[LIVE SMOKE SKIP] pass --execute-live to make a network request")
        return

    extractor = GenericExtractor(timeout=(args.connect_timeout, args.read_timeout))
    result = extractor.fetch_result(args.url)
    content_type = result.headers.get("Content-Type") or result.headers.get("content-type")
    print(
        "[LIVE SMOKE OK] "
        f"status={result.status_code} final_url={result.final_url} "
        f"content_type={content_type} bytes={len(result.raw_html.encode('utf-8'))}"
    )


if __name__ == "__main__":
    main()
