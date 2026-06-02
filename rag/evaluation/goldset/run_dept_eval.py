"""학과/학년/학기 이수표 질의 오탐 측정 (수정 전후 비교용).

dept_eval_cases.yaml 케이스를 파이프라인에 태워 다음을 측정한다.
- dept_filter_extracted: filters.department 가 추출되었는지 (수정 ① 핵심 지표)
- context_hit: 정답 학과 이수표 doc 가 selected_docs 에 포함되는지
- top1_match: selected 1순위가 정답 학과 doc 인지
- top5_hit: retrieved 상위 5에 정답이 있는지

실행:
  docker compose run --rm rag python -m rag.evaluation.goldset.run_dept_eval --tag before
  docker compose run --rm rag python -m rag.evaluation.goldset.run_dept_eval --tag after
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rag.evaluation.goldset.run_goldset_eval import _check_hit, _extract_docs
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query

_CASES = Path(__file__).parent / "dept_eval_cases.yaml"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="run", help="결과 파일 태그 (before/after)")
    ap.add_argument("--cases", default=str(_CASES), help="평가 케이스 YAML 경로")
    args = ap.parse_args()

    cases = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))["goldset"]
    print(f"[dept-eval] 케이스 {len(cases)}개 | tag={args.tag} | cases={args.cases}")

    pipeline = ChatPipeline()
    try:
        pipeline.initialize()
    except Exception as e:
        print(f"[경고] 임베더 초기화 실패: {e}")

    rows = []
    for i, case in enumerate(cases, 1):
        q = case["question"]
        gold = case.get("gold_documents") or []
        try:
            pipeline.run(Query(text=q))
        except Exception as e:
            print(f"  [{case['id']}] 파이프라인 오류: {e}")
        state = pipeline.last_state
        dept_filter = (state.filters or {}).get("department") if state else None
        selected = _extract_docs(state.selected_docs) if state else []
        retrieved = _extract_docs(state.retrieved_docs) if state else []
        ctx_hit = any(_check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold) for d in selected)
        top1_match = bool(selected) and _check_hit(selected[0]["doc_id"], selected[0]["source_url"], selected[0]["chunk_id"], gold)
        top5_hit = any(_check_hit(d["doc_id"], d["source_url"], d["chunk_id"], gold) for d in retrieved[:5])
        top1_doc = selected[0]["doc_id"] if selected else "-"
        top1_title = (selected[0]["title"] if selected else "-") or "-"
        rows.append({
            "id": case["id"], "question": q,
            "dept_filter": dept_filter, "dept_filter_ok": bool(dept_filter),
            "context_hit": ctx_hit, "top1_match": top1_match, "top5_hit": top5_hit,
            "top1_doc": top1_doc, "top1_title": top1_title[:30],
        })
        flag = "OK " if top1_match else ("CTX" if ctx_hit else "MISS")
        print(f"  [{case['id']}] {flag} dept={dept_filter} top1={top1_title[:26]!r} <= {q}")

    n = len(rows)
    summ = {
        "tag": args.tag, "n": n,
        "dept_filter_rate": round(sum(r["dept_filter_ok"] for r in rows) / n, 3),
        "context_hit_rate": round(sum(r["context_hit"] for r in rows) / n, 3),
        "top1_match_rate": round(sum(r["top1_match"] for r in rows) / n, 3),
        "top5_hit_rate": round(sum(r["top5_hit"] for r in rows) / n, 3),
    }
    print("\n=== 요약 ({}): n={} ===".format(args.tag, n))
    print(f"  학과필터 추출률 : {summ['dept_filter_rate']:.0%}")
    print(f"  Context Hit     : {summ['context_hit_rate']:.0%}")
    print(f"  Top1 학과일치   : {summ['top1_match_rate']:.0%}")
    print(f"  Top5 Hit        : {summ['top5_hit_rate']:.0%}")

    out = Path(__file__).parent / f"dept_eval_{args.tag}.json"
    out.write_text(json.dumps({"summary": summ, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dept-eval] 저장: {out}")


if __name__ == "__main__":
    main()
