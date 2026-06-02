"""첨부 파싱 품질 진단: 깨진 PDF/HWP/이미지 OCR 청크를 휴리스틱으로 탐색.

실행: docker compose run --rm rag python -m rag.evaluation.goldset._diagnose_attachments
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict

import psycopg2
from psycopg2.extras import DictCursor

_MARKER_RE = re.compile(r"\[(?:TITLE|BODY|ATTACHMENT|TABLE)\]")
_HANGUL_RE = re.compile(r"[가-힣]")
_JAMO_RE = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]")
_FILE_EXT_RE = re.compile(r"\.(?:pdf|hwp|hwpx|xlsx|pptx|docx|zip|jpg|png)", re.IGNORECASE)
_BINARY_RE = re.compile(r"[�\x00-\x08\x0b\x0c\x0e-\x1f]")


def assess(content: str) -> list[str]:
    flags: list[str] = []
    if not content or not content.strip():
        return ["empty"]
    stripped = _MARKER_RE.sub("", content)
    nospace = re.sub(r"\s", "", stripped)
    total = len(nospace)
    if total < 10:
        return ["too_short"]

    hangul = len(_HANGUL_RE.findall(nospace))
    jamo = len(_JAMO_RE.findall(nospace))
    digit = sum(c.isdigit() for c in nospace)
    latin = len(re.findall(r"[A-Za-z]", nospace))
    cjk = len(re.findall(r"[一-鿿]", nospace))

    if jamo / total > 0.04:
        flags.append("broken_jamo")          # 자모 분리 (OCR 조합 실패)
    if _BINARY_RE.search(stripped):
        flags.append("binary_residue")       # 제어/대체 문자
    if total > 60 and hangul / total < 0.25:
        # 영문/중문 병기(다국어)나 숫자 위주 표는 깨짐이 아니므로 구분
        if (latin + cjk) / total > 0.35:
            flags.append("multilingual")     # 외국어 병기 — 깨짐 아님(참고)
        elif digit / total > 0.45:
            flags.append("numeric_table")    # 숫자 위주 표 — 깨짐 아닐 수 있음(참고)
        else:
            flags.append("low_hangul")       # 한글 비율 낮음 (진짜 의심)

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if lines:
        dl = sum(1 for ln in lines if "download" in ln.lower() or _FILE_EXT_RE.search(ln))
        if dl / len(lines) > 0.35 and len(lines) >= 4:
            flags.append("attachment_list_only")   # 첨부 파일명 나열뿐
        short = sum(1 for ln in lines if len(re.sub(r"\s", "", ln)) <= 3)
        if len(lines) >= 12 and short / len(lines) > 0.5:
            flags.append("table_linearized")       # 표가 선형 파편으로 깨짐

    # 동일 토큰 과다 반복
    tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", stripped)
    if len(tokens) >= 20:
        most = Counter(tokens).most_common(1)[0][1]
        if most / len(tokens) > 0.25:
            flags.append("repetitive")
    return flags


def main() -> None:
    dsn = os.getenv("DATABASE_URL") or (
        f"postgresql://{os.getenv('POSTGRES_USER','chatbot')}:{os.getenv('POSTGRES_PASSWORD','chatbot')}"
        f"@{os.getenv('POSTGRES_HOST','postgres')}:{os.getenv('POSTGRES_PORT','5432')}/{os.getenv('POSTGRES_DB','chatbot')}"
    )
    conn = psycopg2.connect(dsn.replace("postgresql+psycopg2://", "postgresql://"))
    with conn.cursor(cursor_factory=DictCursor) as cur:
        cur.execute(
            """
            SELECT c.doc_id, c.chunk_id, c.section_type, c.content, c.content_length,
                   d.title, d.source_type, d.source_url
            FROM chunks c JOIN documents d ON d.doc_id = c.doc_id
            WHERE c.section_type IN ('attachment', 'table')
            """
        )
        rows = cur.fetchall()

    total = len(rows)
    flag_counts: Counter = Counter()
    by_source: dict[str, Counter] = defaultdict(Counter)
    broken_docs: dict[str, dict] = {}

    real_broken = {"broken_jamo", "binary_residue", "low_hangul",
                   "table_linearized", "attachment_list_only", "repetitive"}
    for r in rows:
        flags = assess(r["content"] or "")
        clean_flags = [f for f in flags if f not in ("empty", "too_short")]
        st = r["source_type"] or "?"
        by_source[st]["total"] += 1
        for f in clean_flags:
            flag_counts[f] += 1
        broken_here = [f for f in clean_flags if f in real_broken]
        if broken_here:
            by_source[st]["broken"] += 1
            d = broken_docs.setdefault(r["doc_id"], {
                "title": r["title"], "source_type": st, "source_url": r["source_url"],
                "flags": Counter(), "chunks": 0,
            })
            d["chunks"] += 1
            for f in broken_here:
                d["flags"][f] += 1

    print(f"=== 첨부/표 청크 진단: 총 {total}개 ===")
    print(f"깨짐 의심 청크: {sum(flag_counts.values())}건(중복 플래그 포함), 문서 {len(broken_docs)}개\n")
    print("[플래그별 청크 수]")
    for f, c in flag_counts.most_common():
        print(f"  {f:<22}: {c}")

    print("\n[source_type별 깨짐 비율]")
    for st, cnt in sorted(by_source.items(), key=lambda x: -x[1].get("broken", 0)):
        t = cnt["total"]; b = cnt.get("broken", 0)
        if t:
            print(f"  {st:<20}: {b}/{t} ({b/t:.0%})")

    print("\n[깨짐 의심 문서 상위 20 (청크 수 기준)]")
    ranked = sorted(broken_docs.items(), key=lambda x: -x[1]["chunks"])[:20]
    for doc_id, info in ranked:
        flags = ",".join(f"{k}×{v}" for k, v in info["flags"].most_common())
        print(f"  [{info['source_type']}] {doc_id} (청크 {info['chunks']}) | {flags}")
        print(f"      {(info['title'] or '')[:46]} | {info['source_url']}")

    # OCR 표 재구성 직접 타겟: table_linearized / broken_jamo 보유 문서
    ocr_targets = {
        k: v for k, v in broken_docs.items()
        if v["flags"].get("table_linearized") or v["flags"].get("broken_jamo")
    }

    # 타겟 문서의 원본 보존 상태 조회 (재파싱 vs 재크롤링 판정)
    target_ids = list(ocr_targets.keys())
    asset_status: dict[str, dict] = {}
    if target_ids:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute(
                """
                SELECT doc_id,
                       array_agg(DISTINCT parser_type) AS parsers,
                       bool_or(saved_path IS NOT NULL AND saved_path <> '') AS has_path
                FROM document_assets
                WHERE doc_id = ANY(%s)
                GROUP BY doc_id
                """,
                (target_ids,),
            )
            for row in cur.fetchall():
                asset_status[row["doc_id"]] = {"parsers": row["parsers"], "has_path": row["has_path"]}

    reparse_ok, recrawl = [], []
    for doc_id, info in ocr_targets.items():
        st = asset_status.get(doc_id)
        if st and st["has_path"]:
            reparse_ok.append((doc_id, info, st["parsers"]))
        else:
            recrawl.append((doc_id, info, st["parsers"] if st else ["(inline/no-asset)"]))

    print(f"\n[OCR 표 재구성 타겟: {len(ocr_targets)}개 문서]")
    print(f"  - 원본 보존(재파싱으로 직접 수정 가능): {len(reparse_ok)}개")
    print(f"  - 원본 미보존(재크롤링 필요): {len(recrawl)}개")

    print(f"\n[재파싱 가능 (원본 파일 보존) 상위 20]")
    for doc_id, info, parsers in sorted(reparse_ok, key=lambda x: -x[1]["flags"].get("table_linearized", 0))[:20]:
        flags = ",".join(f"{k}×{v}" for k, v in info["flags"].most_common())
        print(f"  [{info['source_type']}/{','.join(parsers)}] {doc_id} | {flags}")
        print(f"      {(info['title'] or '')[:46]}")

    print(f"\n[재크롤링 필요 (원본 미보존) 상위 15]")
    for doc_id, info, parsers in sorted(recrawl, key=lambda x: -x[1]["flags"].get("table_linearized", 0))[:15]:
        flags = ",".join(f"{k}×{v}" for k, v in info["flags"].most_common())
        print(f"  [{info['source_type']}/{','.join(parsers)}] {doc_id} | {flags}")
        print(f"      {(info['title'] or '')[:46]}")


if __name__ == "__main__":
    main()
