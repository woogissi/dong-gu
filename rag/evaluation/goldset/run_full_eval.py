"""RAG 파이프라인 전체 성능 평가 (다회 평균).

goldset 66문항을 N회(기본 3회) 실행하여:
- 결정적 retrieval 지표(Top-1/3/5, Context Hit)의 안정성 확인
- 비결정적 answer 지표(Grounded/Correct/Refused)의 평균±변동(min~max)
- 지연(latency) 분포 — 전체 및 단계별(retrieve/generate 등)
- 카테고리/난이도/소스타입별 검색 성능
- 실패 분류 + 케이스 안정성(매 실행 결과가 바뀌는 flaky 케이스 식별)
를 집계해 종합 리포트(`full_eval_report.md`)와 원자료(`full_eval_runs.json`)를 생성한다.

실행:
    docker compose run --rm rag python -m rag.evaluation.goldset.run_full_eval
    docker compose run --rm rag python -m rag.evaluation.goldset.run_full_eval --runs 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from rag.evaluation.goldset.run_goldset_eval import compute_summary, evaluate_case, load_goldset
from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query

_DIR = Path(__file__).parent


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 파이프라인 전체 성능 평가(다회)")
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="반복 실행 횟수 (latency 프로파일은 1회로 충분, 정답 안정성 분석 시 3 권장)",
    )
    args = parser.parse_args()

    goldset = load_goldset()
    print(f"[full-eval] 케이스 {len(goldset)}개 × {args.runs}회 실행")

    pipeline = ChatPipeline()
    try:
        pipeline.initialize()
    except Exception as e:  # pragma: no cover - 임베더 초기화 실패 진단용
        print(f"[경고] 임베더 초기화 실패: {e}")

    run_results: list[list[dict]] = []
    run_summaries: list[dict] = []
    case_total_ms: list[float] = []
    stage_ms: dict[str, list[float]] = defaultdict(list)
    substage_ms: dict[str, list[float]] = defaultdict(list)
    retrieval_call_ms: dict[str, list[float]] = defaultdict(list)
    per_case_correct: dict[str, list[bool]] = defaultdict(list)
    per_case_refused: dict[str, list[bool]] = defaultdict(list)
    per_case_meta: dict[str, dict] = {}

    for run_idx in range(1, args.runs + 1):
        print(f"\n[full-eval] === Run {run_idx}/{args.runs} ===")
        results: list[dict] = []
        for i, case in enumerate(goldset, 1):
            cid = case["id"]
            t0 = time.perf_counter()
            try:
                answer = pipeline.run(Query(text=case["question"]))
                state = pipeline.last_state
                elapsed = (time.perf_counter() - t0) * 1000.0
                result = evaluate_case(case, state, answer.answer if answer else "")
                result["elapsed_ms"] = round(elapsed)
                case_total_ms.append(elapsed)
                for t in state.metadata.get("timings_ms", []) or []:
                    stage_ms[t.get("stage", "?")].append(float(t.get("elapsed_ms", 0)))
                for t in state.metadata.get("substage_timings_ms", []) or []:
                    key = f"{t.get('parent', '?')} › {t.get('substage', '?')}"
                    substage_ms[key].append(float(t.get("elapsed_ms", 0)))
                for t in state.metadata.get("retrieval_timings_ms", []) or []:
                    retrieval_call_ms[t.get("label", "?")].append(float(t.get("elapsed_ms", 0)))
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000.0
                result = {
                    "id": cid, "category": case.get("category"), "question": case.get("question"),
                    "difficulty": case.get("difficulty"), "source_type": case.get("source_type"),
                    "error": str(e), "top1_hit": False, "top3_hit": False, "top5_hit": False,
                    "context_hit": False, "answer_grounded": False, "answer_correct": False,
                    "answer_refused": False, "failure_stage": "pipeline_error", "elapsed_ms": round(elapsed),
                    "gold_documents": case.get("gold_documents", []),
                }
            results.append(result)
            per_case_correct[cid].append(bool(result.get("answer_correct")))
            per_case_refused[cid].append(bool(result.get("answer_refused")))
            per_case_meta[cid] = {
                "question": case.get("question"), "category": case.get("category"),
                "difficulty": case.get("difficulty"),
            }
            if i % 10 == 0:
                print(f"    {i}/{len(goldset)} ...")
        run_results.append(results)
        run_summaries.append(compute_summary(results))

    _write_report(args.runs, goldset, run_summaries, run_results,
                  case_total_ms, stage_ms, substage_ms, retrieval_call_ms,
                  per_case_correct, per_case_refused, per_case_meta)


def _agg(run_summaries: list[dict], key: str) -> dict:
    vals = [s.get(key) for s in run_summaries if s.get(key) is not None]
    if not vals:
        return {"mean": None, "min": None, "max": None, "vals": []}
    return {"mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals), "vals": vals}


def _write_report(runs, goldset, run_summaries, run_results, case_total_ms, stage_ms,
                  substage_ms, retrieval_call_ms,
                  per_case_correct, per_case_refused, per_case_meta) -> None:
    n = len(goldset)
    det_keys = ["top1_hit_rate", "top3_hit_rate", "top5_hit_rate", "context_hit_rate"]
    ans_keys = ["answer_grounded_rate", "answer_correct_rate", "answer_refused_rate"]

    def fmt(a):
        if a["mean"] is None:
            return "N/A"
        if a["min"] == a["max"]:
            return f"{a['mean']:.1%}"
        return f"{a['mean']:.1%}  ({a['min']:.1%}~{a['max']:.1%})"

    det = {k: _agg(run_summaries, k) for k in det_keys}
    ans = {k: _agg(run_summaries, k) for k in ans_keys}

    lines = [
        "# RAG 파이프라인 전체 성능 평가 (다회 평균)",
        "",
        f"생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"실행 구성: goldset {n}문항 × {runs}회 (총 {n*runs}회 호출)",
        "",
        "## 1. 핵심 지표 (다회 평균, 괄호=변동폭)",
        "",
        "| 지표 | 값 | 성격 |",
        "|---|---:|---|",
        f"| Top-1 Hit | {fmt(det['top1_hit_rate'])} | 결정적 |",
        f"| Top-3 Hit | {fmt(det['top3_hit_rate'])} | 결정적 |",
        f"| Top-5 Hit | {fmt(det['top5_hit_rate'])} | 결정적 |",
        f"| **Context Hit** | **{fmt(det['context_hit_rate'])}** | 결정적 |",
        f"| Answer Grounded | {fmt(ans['answer_grounded_rate'])} | 비결정(LLM) |",
        f"| **Answer Correct** | **{fmt(ans['answer_correct_rate'])}** | 비결정(LLM) |",
        f"| Answer Refused | {fmt(ans['answer_refused_rate'])} | 비결정(LLM) |",
        "",
        "> 결정적 지표(검색·선택)는 매 실행 동일해야 한다. 비결정 지표(LLM 생성)는 gpt-4o-mini 분산으로 진동하므로 다회 평균으로 본다.",
        "",
        "### 실행별 원값",
        "",
        "| Run | Top-1 | Top-5 | Context | Grounded | Correct | Refused |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, s in enumerate(run_summaries, 1):
        cr = s.get("answer_correct_rate")
        lines.append(
            f"| {i} | {s.get('top1_hit_rate',0):.1%} | {s.get('top5_hit_rate',0):.1%} | "
            f"{s.get('context_hit_rate',0):.1%} | {s.get('answer_grounded_rate',0):.1%} | "
            f"{(cr if cr is not None else 0):.1%} | {s.get('answer_refused_rate',0):.1%} |"
        )

    lines += [
        "",
        "## 2. 지연(latency)",
        "",
        f"- 케이스당 총 지연: 평균 {sum(case_total_ms)/len(case_total_ms):.0f}ms · "
        f"p50 {_percentile(case_total_ms,0.5):.0f}ms · p95 {_percentile(case_total_ms,0.95):.0f}ms · "
        f"max {max(case_total_ms):.0f}ms (n={len(case_total_ms)})",
        "",
        "| 단계 | 평균 ms | p95 ms |",
        "|---|---:|---:|",
    ]
    for stage, vals in sorted(stage_ms.items(), key=lambda x: -sum(x[1]) / max(len(x[1]), 1)):
        lines.append(f"| {stage} | {sum(vals)/len(vals):.0f} | {_percentile(vals,0.95):.0f} |")

    if substage_ms:
        lines += [
            "",
            "### 2-1. 서브단계 분해 (select_and_build_context / generate_answer 내부)",
            "",
            "| 서브단계 | 평균 ms | p95 ms | 표본 |",
            "|---|---:|---:|---:|",
        ]
        for sub, vals in sorted(substage_ms.items(), key=lambda x: -sum(x[1]) / max(len(x[1]), 1)):
            lines.append(
                f"| {sub} | {sum(vals)/len(vals):.0f} | {_percentile(vals,0.95):.0f} | {len(vals)} |"
            )

    if retrieval_call_ms:
        lines += [
            "",
            "### 2-2. retrieval 호출별 (main vs fallback 재시도)",
            "",
            "| label | 호출 횟수 | 평균 ms | p95 ms |",
            "|---|---:|---:|---:|",
        ]
        for label, vals in sorted(retrieval_call_ms.items(), key=lambda x: -sum(x[1])):
            lines.append(
                f"| {label} | {len(vals)} | {sum(vals)/len(vals):.0f} | {_percentile(vals,0.95):.0f} |"
            )
        lines += [
            "",
            "> main 외 fallback_* 호출이 잦으면 재시도가 지연의 숨은 원인이다.",
        ]

    s0 = run_summaries[0]
    lines += [
        "",
        "## 3. 카테고리별 검색 성능 (Top5 / Context, 결정적)",
        "",
        "| 카테고리 | 총수 | Top5 | Context |",
        "|---|---:|---:|---:|",
    ]
    for cat, st in sorted(s0.get("by_category", {}).items()):
        t = st["total"]
        lines.append(f"| {cat} | {t} | {st['top5_hit']}/{t} ({st['top5_hit']/t:.0%}) | {st['context_hit']}/{t} ({st['context_hit']/t:.0%}) |")

    lines += [
        "",
        "## 4. 난이도별 Context Hit (결정적)",
        "",
        "| 난이도 | 총수 | Context |",
        "|---|---:|---:|",
    ]
    for diff, st in sorted(s0.get("by_difficulty", {}).items()):
        t = st["total"]
        lines.append(f"| {diff} | {t} | {st['context_hit']}/{t} ({st['context_hit']/t:.0%}) |")

    by_src = defaultdict(lambda: {"n": 0, "ctx": 0, "top5": 0})
    for results in run_results:
        for r in results:
            s = r.get("source_type") or "?"
            by_src[s]["n"] += 1
            by_src[s]["ctx"] += 1 if r.get("context_hit") else 0
            by_src[s]["top5"] += 1 if r.get("top5_hit") else 0
    lines += [
        "",
        "## 5. 소스타입별 (전 실행 누적 평균)",
        "",
        "| source_type | 표본 | Top5 | Context |",
        "|---|---:|---:|---:|",
    ]
    for s, dd in sorted(by_src.items()):
        lines.append(f"| {s} | {dd['n']} | {dd['top5']/dd['n']:.0%} | {dd['ctx']/dd['n']:.0%} |")

    lines += [
        "",
        "## 6. 실패 분류 (실행별 건수)",
        "",
        "| Failure Stage | " + " | ".join(f"Run{i}" for i in range(1, runs + 1)) + " |",
        "|---|" + "---:|" * runs,
    ]
    all_stages = sorted({st for s in run_summaries for st in s.get("failure_stage_counts", {})})
    for stage in all_stages:
        row = " | ".join(str(s.get("failure_stage_counts", {}).get(stage, 0)) for s in run_summaries)
        lines.append(f"| {stage} | {row} |")

    flaky = []
    consistent_fail = []
    for cid, corrects in per_case_correct.items():
        if len(set(corrects)) > 1:
            flaky.append(cid)
        elif corrects and not corrects[0]:
            consistent_fail.append(cid)
    lines += [
        "",
        "## 7. 케이스 안정성 (Answer Correct 기준)",
        "",
        f"- **항상 정답**: {sum(1 for c in per_case_correct.values() if all(c))}건",
        f"- **flaky(실행마다 정답/오답 진동)**: {len(flaky)}건 → {', '.join(sorted(flaky)) or '없음'}",
        f"- **항상 오답**: {len(consistent_fail)}건 → {', '.join(sorted(consistent_fail)) or '없음'}",
        "",
        "> flaky 케이스는 LLM 생성 비결정성의 직접 증거다. '항상 오답'이 구조적으로 개선이 필요한 실제 약점이다.",
    ]
    if consistent_fail:
        lines += ["", "### '항상 오답' 케이스 상세", "", "| ID | 카테고리 | 난이도 | 질문 |", "|---|---|---|---|"]
        for cid in sorted(consistent_fail):
            m = per_case_meta.get(cid, {})
            lines.append(f"| {cid} | {m.get('category','')} | {m.get('difficulty','')} | {m.get('question','')} |")

    report_path = _DIR / "full_eval_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[full-eval] 리포트 저장: {report_path}")

    raw = {
        "generated_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "runs": runs,
        "run_summaries": run_summaries,
        "per_case_correct": dict(per_case_correct),
        "per_case_refused": dict(per_case_refused),
        "latency": {
            "total_mean_ms": sum(case_total_ms) / len(case_total_ms),
            "total_p95_ms": _percentile(case_total_ms, 0.95),
            "stage_mean_ms": {k: sum(v) / len(v) for k, v in stage_ms.items()},
            "substage_mean_ms": {k: sum(v) / len(v) for k, v in substage_ms.items()},
            "retrieval_call_mean_ms": {
                k: {"count": len(v), "mean_ms": sum(v) / len(v)} for k, v in retrieval_call_ms.items()
            },
        },
    }
    (_DIR / "full_eval_runs.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[full-eval] 원자료 저장: {_DIR / 'full_eval_runs.json'}")
    print("\n" + "=" * 60)
    print("=== 전체 성능 평가 요약 (다회 평균) ===")
    print(f"Top-1 {fmt(det['top1_hit_rate'])} | Top-5 {fmt(det['top5_hit_rate'])} | Context {fmt(det['context_hit_rate'])}")
    print(f"Grounded {fmt(ans['answer_grounded_rate'])} | Correct {fmt(ans['answer_correct_rate'])} | Refused {fmt(ans['answer_refused_rate'])}")
    print(f"flaky={len(flaky)} consistent_fail={len(consistent_fail)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
