# -*- coding: utf-8 -*-
"""C1~C4 콘솔/state 캡처용 PNG 렌더러 (Apple 다크 타일 톤).
실제 state.to_log_dict() 캡처값(2026-06-02) 사용. 일회용 컨테이너에서 실행.
컬럼 좌표 정렬이라 monospace 불필요 → NanumGothic(한글 sans) 사용.
출력: 최종/captures/*.png
"""
import os
from PIL import Image, ImageDraw, ImageFont

BG = (39, 39, 41, 255)        # #272729
BORDER = (58, 58, 60, 255)    # #3a3a3c
WHITE = (245, 245, 247, 255)
MUTE = (165, 165, 170, 255)
SKY = (41, 151, 255, 255)     # #2997ff
DOT = (90, 90, 94, 255)

PAD = 56
TITLE_H = 82
SIZE = 30
LH = 48


def find_font(*names):
    for root, _, files in os.walk("/usr/share/fonts"):
        for n in names:
            if n in files:
                return os.path.join(root, n)
    for root, _, files in os.walk("/usr/share/fonts"):
        for f in files:
            if "NanumGothic" in f and f.endswith(".ttf"):
                return os.path.join(root, f)
    raise RuntimeError("Nanum font not found")


REG = ImageFont.truetype(find_font("NanumGothic.ttf"), SIZE)
BOLD = ImageFont.truetype(find_font("NanumGothicBold.ttf", "NanumGothic.ttf"), SIZE)
TITLEF = ImageFont.truetype(find_font("NanumGothic.ttf"), 26)

# line types
def KV(label, value, color=SKY, bar=None):
    return ("kv", label, value, color, bar)

def FULL(segs):  # segs: list of (text,color)
    return ("full", segs)

def RULE():
    return ("rule",)

def GAP():
    return ("gap",)


def render(name, title, lines, bar_max=None):
    kv_labels = [ln[1] for ln in lines if ln[0] == "kv"]
    label_w = max((REG.getlength(x) for x in kv_labels), default=0)
    valcol = PAD + label_w + 30
    bar_area = 340 if bar_max else 0

    # width
    widths = [TITLEF.getlength(title) + 150]
    for ln in lines:
        if ln[0] == "kv":
            f = BOLD if ln[3] == SKY else REG
            widths.append(valcol + f.getlength(ln[2]) - PAD + (bar_area if ln[4] is not None else 0))
        elif ln[0] == "full":
            widths.append(sum(REG.getlength(t) for t, _ in ln[1]))
    W = int(PAD * 2 + max(widths))
    H = int(TITLE_H + PAD * 0.7 + len(lines) * LH + PAD * 0.7)

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=26, fill=BG, outline=BORDER, width=2)
    for x in (PAD, PAD + 34, PAD + 68):
        d.ellipse([x, 32, x + 18, 50], fill=DOT)
    d.text((PAD + 110, 28), title, font=TITLEF, fill=MUTE)
    d.line([PAD, TITLE_H, W - PAD, TITLE_H], fill=BORDER, width=2)

    y = int(TITLE_H + PAD * 0.6)
    for ln in lines:
        kind = ln[0]
        if kind == "gap":
            y += LH
            continue
        if kind == "rule":
            d.line([PAD, y + LH // 2, W - PAD, y + LH // 2], fill=BORDER, width=2)
            y += LH
            continue
        if kind == "kv":
            _, label, value, color, bar = ln
            d.text((PAD, y), label, font=REG, fill=MUTE)
            f = BOLD if color == SKY else REG
            d.text((valcol, y), value, font=f, fill=color)
            if bar is not None and bar_max:
                bx = int(W - PAD - bar_area + 30)
                bw = int((bar / bar_max) * (bar_area - 80))
                d.rounded_rectangle([bx, y + 10, bx + max(4, bw), y + LH - 20],
                                    radius=6, fill=SKY)
            y += LH
        elif kind == "full":
            x = PAD
            for text, color in ln[1]:
                f = BOLD if color == SKY else REG
                d.text((x, y), text, font=f, fill=color)
                x += f.getlength(text)
            y += LH
    img.save(name)
    print("SAVED", os.path.basename(name), img.size)


OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
os.makedirs(OUT, exist_ok=True)

# ---------- C1: scenario 1 — preprocess & retrieval ----------
render(os.path.join(OUT, "C1_scenario1_preprocess.png"),
       'state.to_log_dict()  —  "1학기 중간고사 기간 알려줘"', [
    KV("primary_intent", "INFO"),
    KV("query_family", "academic_schedule"),
    FULL([("keywords  : 중간고사 · 1학기 · 기간 · 1학기중간고사기간 …(10개)", WHITE)]),
    FULL([("entities  : time → [1학기, 기간]", WHITE)]),
    KV("rewritten_queries", "4"),
    FULL([("temporal_signals : {semesters:[1학기], has_explicit:true}", WHITE)]),
    KV("query_vector_size", "1024"),
    FULL([("effective_strategy : ", MUTE), ("vector", SKY),
          ("   (fallback_used: false)", MUTE)]),
    FULL([("retrieval_quality : {ok:true, top1:1.15, context_chars:13194}", WHITE)]),
    KV("canonical_filter", "10 -> 4 candidates"),
    KV("temporal_validation", "matched [true]"),
])

# ---------- C2: scenario 1 — rerank & generation ----------
render(os.path.join(OUT, "C2_scenario1_rerank_generate.png"),
       "rerank  ->  select  ->  generate", [
    KV("reranked -> selected", "20 -> 3 docs"),
    FULL([("[1] 학사일정 | 학사정보 | 대학생활    rerank_score: ", WHITE), ("8.99", SKY)]),
    FULL([("      signals : canonical 3.0 + family_boost 2.48", MUTE)]),
    FULL([("                + verified_title 1.5 + heading 0.8", MUTE)]),
    FULL([("      attachment chunk -> family_penalty -2.8 (밀림)", MUTE)]),
    FULL([("answer_input  : context 3,989 · prompt 4,551 chars", WHITE)]),
    FULL([("negative_repair : null  (거절 없음)", WHITE)]),
    GAP(),
    FULL([("answer >> ", MUTE),
          ("“1학기 중간고사 기간은 4월 21일부터 27일까지입니다.”", SKY)]),
])

# ---------- C3: scenario 1 — timings (mini bars) ----------
render(os.path.join(OUT, "C3_scenario1_timings.png"),
       "timings (ms)  —  cold start (첫 모델 로드 포함)", [
    KV("classify_primary_intent", "0", WHITE, bar=0),
    KV("preprocess", "5569", WHITE, bar=5569),
    KV("embed_query", "458", WHITE, bar=458),
    KV("retrieve", "13057", WHITE, bar=13057),
    KV("select_and_build_context", "11", WHITE, bar=11),
    KV("generate_answer", "2961", WHITE, bar=2961),
    KV("postprocess", "0", WHITE, bar=0),
    RULE(),
    KV("total_run_ms", "22056", SKY, bar=22056),
], bar_max=22056)

# ---------- C4: scenario 2 — non-info (GENERAL) ----------
render(os.path.join(OUT, "C4_scenario2_general.png"),
       'state.to_log_dict()  —  "안녕"', [
    KV("primary_intent", "GENERAL"),
    FULL([("timings : [classify_primary_intent]   <- only stage", WHITE)]),
    KV("retrieved_doc_count", "0"),
    KV("reranked_doc_count", "0", WHITE),
    KV("selected_doc_count", "0"),
    KV("fallback_used", "false", WHITE),
    GAP(),
    FULL([("answer >> 안녕하세요. 동의대학교 정보 안내를 도와드리고 있어요.", WHITE)]),
    FULL([("            학사, 장학, 기숙사, 통학버스 같은 학교 정보를 물어봐 주세요.", MUTE)]),
])

print("DONE ->", OUT)
