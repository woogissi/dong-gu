from __future__ import annotations

import argparse
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="크롤링, 청킹, 벡터 적재, RAG 적재 점검을 순서대로 실행합니다.",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help="도움말을 보여주고 종료합니다.")
    parser._optionals.title = "옵션"
    parser.add_argument(
        "--skip-static-discovery",
        action="store_true",
        help="정적 페이지 discovery 단계를 건너뜁니다.",
    )
    parser.add_argument(
        "--skip-full-pipeline",
        action="store_true",
        help="전체 수집 파이프라인 단계를 건너뜁니다.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=200,
        help="static discovery에서 수집할 정적 페이지 최대 개수입니다.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="static discovery의 내부 링크 탐색 최대 깊이입니다.",
    )
    parser.add_argument(
        "--since-date",
        default="2025-12-01",
        help="YYYY-MM-DD 이후 게시글만 수집합니다.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=10,
        help="게시판 seed별로 수집할 목록 페이지 최대 개수입니다.",
    )
    parser.add_argument(
        "--detail-workers",
        type=int,
        default=3,
        help="게시판 상세 페이지 fetch worker 개수입니다.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="벡터 적재에서 한 번에 처리할 chunk batch 크기입니다.",
    )
    parser.add_argument(
        "--allow-insecure-ssl",
        action="store_true",
        help="설정된 구형 DEU 호스트에 한해 SSL 검증 없이 재시도를 허용합니다.",
    )
    parser.add_argument(
        "--force-static-recrawl",
        action="store_true",
        help="이미 처리된 정적 페이지도 다시 수집합니다.",
    )
    parser.add_argument(
        "--fail-on-partial",
        action="store_true",
        help="RAG 적재 점검 결과가 부분 완료 또는 비정상이면 실패 코드로 종료합니다.",
    )
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
