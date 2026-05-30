"""
seeds.py에 정의된 URL과 DB에 저장된 문서를 비교하여 수집 커버리지를 감사합니다.

실행:
    docker compose run --rm crawler python -m crawler.run.audit_seed_coverage
    docker compose run --rm crawler python -m crawler.run.audit_seed_coverage --eval
    docker compose run --rm crawler python -m crawler.run.audit_seed_coverage --url-pattern scheduleList
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from crawler.config.seeds import iter_seed_catalog
from crawler.ingestion.pgvector_loader import PGVectorLoader


EVAL_TARGETS = [
    {
        "label": "학사일정(scheduleList)",
        "url_pattern": "scheduleList",
        "note": "개강일/종강일/계절학기/졸업식 정보",
    },
    {
        "label": "정보공학관 식당",
        "url_pattern": "deu-dining-hall",
        "note": "정보공학관 식당 운영시간",
    },
    {
        "label": "전화번호(phone.do)",
        "url_pattern": "phone.do",
        "note": "교직원/교수 연락처",
    },
    {
        "label": "컴퓨터공학과 교수진(sub02)",
        "url_pattern": "swcc.deu.ac.kr/computer/sub02",
        "note": "장시웅 교수 등 교수진 연락처",
    },
    {
        "label": "컴퓨터공학과 이수표(sub03_01)",
        "url_pattern": "swcc.deu.ac.kr/computer/sub03_01",
        "note": "졸업학점/이수구분표",
    },
    {
        "label": "학생서비스센터(dess)",
        "url_pattern": "dess.deu.ac.kr",
        "note": "휴·복학, 제증명, 학사안내",
    },
    {
        "label": "학과사무실 위치/전화(Page12)",
        "url_pattern": "dess.deu.ac.kr/?mid=Page12",
        "note": "학과사무실 전화번호",
    },
    {
        "label": "상담센터(counsel)",
        "url_pattern": "counsel.deu.ac.kr",
        "note": "학생 상담 서비스",
    },
    {
        "label": "DAP/학사정보시스템(dap)",
        "url_pattern": "dap.deu.ac.kr",
        "note": "성적확인/학적조회 (SSO 로그인 필요)",
    },
]


def get_db_conn():
    loader = PGVectorLoader()
    return loader.conn


def audit_url_pattern(conn, url_pattern: str) -> dict[str, Any]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                COUNT(DISTINCT d.doc_id) AS docs,
                COUNT(DISTINCT dc.doc_id) AS has_content,
                COUNT(DISTINCT c.doc_id) AS has_chunks,
                COUNT(DISTINCT e.chunk_id) AS has_embeddings
            FROM documents d
            LEFT JOIN document_contents dc ON dc.doc_id = d.doc_id
            LEFT JOIN chunks c ON c.doc_id = d.doc_id
            LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
            WHERE d.source_url ILIKE %s
            """,
            (f"%{url_pattern}%",),
        )
        row = dict(cur.fetchone())
    return row


def audit_source_type_coverage(conn) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                d.source_type,
                COUNT(DISTINCT d.doc_id) AS docs,
                COUNT(DISTINCT dc.doc_id) AS has_content,
                COUNT(DISTINCT c.doc_id) AS has_chunks,
                COUNT(DISTINCT e.chunk_id) AS has_embeddings
            FROM documents d
            LEFT JOIN document_contents dc ON dc.doc_id = d.doc_id
            LEFT JOIN chunks c ON c.doc_id = d.doc_id
            LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
            GROUP BY d.source_type
            ORDER BY docs DESC
            """
        )
        return [dict(r) for r in cur.fetchall()]


def audit_seeds_vs_db(conn) -> list[dict]:
    seeds = iter_seed_catalog()
    results = []
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for seed in seeds:
            url = seed["url"]
            cur.execute(
                """
                SELECT COUNT(DISTINCT d.doc_id) AS docs,
                       COUNT(DISTINCT c.doc_id) AS has_chunks,
                       COUNT(DISTINCT e.chunk_id) AS has_embeddings
                FROM documents d
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
                WHERE d.source_url = %s OR d.source_url ILIKE %s
                """,
                (url, f"%{url.split('?')[0]}%"),
            )
            row = dict(cur.fetchone())
            results.append(
                {
                    "seed_name": seed["name"],
                    "url": url,
                    "page_kind": seed.get("page_kind", ""),
                    "source_type": seed.get("source_type", ""),
                    "docs": row["docs"],
                    "has_chunks": row["has_chunks"],
                    "has_embeddings": row["has_embeddings"],
                }
            )
    return results


def print_eval_report(conn) -> None:
    print("\n=== RAG 평가 누락 케이스별 DB 커버리지 ===\n")
    fmt = "{:<35} {:>5} {:>8} {:>8} {:>12}  {}"
    print(fmt.format("항목", "docs", "content", "chunks", "embeddings", "비고"))
    print("-" * 95)
    for t in EVAL_TARGETS:
        r = audit_url_pattern(conn, t["url_pattern"])
        status = "✅" if r["has_chunks"] > 0 else "❌"
        print(
            fmt.format(
                f"{status} {t['label']}"[:35],
                r["docs"],
                r["has_content"],
                r["has_chunks"],
                r["has_embeddings"],
                t["note"],
            )
        )


def print_seeds_report(conn, only_missing: bool = False) -> None:
    rows = audit_seeds_vs_db(conn)
    missing = [r for r in rows if r["docs"] == 0]
    no_chunks = [r for r in rows if r["docs"] > 0 and r["has_chunks"] == 0]

    print(f"\n=== seeds.py vs DB 비교 (총 {len(rows)}개 seed) ===")
    print(f"  DB 미수집: {len(missing)}개")
    print(f"  수집했지만 chunk 없음: {len(no_chunks)}개\n")

    if missing:
        print("--- DB에 없는 seed URL ---")
        for r in missing:
            print(f"  [{r['page_kind']}] {r['seed_name']}: {r['url']}")

    if no_chunks:
        print("\n--- 수집됐지만 chunk가 0인 URL ---")
        for r in no_chunks:
            print(f"  [{r['source_type']}] {r['seed_name']}: docs={r['docs']} url={r['url']}")


def print_coverage_report(conn) -> None:
    rows = audit_source_type_coverage(conn)
    print("\n=== source_type별 커버리지 ===\n")
    fmt = "{:<22} {:>6} {:>8} {:>8} {:>12}"
    print(fmt.format("source_type", "docs", "content", "chunks", "embeddings"))
    print("-" * 62)
    for r in rows:
        chunk_rate = f"{r['has_chunks']/r['docs']*100:.0f}%" if r["docs"] else "-"
        flag = "" if r["has_chunks"] == r["docs"] else " ⚠"
        print(
            fmt.format(r["source_type"][:22], r["docs"], r["has_content"], r["has_chunks"], r["has_embeddings"])
            + f"  ({chunk_rate}{flag})"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="seed 커버리지 감사")
    parser.add_argument("--eval", action="store_true", help="RAG 평가 누락 케이스별 확인")
    parser.add_argument("--seeds", action="store_true", help="seeds.py vs DB 비교")
    parser.add_argument("--coverage", action="store_true", help="source_type별 커버리지")
    parser.add_argument("--url-pattern", help="특정 URL 패턴만 조회")
    parser.add_argument("--all", dest="all_reports", action="store_true", help="전체 보고서")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_all = args.all_reports or not any([args.eval, args.seeds, args.coverage, args.url_pattern])

    loader = PGVectorLoader()
    conn = loader.conn
    try:
        if run_all or args.eval:
            print_eval_report(conn)
        if run_all or args.coverage:
            print_coverage_report(conn)
        if run_all or args.seeds:
            print_seeds_report(conn)
        if args.url_pattern:
            r = audit_url_pattern(conn, args.url_pattern)
            print(f"\n[{args.url_pattern}] docs={r['docs']} content={r['has_content']} chunks={r['has_chunks']} embeddings={r['has_embeddings']}")
    finally:
        loader.close()


if __name__ == "__main__":
    main()
