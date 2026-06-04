"""발표 시연용 RAG 파이프라인 데이터 흐름 뷰어.

질문을 ChatPipeline 으로 1회 실행한 뒤, ``pipeline.last_state`` 의
단계별 trace(intent → 전처리/재작성 → 검색 → 재정렬 → 선택 → 생성)를
사람이 읽기 좋은 형태로 한 단계씩 출력한다.

파이프라인 로직은 건드리지 않는 read-only 뷰어다.
모든 데이터는 ``state.to_log_dict()`` / ``state.metadata`` 에서만 읽는다.

실행(컨테이너 내부 권장):
    docker compose run --rm rag python -m rag.scripts.demo_pipeline_flow \
        --question "컴퓨터공학과 2학년 이수표 교육과정" --step

옵션:
    --question  실행할 질문(반복 가능). 미지정 시 시연 기본 3종.
    --step      단계마다 Enter 대기(라이브 내레이션용).
    --save PATH to_log_dict() 전체 JSON 저장(사전 캡처 백업용).
    --full      후보 trace 를 상위 N 대신 전체 출력.
    --top-n N   각 trace 에서 보여줄 후보 수(기본 5).
    --no-color  ANSI 색상 비활성화.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query


DEMO_QUESTIONS = [
    "컴퓨터공학과 2학년 이수표 교육과정",  # 정상 경로 + 학과 커리큘럼 보정
    "정보공학관 학생식당 운영시간",  # facility 보정
    "수강신청 기간 알려줘",  # canonical notice + 학사일정
]


# ── 출력 유틸 ────────────────────────────────────────────────────────────────
class C:
    """ANSI 색상 코드(런타임에 --no-color 로 비활성화 가능)."""

    enabled = True
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"

    @classmethod
    def wrap(cls, code: str, text: str) -> str:
        if not cls.enabled:
            return text
        return f"{code}{text}{cls.RESET}"


def c(code: str, text: str) -> str:
    return C.wrap(code, text)


def _truncate(text: Any, width: int) -> str:
    s = str(text if text is not None else "")
    s = s.replace("\n", " ").strip()
    if len(s) <= width:
        return s
    return s[: width - 1] + "…"


def _fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "  -  "


def _stage_header(num: str, title: str) -> None:
    line = "═" * 64
    print()
    print(c(C.CYAN, line))
    print(c(C.CYAN + C.BOLD, f"  {num}  {title}"))
    print(c(C.CYAN, line))


def _field(label: str, value: Any) -> None:
    print(f"  {c(C.DIM, label + ':'):<28} {value}")


def _json_default(obj: Any) -> Any:
    """metadata 안에 섞인 Pydantic 모델 등 비직렬화 객체를 안전하게 변환."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return str(obj)


def _maybe_pause(step: bool) -> None:
    if not step:
        return
    try:
        input(c(C.DIM, "    ↵ 계속하려면 Enter…"))
    except (EOFError, KeyboardInterrupt):
        print()


# ── 단계별 렌더링 ────────────────────────────────────────────────────────────
def render_intent(log: dict, step: bool) -> None:
    _stage_header("①", "INTENT  의도 분류")
    intent = log.get("primary_intent", "?")
    color = C.GREEN if intent == "INFO" else C.YELLOW
    _field("primary_intent", c(color + C.BOLD, intent))
    if intent != "INFO":
        print(c(C.YELLOW, "    → 비-INFO: LLM 검색 없이 직접 응답 경로"))
    _maybe_pause(step)


def render_query_understanding(log: dict, step: bool) -> None:
    _stage_header("②", "QUERY UNDERSTANDING  전처리 · 재작성")
    meta = log.get("metadata", {})
    qu = meta.get("query_understanding", {}) if isinstance(meta, dict) else {}

    _field("original_query", c(C.BOLD, log.get("original_query", "")))
    _field("normalized_query", log.get("normalized_query", ""))
    _field("keywords", ", ".join(log.get("keywords", []) or []) or "-")

    entities = log.get("entities") or qu.get("entities") or {}
    _field("entities", json.dumps(entities, ensure_ascii=False) if entities else "-")
    _field("detected_domain", qu.get("detected_domain", "-"))
    _field("detected_category", qu.get("detected_category", log.get("category")))

    # 재작성 변형(single rewrite 기본, multi-query 활성화 시 우선)
    multi = meta.get("multi_query") if isinstance(meta, dict) else None
    single = meta.get("single_query_rewrite") if isinstance(meta, dict) else None
    if isinstance(multi, dict) and multi.get("generated"):
        print(c(C.MAGENTA, "  multi-query 변형:"))
        for v in multi.get("generated", []):
            print(f"      • {v}")
    elif isinstance(single, dict) and single.get("generated"):
        applied = single.get("applied")
        tag = c(C.GREEN, "적용됨") if applied else c(C.DIM, "미적용")
        print(f"  {c(C.MAGENTA, 'query rewrite')} ({tag}):")
        for v in single.get("generated", []):
            print(f"      • {v}")
    else:
        rewritten = log.get("rewritten_query")
        if rewritten:
            _field("rewritten_query", rewritten)
    _maybe_pause(step)


def _render_candidate_table(trace: list, top_n: int | None) -> None:
    rows = trace if top_n is None else trace[:top_n]
    if not rows:
        print(c(C.DIM, "    (후보 없음)"))
        return
    header = f"    {'#':>2}  {'score':>6}  {'lex':>5}  {'vec':>5}  {'source_type':<18}  title"
    print(c(C.DIM, header))
    for item in rows:
        rank = item.get("rank", "?")
        line = (
            f"    {rank:>2}  {_fmt_score(item.get('score')):>6}  "
            f"{_fmt_score(item.get('lexical_score')):>5}  "
            f"{_fmt_score(item.get('vector_score')):>5}  "
            f"{_truncate(item.get('source_type'), 18):<18}  "
            f"{_truncate(item.get('title'), 38)}"
        )
        print(line)


def render_retrieval(log: dict, top_n: int | None, step: bool) -> None:
    _stage_header("③", "RETRIEVAL  검색")
    meta = log.get("metadata", {})
    _field("retrieval_strategy", c(C.BOLD, log.get("retrieval_strategy", "?")))
    _field("retrieved_doc_count", log.get("retrieved_doc_count", 0))
    _field("top_k", log.get("retrieval_top_k", "-"))
    trace = meta.get("retrieved_candidate_trace", []) if isinstance(meta, dict) else []
    print(c(C.BLUE, "  검색된 후보(상위):"))
    _render_candidate_table(trace, top_n)
    _maybe_pause(step)


def render_rerank(log: dict, top_n: int | None, step: bool) -> None:
    _stage_header("④", "RERANK  재정렬 — 순위가 어떻게 바뀌었나")
    meta = log.get("metadata", {})
    comparison = meta.get("rerank_comparison", []) if isinstance(meta, dict) else []
    rows = comparison if top_n is None else comparison[:top_n]
    if not rows:
        print(c(C.DIM, "    (재정렬 비교 데이터 없음)"))
        _maybe_pause(step)
        return
    header = f"    {'before':>6} → {'after':>5}  {'Δ':>4}  {'rerank':>6}  sel  title"
    print(c(C.DIM, header))
    for row in rows:
        before = row.get("rank_before")
        after = row.get("rank_after")
        delta = row.get("rank_delta")
        if delta is None:
            arrow = c(C.MAGENTA, " new")
            delta_s = "  +"
        elif delta > 0:
            arrow = c(C.GREEN, f"▲{delta}")
            delta_s = arrow
        elif delta < 0:
            arrow = c(C.RED, f"▼{abs(delta)}")
            delta_s = arrow
        else:
            arrow = c(C.DIM, " =")
            delta_s = arrow
        sel = c(C.GREEN + C.BOLD, "✓") if row.get("selected") else " "
        before_s = "-" if before is None else str(before)
        print(
            f"    {before_s:>6} → {str(after):>5}  {delta_s:>4}  "
            f"{_fmt_score(row.get('rerank_score')):>6}   {sel}   "
            f"{_truncate(row.get('title'), 40)}"
        )
    _maybe_pause(step)


_CORRECTION_FLAGS = [
    ("faculty_selection_correction", "교수(faculty) 선택 보정"),
    ("facility_selection_correction_applied", "시설(facility) 선택 보정"),
    ("department_curriculum_selection", "학과 이수표(curriculum) 필터"),
    ("canonical_notice_selection", "대표 공지(canonical notice) 필터"),
    ("department_faculty_list_correction_applied", "학과 교수명단 보정"),
]


def render_selection(log: dict, step: bool) -> None:
    _stage_header("⑤", "SELECTION  최종 선택 · 도메인 보정")
    meta = log.get("metadata", {})
    _field("selected_doc_count", c(C.BOLD, str(log.get("selected_doc_count", 0))))

    # 도메인 보정 발동 여부
    applied = []
    if isinstance(meta, dict):
        for key, label in _CORRECTION_FLAGS:
            val = meta.get(key)
            if val:  # truthy(True 또는 비어있지 않은 dict)
                applied.append(label)
    if applied:
        print(c(C.YELLOW, "  적용된 도메인 보정:"))
        for label in applied:
            print(f"      {c(C.YELLOW, '◆')} {label}")
    else:
        print(c(C.DIM, "  적용된 도메인 보정 없음"))

    trace = meta.get("selected_candidate_trace", []) if isinstance(meta, dict) else []
    print(c(C.GREEN, "  최종 선택된 청크:"))
    _render_candidate_table(trace, None)
    _maybe_pause(step)


def render_generation(log: dict, step: bool) -> None:
    _stage_header("⑥", "GENERATION  답변 생성 · 출처")
    meta = log.get("metadata", {})
    answer = log.get("answer_text", "") or ""
    success = log.get("success")
    status = c(C.GREEN, "success") if success else c(C.RED, "failed")
    _field("status", status)

    print(c(C.BOLD, "  답변:"))
    for line in answer.splitlines() or [""]:
        print(f"    {line}")

    citations = meta.get("citation_trace", []) if isinstance(meta, dict) else []
    if citations:
        print(c(C.BLUE, "  출처:"))
        for cit in citations:
            print(
                f"      [{cit.get('rank')}] {_truncate(cit.get('title'), 44)}  "
                f"{c(C.DIM, _truncate(cit.get('source_url'), 50))}"
            )
    _maybe_pause(step)


def render_diagnostics(log: dict, total_ms: int, step: bool) -> None:
    _stage_header("⑦", "DIAGNOSTICS  진단 · latency")
    meta = log.get("metadata", {})
    fallback = log.get("fallback_used")
    _field(
        "fallback_used",
        c(C.YELLOW + C.BOLD, "True") if fallback else c(C.DIM, "False"),
    )
    quality = meta.get("retrieval_quality") if isinstance(meta, dict) else None
    if isinstance(quality, dict):
        ok = quality.get("ok")
        ok_s = c(C.GREEN, "ok") if ok else c(C.RED, f"not ok ({quality.get('reason')})")
        _field("retrieval_quality", ok_s)
        _field(
            "top1 / avg_topk",
            f"{_fmt_score(quality.get('top1_score'))} / {_fmt_score(quality.get('avg_topk_score'))}",
        )

    timings = meta.get("timings_ms") if isinstance(meta, dict) else None
    if isinstance(timings, list) and timings:
        print(c(C.BLUE, "  단계별 소요시간(ms):"))
        for t in timings:
            stage = t.get("stage", "?")
            ms = t.get("elapsed_ms", "?")
            bar = "█" * min(40, int(ms) // 50) if isinstance(ms, (int, float)) else ""
            print(f"      {stage:<22} {str(ms):>6}  {c(C.DIM, bar)}")
    _field("total_run_ms", c(C.BOLD, str(total_ms)))
    _maybe_pause(step)


def render_all(log: dict, total_ms: int, top_n: int | None, step: bool) -> None:
    print()
    print(c(C.MAGENTA + C.BOLD, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓"))
    print(c(C.MAGENTA + C.BOLD, f"┃  Q. {_truncate(log.get('original_query'), 58):<58} ┃"))
    print(c(C.MAGENTA + C.BOLD, "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"))

    render_intent(log, step)
    if log.get("primary_intent") != "INFO":
        # 비-INFO 는 검색/생성 단계가 의미 없으므로 답변만 보여주고 종료
        render_generation(log, step)
        return
    render_query_understanding(log, step)
    render_retrieval(log, top_n, step)
    render_rerank(log, top_n, step)
    render_selection(log, step)
    render_generation(log, step)
    render_diagnostics(log, total_ms, step)


# ── 실행 ────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="발표 시연용 RAG 파이프라인 데이터 흐름 뷰어",
    )
    parser.add_argument("--question", action="append", default=[], help="실행할 질문(반복 가능)")
    parser.add_argument("--step", action="store_true", help="단계마다 Enter 대기")
    parser.add_argument("--save", default="", help="to_log_dict() 전체 JSON 저장 경로")
    parser.add_argument("--full", action="store_true", help="후보 trace 전체 출력")
    parser.add_argument("--top-n", type=int, default=5, help="trace 후보 표시 개수(기본 5)")
    parser.add_argument("--no-color", action="store_true", help="ANSI 색상 비활성화")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.no_color or not sys.stdout.isatty():
        # 파일 리다이렉트 시에도 깔끔하도록 색상 자동 비활성화
        C.enabled = False
    if os.environ.get("NO_COLOR"):
        C.enabled = False

    questions = args.question or DEMO_QUESTIONS
    top_n = None if args.full else args.top_n

    print(c(C.DIM, "ChatPipeline 초기화 중(KoE5 로딩 등, 수 초 소요)…"))
    pipeline = ChatPipeline()
    init_started = time.perf_counter()
    pipeline.initialize()
    init_ms = int(round((time.perf_counter() - init_started) * 1000))
    print(c(C.DIM, f"초기화 완료 ({init_ms} ms)"))

    saved: list[dict] = []
    for question in questions:
        run_started = time.perf_counter()
        try:
            pipeline.run(Query(text=question))
        except Exception as exc:  # noqa: BLE001 — 시연 중 한 질문 실패가 전체를 막지 않도록
            print(c(C.RED, f"\n[!] '{question}' 실행 실패: {type(exc).__name__}: {exc}"))
            continue
        total_ms = int(round((time.perf_counter() - run_started) * 1000))
        state = pipeline.last_state
        if state is None:
            print(c(C.RED, f"\n[!] '{question}' last_state 없음"))
            continue
        log = state.to_log_dict()
        render_all(log, total_ms, top_n, args.step)
        saved.append({"total_run_ms": total_ms, "log": log})

    if args.save and saved:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(saved, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        print(c(C.GREEN, f"\n백업 저장됨: {out} ({len(saved)}건)"))


if __name__ == "__main__":
    main()
