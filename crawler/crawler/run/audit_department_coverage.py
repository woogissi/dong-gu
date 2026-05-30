"""
각 학과 홈페이지에서 sub02.do(교수 정보), sub03_01.do(이수표) URL을 자동 탐색하고
DB 수집 현황과 비교하여 누락 목록을 출력합니다.

실행:
    docker compose run --rm crawler python -m crawler.run.audit_department_coverage
    docker compose run --rm crawler python -m crawler.run.audit_department_coverage --fetch  # 실제 HTTP 확인
    docker compose run --rm crawler python -m crawler.run.audit_department_coverage --show-seeds  # seeds.py 추가 코드 출력
"""
from __future__ import annotations

import argparse
import concurrent.futures
import re
import urllib3
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from psycopg2.extras import RealDictCursor

from crawler.ingestion.pgvector_loader import PGVectorLoader

urllib3.disable_warnings()

DEPARTMENT_URLS = [
    ("태권도학과", "https://tkd.deu.ac.kr"),
    ("화장품공학과", "https://dce.deu.ac.kr"),
    ("경영학과·회계학과", "https://busunessadministration.deu.ac.kr"),
    ("경찰행정학과", "https://police2001.deu.ac.kr"),
    ("심리학과", "https://psychology.deu.ac.kr"),
    ("건축공학과", "https://archieng.deu.ac.kr"),
    ("일본학과", "https://japan.deu.ac.kr"),
    ("레저스포츠학과", "https://deuhome.deu.ac.kr/leisure/index.do"),
    ("AI다문화상담학과", "https://multicounsel.deu.ac.kr"),
    ("스마트창업경영학과", "https://sei.deu.ac.kr/sei/index.do"),
    ("문헌정보학과", "https://lis.deu.ac.kr"),
    ("라이프복지학과", "https://llc.deu.ac.kr/llc/index.do"),
    ("뷰티비즈니스학과", "https://bb.deu.ac.kr/bb/index.do"),
    ("부동산자산경영학과", "https://rdm.deu.ac.kr/rdm/index.do"),
    ("창업투자경영학과", "https://eim.deu.ac.kr/eim/index.do"),
    ("응급구조학과", "https://ems.deu.ac.kr"),
    ("국어국문학과", "https://koreanl.deu.ac.kr"),
    ("스마트항만물류학과", "https://logistics.deu.ac.kr"),
    ("K-뷰티학과", "https://kbeauty.deu.ac.kr"),
    ("금융경영학과", "https://banin.deu.ac.kr"),
    ("중어중국학과", "https://china.deu.ac.kr/chi"),
    ("영어영문학과", "https://english.deu.ac.kr"),
    ("평생교육상담학과", "https://lifelonged.deu.ac.kr"),
    ("아동학과", "https://childfamily.deu.ac.kr"),
    ("유아교육과", "https://ece.deu.ac.kr"),
    ("광고홍보학과", "https://ad.deu.ac.kr"),
    ("미디어커뮤니케이션학과", "https://massmedia.deu.ac.kr"),
    ("법학과", "https://law.deu.ac.kr"),
    ("소방방재행정학과", "https://fire.deu.ac.kr"),
    ("행정학과", "https://pap.deu.ac.kr"),
    ("사회복지학과", "https://socialwelfare.deu.ac.kr"),
    ("디지털콘텐츠학과", "https://dcc.deu.ac.kr"),
    ("재무부동산학과", "https://deuhome.deu.ac.kr/fre/index.do"),
    ("무역학과", "https://trade.deu.ac.kr"),
    ("유통물류학과", "https://dm.deu.ac.kr"),
    ("경영정보학과", "https://mis.deu.ac.kr"),
    ("e비즈니스학과", "https://ebiz.deu.ac.kr"),
    ("국제관광경영학과", "https://newtour.deu.ac.kr"),
    ("호텔·컨벤션경영학과", "https://hotel.deu.ac.kr"),
    ("외식경영학과", "https://neweatingout.deu.ac.kr"),
    ("스마트호스피탈리티학과", "https://shp.deu.ac.kr"),
    ("시니어스포츠지도학과", "https://seniorsp.deu.ac.kr"),
    ("간호학과", "https://nursing.deu.ac.kr"),
    ("임상병리학과", "https://1cls.deu.ac.kr"),
    ("치위생학과", "https://dental.deu.ac.kr"),
    ("방사선학과", "https://radiology.deu.ac.kr"),
    ("의료경영학과", "https://hcm1.deu.ac.kr"),
    ("물리치료학과", "https://pt.deu.ac.kr"),
    ("식품영양학과", "https://fn.deu.ac.kr"),
    ("한의예과", "https://omc.deu.ac.kr"),
    ("기계공학과", "https://nme.deu.ac.kr"),
    ("로봇공학과", "https://mecha.deu.ac.kr"),
    ("자동차공학과", "https://automotive-engineering.deu.ac.kr"),
    ("조선해양공학과", "https://naoe.deu.ac.kr"),
    ("신소재공학과", "https://mse.deu.ac.kr"),
    ("건축학과", "https://deuproarchi.deu.ac.kr"),
    ("토목공학과", "https://civil.deu.ac.kr"),
    ("도시공학과", "https://urban.deu.ac.kr"),
    ("환경공학과", "https://env.deu.ac.kr"),
    ("화학공학과", "https://cheng.deu.ac.kr"),
    ("의생명공학과", "https://biotech.deu.ac.kr"),
    ("바이오의약공학과", "https://biopharm.deu.ac.kr"),
    ("식품공학과", "https://efood.deu.ac.kr"),
    ("인간공학과", "https://hsde.deu.ac.kr"),
    ("산업경영빅데이터공학과", "https://pite.deu.ac.kr"),
    ("제품디자인공학과", "https://pdm.deu.ac.kr"),
    ("전기공학과", "https://elec.deu.ac.kr"),
    ("전자공학과", "https://ee.deu.ac.kr"),
    ("첨단에너지공학과", "https://energy.deu.ac.kr"),
    ("미래모빌리티학과", "https://futuremobility.deu.ac.kr"),
    ("소프트웨어융합대학", "https://swcc.deu.ac.kr"),
    ("컴퓨터공학과", "https://swcc.deu.ac.kr/computer/index.do"),
    ("컴퓨터소프트웨어공학과", "https://swcc.deu.ac.kr/se/index.do"),
    ("응용소프트웨어공학과", "https://swcc.deu.ac.kr/asw/index.do"),
    ("인공지능학과", "https://swcc.deu.ac.kr/ai/index.do"),
    ("게임공학과", "https://swcc.deu.ac.kr/game/index.do"),
    ("디지털융합학과", "https://sw.deu.ac.kr"),
    ("음악학과", "https://music.deu.ac.kr"),
    ("디자인조형학과", "https://designart.deu.ac.kr"),
    ("패션디자인학과", "https://fashion.deu.ac.kr"),
    ("체육학과", "https://deptpe.deu.ac.kr"),
    ("경기지도학과", "https://sportscoaching.deu.ac.kr"),
    ("영화학과", "https://cinema.deu.ac.kr"),
]

SUB02_RE = re.compile(r"/sub02(?:_\d+)?\.do", re.I)
SUB03_RE = re.compile(r"/sub03(?:_\d+)?\.do", re.I)


def discover_sub_urls(dept_name: str, base_url: str) -> dict:
    """학과 메인 페이지에서 sub02/sub03 URL을 자동 발견."""
    result = {
        "dept": dept_name,
        "base_url": base_url,
        "sub02_url": None,
        "sub03_url": None,
        "error": None,
    }
    try:
        r = requests.get(base_url, timeout=10, verify=False, allow_redirects=True)
        if r.status_code != 200:
            result["error"] = f"HTTP {r.status_code}"
            return result

        soup = BeautifulSoup(r.text, "html.parser")
        seen_sub02, seen_sub03 = set(), set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith("#") or href.startswith("javascript"):
                continue
            abs_url = urljoin(r.url, href)
            path = urlparse(abs_url).path.lower()
            if SUB02_RE.search(path) and abs_url not in seen_sub02:
                seen_sub02.add(abs_url)
            if SUB03_RE.search(path) and abs_url not in seen_sub03:
                seen_sub03.add(abs_url)

        if seen_sub02:
            # sub02.do 우선, 없으면 sub02_01.do
            result["sub02_url"] = next(
                (u for u in sorted(seen_sub02) if u.endswith("sub02.do")),
                sorted(seen_sub02)[0],
            )
        if seen_sub03:
            result["sub03_url"] = next(
                (u for u in sorted(seen_sub03) if "sub03_01" in u),
                next(
                    (u for u in sorted(seen_sub03) if u.endswith("sub03.do")),
                    sorted(seen_sub03)[0],
                ),
            )
    except Exception as e:
        result["error"] = str(e)[:60]
    return result


def check_db(conn, url_pattern: str) -> dict:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                COUNT(DISTINCT d.doc_id) AS docs,
                COUNT(DISTINCT c.doc_id) AS has_chunks,
                COUNT(DISTINCT e.chunk_id) AS has_embeddings
            FROM documents d
            LEFT JOIN chunks c ON c.doc_id = d.doc_id
            LEFT JOIN chunk_embeddings e ON e.chunk_id = c.chunk_id
            WHERE d.source_url ILIKE %s
            """,
            (f"%{url_pattern}%",),
        )
        return dict(cur.fetchone())


def verify_url(url: str) -> bool:
    try:
        r = requests.head(url, timeout=6, verify=False, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="학과별 sub02/sub03 커버리지 감사")
    parser.add_argument("--fetch", action="store_true", help="각 학과 메인 페이지를 실제로 크롤링하여 URL 발견")
    parser.add_argument("--show-seeds", action="store_true", help="seeds.py에 추가할 코드 출력")
    parser.add_argument("--only-missing", action="store_true", help="DB 미수집 항목만 출력")
    parser.add_argument("--workers", type=int, default=8, help="병렬 워커 수")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    loader = PGVectorLoader()
    conn = loader.conn

    print(f"총 {len(DEPARTMENT_URLS)}개 학과 분석 중...\n")

    results = []

    if args.fetch:
        print(f"[HTTP] {len(DEPARTMENT_URLS)}개 학과 메인 페이지 탐색 (workers={args.workers})...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(discover_sub_urls, name, url): (name, url) for name, url in DEPARTMENT_URLS}
            for fut in concurrent.futures.as_completed(futs):
                results.append(fut.result())
        results.sort(key=lambda r: r["dept"])
    else:
        # HTTP 없이 seeds.py의 기존 패턴에서 유추
        from crawler.config.seeds import iter_seed_catalog
        seed_urls = {s["url"] for s in iter_seed_catalog()}
        for dept, base in DEPARTMENT_URLS:
            results.append({"dept": dept, "base_url": base, "sub02_url": None, "sub03_url": None, "error": None})

    # DB 비교
    print(f"{'학과':<22} {'sub02(교수)':<6} {'sub03(이수표)':<7} {'비고'}")
    print("-" * 72)

    missing_sub02 = []
    missing_sub03 = []

    for r in results:
        sub02_db = sub03_db = None
        sub02_status = sub03_status = "?"

        if r["sub02_url"]:
            key = urlparse(r["sub02_url"]).path.split("/sub02")[0].rstrip("/").split("/")[-1] or urlparse(r["sub02_url"]).netloc
            sub02_db = check_db(conn, r["sub02_url"].split("?")[0])
            if sub02_db["docs"] > 0:
                sub02_status = f"✅{sub02_db['docs']}d/{sub02_db['has_chunks']}c"
            else:
                sub02_status = "❌없음"
                missing_sub02.append(r)
        elif not args.fetch:
            # DB에서 도메인 패턴으로 검색
            netloc = urlparse(r["base_url"]).netloc
            path_base = urlparse(r["base_url"]).path.split("/index.do")[0].rstrip("/")
            pattern = f"{netloc}{path_base}/sub02"
            sub02_db = check_db(conn, pattern)
            if sub02_db["docs"] > 0:
                sub02_status = f"✅{sub02_db['docs']}d/{sub02_db['has_chunks']}c"
            else:
                sub02_status = "❌없음"
                missing_sub02.append(r)

        if r["sub03_url"]:
            sub03_db = check_db(conn, r["sub03_url"].split("?")[0])
            if sub03_db["docs"] > 0:
                sub03_status = f"✅{sub03_db['docs']}d"
            else:
                sub03_status = "❌없음"
                missing_sub03.append(r)
        elif not args.fetch:
            netloc = urlparse(r["base_url"]).netloc
            path_base = urlparse(r["base_url"]).path.split("/index.do")[0].rstrip("/")
            pattern = f"{netloc}{path_base}/sub03"
            sub03_db = check_db(conn, pattern)
            if sub03_db["docs"] > 0:
                sub03_status = f"✅{sub03_db['docs']}d"
            else:
                sub03_status = "❌없음"
                missing_sub03.append(r)

        err = f" [{r['error']}]" if r.get("error") else ""
        sub02_disp = r["sub02_url"] or "(미발견)"
        sub03_disp = r["sub03_url"] or "(미발견)"

        if args.only_missing and "❌" not in sub02_status and "❌" not in sub03_status:
            continue

        print(f"{r['dept']:<22} {sub02_status:<14} {sub03_status:<14}{err}")
        if args.fetch and r["sub02_url"]:
            print(f"  sub02: {sub02_disp[:80]}")
        if args.fetch and r["sub03_url"]:
            print(f"  sub03: {sub03_disp[:80]}")

    loader.close()
    print()
    print(f"[요약] sub02 미수집: {len(missing_sub02)}개 | sub03 미수집: {len(missing_sub03)}개")

    if args.show_seeds and args.fetch:
        print("\n# ===== seeds.py에 추가할 코드 =====")
        for r in missing_sub02:
            if r["sub02_url"]:
                print(f'"{r["sub02_url"]}",  # {r["dept"]} 교수 정보')
        for r in missing_sub03:
            if r["sub03_url"]:
                print(f'"{r["sub03_url"]}",  # {r["dept"]} 이수표')


if __name__ == "__main__":
    main()
