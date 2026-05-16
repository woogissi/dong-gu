from __future__ import annotations

import argparse
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run crawl, chunk, vector index, and RAG smoke check.")
    parser.add_argument("--skip-static-discovery", action="store_true")
    parser.add_argument("--skip-full-pipeline", action="store_true")
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--since-date", default="2025-12-01")
    parser.add_argument("--pages", type=int, default=10)
    parser.add_argument("--detail-workers", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--allow-insecure-ssl", action="store_true")
    parser.add_argument("--force-static-recrawl", action="store_true")
    parser.add_argument("--fail-on-partial", action="store_true")
    return parser.parse_args()


def run_step(name: str, command: list[str], summary: list[dict]) -> None:
    started = time.monotonic()
    print(f"[RUN START] {name}: {' '.join(command)}", flush=True)
    result = subprocess.run(command, check=False)
    elapsed = round(time.monotonic() - started, 2)
    summary.append({"step": name, "returncode": result.returncode, "elapsed_seconds": elapsed})
    print(f"[RUN END] {name}: returncode={result.returncode} elapsed={elapsed}s", flush=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    args = parse_args()
    summary: list[dict] = []

    if not args.skip_static_discovery:
        command = [
            sys.executable,
            "-m",
            "crawler.run.run_static_discovery",
            "--closed-loop-discovery",
            "--max-pages",
            str(args.max_pages),
            "--max-depth",
            str(args.max_depth),
        ]
        if args.allow_insecure_ssl:
            command.append("--allow-insecure-ssl")
        run_step("static_discovery", command, summary)

    if not args.skip_full_pipeline:
        command = [
            sys.executable,
            "-m",
            "crawler.run.run_full_pipeline",
            "--closed-loop-discovery",
            "--incremental",
            "--since-date",
            args.since_date,
            "--pages",
            str(args.pages),
            "--compress-raw-html",
            "--detail-workers",
            str(args.detail_workers),
        ]
        if args.allow_insecure_ssl:
            command.append("--allow-insecure-ssl")
        if args.force_static_recrawl:
            command.append("--force-static-recrawl")
        run_step("full_pipeline", command, summary)

    run_step("chunking", [sys.executable, "-m", "crawler.run.run_ingestion_pipeline"], summary)
    run_step(
        "vector_ingestion",
        [sys.executable, "-m", "crawler.run.run_vector_ingestion", "--batch-size", str(args.batch_size)],
        summary,
    )
    smoke_command = [sys.executable, "-m", "crawler.run.run_rag_load_check"]
    if args.fail_on_partial:
        smoke_command.append("--fail-on-partial")
    run_step("rag_smoke_check", smoke_command, summary)

    print("[RUN SUMMARY]", flush=True)
    for item in summary:
        print(
            f"- {item['step']}: returncode={item['returncode']} elapsed={item['elapsed_seconds']}s",
            flush=True,
        )


if __name__ == "__main__":
    main()
