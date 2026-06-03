# -*- coding: utf-8 -*-
"""
dong-gu 최종 발표 deck 빌더 (Apple-style design system, 16:9).
python-pptx로 18+1장 슬라이드 생성. 일회용 docker 컨테이너에서 실행.
출력: 최종/dong-gu_final.pptx
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

# ---------- tokens ----------
BLUE = "0066CC"; SKY = "2997FF"; WHITE = "FFFFFF"; PARCH = "F5F5F7"
DARK = "272729"; DARK2 = "2A2A2C"; INK = "1D1D1F"; INK80 = "333333"
INK48 = "7A7A7A"; HAIR = "E0E0E0"; MUTE_D = "CCCCCC"; HAIR_D = "3A3A3C"

F_DISP = "Aptos Display"; F_SEMI = "Aptos SemiBold"; F_REG = "Aptos"
F_LIGHT = "Aptos Light"; F_MONO = "Consolas"

EMU_IN = 914400
prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def rgb(h):
    return RGBColor.from_string(h)


def slide(bg=WHITE):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = rgb(bg)
    return s


def add_text(s, x, y, w, h, text, size, color, font=F_REG, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, line_spacing=1.2, tracking=None, pad=0.0):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, Inches(pad))
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if line_spacing:
            p.line_spacing = line_spacing
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.name = font
        r.font.color.rgb = rgb(color)
        if tracking is not None:
            r._r.get_or_add_rPr().set("spc", str(int(tracking * 100)))
    return tb


def add_rich(s, x, y, w, h, lines, size, font, default_color,
             line_spacing=1.25, anchor=MSO_ANCHOR.TOP, pad=0.0):
    """lines: list; each item is str OR list of (text,color) tuples."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
        setattr(tf, m, Inches(pad))
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = line_spacing
        runs = line if isinstance(line, list) else [(line, default_color)]
        for text, color in runs:
            r = p.add_run()
            r.text = text
            r.font.size = Pt(size)
            r.font.name = font
            r.font.color.rgb = rgb(color or default_color)
    return tb


def rrect(s, x, y, w, h, fill=None, line=None, line_w=1.0, radius=0.18):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                             Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    try:
        shp.adjustments[0] = min(0.5, radius / max(0.01, min(w, h)))
    except Exception:
        pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid(); shp.fill.fore_color.rgb = rgb(fill)
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = rgb(line); shp.line.width = Pt(line_w)
    shp.text_frame.paragraphs[0].text = ""
    return shp


def bar(s, x, y, w, h, fill):
    shp = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                             Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    shp.fill.solid(); shp.fill.fore_color.rgb = rgb(fill)
    shp.line.fill.background()
    return shp


def hairline(s, x, y, w, color=HAIR, pt=1.0):
    bar(s, x, y, w, pt / 72.0, color)


def pill(s, x, y, w, h, fill, text=None, tsize=11, tcolor=WHITE, font=F_SEMI):
    shp = rrect(s, x, y, w, h, fill=fill, line=None, radius=h / 2.0)
    if text:
        tf = shp.text_frame
        tf.word_wrap = False
        for m in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            setattr(tf, m, Inches(0.04))
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = text
        r.font.size = Pt(tsize); r.font.name = font; r.font.color.rgb = rgb(tcolor)
    return shp


def set_arrow(shape):
    spPr = shape._element.spPr
    ln = spPr.find(qn("a:ln"))
    if ln is None:
        ln = spPr.makeelement(qn("a:ln"), {}); spPr.append(ln)
    for t in ln.findall(qn("a:tailEnd")):
        ln.remove(t)
    ln.append(ln.makeelement(qn("a:tailEnd"),
              {"type": "triangle", "w": "med", "len": "med"}))


def arrow(s, x1, y1, x2, y2, color=BLUE, w=1.5):
    cn = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                                Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    cn.shadow.inherit = False
    cn.line.width = Pt(w); cn.line.color.rgb = rgb(color)
    set_arrow(cn)
    return cn


def grid(n, gutter, x0=0.85, total=11.63):
    w = (total - (n - 1) * gutter) / n
    return w, [x0 + i * (w + gutter) for i in range(n)]


def header(s, kicker, title, subtitle, dark=False, divider=True):
    accent = SKY if dark else BLUE
    ink = WHITE if dark else INK
    sub = MUTE_D if dark else INK48
    add_text(s, 0.85, 0.55, 11.63, 0.30, kicker, 12, accent, F_SEMI)
    add_text(s, 0.85, 0.95, 11.63, 0.85, title, 32, ink, F_SEMI,
             tracking=-0.4, line_spacing=1.0)
    add_text(s, 0.85, 1.88, 11.63, 0.50, subtitle, 18, sub, F_REG)
    if divider:
        hairline(s, 0.85, 2.50, 11.63, HAIR_D if dark else HAIR, 1.0)


_PG = {"n": 0}


def footer(s, page, section, dark=False):
    # page 인자는 호환용으로 무시하고 슬라이드 순서대로 자동 번호 매김
    _PG["n"] += 1
    page = _PG["n"]
    c = MUTE_D if dark else INK48
    add_text(s, 0.85, 7.02, 6.0, 0.28, section, 10, c, F_REG)
    add_text(s, 6.48, 7.02, 6.0, 0.28, f"{page:02d}", 10, c, F_REG,
             align=PP_ALIGN.RIGHT)


def codetile(s, x, y, w, h, lines):
    rrect(s, x, y, w, h, fill=DARK, line=HAIR_D, line_w=1.0, radius=0.12)
    add_rich(s, x + 0.28, y + 0.22, w - 0.56, h - 0.44, lines, 11.5, F_MONO,
             WHITE, line_spacing=1.32)


def card(s, x, y, w, h, title, body, *, dark=False, fill=None, number=None,
         accent=BLUE, tsize=16, bsize=13, radius=0.18):
    if fill is None:
        fill = DARK2 if dark else WHITE
    line = None if dark else HAIR
    rrect(s, x, y, w, h, fill=fill, line=line, line_w=1.0, radius=radius)
    cy = y + 0.24
    if number is not None:
        add_text(s, x + 0.24, cy, w - 0.48, 0.7, number, 40, accent, F_SEMI,
                 tracking=-0.5, line_spacing=1.0)
        cy += 0.72
    tcolor = WHITE if dark else INK
    add_text(s, x + 0.24, cy, w - 0.48, 0.4, title, tsize, tcolor, F_SEMI,
             tracking=-0.3, line_spacing=1.0)
    cy += 0.40
    bcolor = MUTE_D if dark else INK80
    add_text(s, x + 0.24, cy, w - 0.48, h - (cy - y) - 0.2, body, bsize, bcolor,
             F_REG, line_spacing=1.25)


# ===================================================================
# 0. COVER
# ===================================================================
s = slide(WHITE)
add_text(s, 0.85, 0.55, 11.63, 0.30, "CAPSTONE · FINAL PRESENTATION", 12, BLUE, F_SEMI)
add_text(s, 0.85, 2.55, 11.63, 1.2, "dong-gu", 54, INK, F_SEMI, tracking=-0.5, line_spacing=1.0)
add_text(s, 0.85, 3.75, 11.63, 0.7, "동의대학교 학생 질의응답 RAG 챗봇", 24, INK80, F_LIGHT)
add_text(s, 0.85, 4.55, 11.0, 0.6,
         "흩어진 학교 정보를 카카오톡 한 곳에서, 공식 문서에 근거해 답하다.", 18, INK48, F_REG)
hairline(s, 0.85, 6.55, 11.63, HAIR, 1.0)
add_text(s, 0.85, 6.68, 8.0, 0.3, "OO조  ·  RAG · Crawler · Backend", 11, INK48, F_REG)
add_text(s, 6.48, 6.68, 6.0, 0.3, "2026", 11, INK48, F_REG, align=PP_ALIGN.RIGHT)

# ===================================================================
# 1. 초기 목표
# ===================================================================
s = slide(WHITE)
header(s, "01 · 초기 목표", "왜 만들었나", "학교 정보는 많지만, 흩어져 있어 찾기 어렵다.")
rrect(s, 0.85, 2.65, 11.63, 1.25, fill=PARCH, line=HAIR, radius=0.14)
add_rich(s, 1.15, 2.85, 11.0, 0.95, [
    [("“수강신청이 언제더라? 공지가 어디 올라왔지…”", INK80)],
    [("“중간고사 기간을 찾으려 게시판·학사공지·홈페이지를 다 뒤졌는데 내용이 다 달랐어.”", INK80)],
], 15, F_REG, INK80, line_spacing=1.4)
w, xs = grid(3, 0.30)
goals = [
    ("01", "자동 수집 크롤러", "학교 공식 문서를 주기적으로 수집·적재한다."),
    ("02", "하이브리드 RAG", "의미 기반 검색 + 키워드 검색을 결합한다."),
    ("03", "카카오톡 챗봇", "학생이 늘 쓰는 채널에서 언제든 질문한다."),
]
for (num, t, b), x in zip(goals, xs):
    card(s, x, 4.15, w, 2.4, t, b, number=num)
hairline(s, 0.85, 6.7, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.78, 11.63, 0.3, "세 가지 목표가 오늘 발표의 큰 줄기입니다.", 12, INK80, F_REG)
footer(s, 1, "초기 목표")

# ===================================================================
# 2. 중간발표 요약
# ===================================================================
s = slide(PARCH)
header(s, "02 · 중간발표 요약", "중간발표까지의 진행", "기초 골격은 세웠다 — 남은 건 품질·규칙·평가.")
card(s, 0.85, 2.65, 5.615, 3.9, "완료한 것",
     "• 크롤러: 게시판·정적 페이지 수집\n• 첨부(PDF·HWP·이미지) 텍스트 변환\n• BM25 어휘 검색 기초 파이프라인\n• 카카오 연동 FastAPI 서버 골격",
     fill=WHITE, bsize=14)
card(s, 6.865, 2.65, 5.615, 3.9, "남은 과제",
     "• 검색 품질 개선\n• 도메인 규칙 게이트 적용\n• 정량 평가 프레임워크 구축",
     fill=WHITE, accent=BLUE, bsize=14)
add_text(s, 7.105, 5.0, 5.1, 1.3,
         "→ 최종 결과는 이 세 과제를 어떻게 풀었는지에 대한 이야기입니다.",
         13, BLUE, F_SEMI, line_spacing=1.3)
footer(s, 2, "중간발표 요약")

# ===================================================================
# 3. 시스템 개요 (D1)
# ===================================================================
s = slide(PARCH)
header(s, "03 · 최종 결과 · 3.1", "시스템 개요", "세 개의 독립 Docker 컨테이너로 구성된 수집→응답 파이프라인.")
pill(s, 0.85, 2.68, 4.7, 0.34, BLUE, "3 Docker containers · independently deployable", 11)
nodes = [("Crawler", "collect & ingest", 0.85, False),
         ("RAG Pipeline", "port 8001", 3.89, True),
         ("Backend", "port 8000", 6.93, False),
         ("KakaoTalk user", "external", 9.97, False)]
for name, cap, x, core in nodes:
    rrect(s, x, 3.20, 2.50, 1.30, fill=(WHITE if core or name != "KakaoTalk user" else PARCH),
          line=HAIR, radius=0.16)
    if core:
        bar(s, x, 3.20, 2.50, 0.06, BLUE)
    add_text(s, x + 0.2, 3.6, 2.1, 0.4, name, 16, INK, F_SEMI, align=PP_ALIGN.CENTER)
    add_text(s, x + 0.2, 4.0, 2.1, 0.3, cap, 11, INK48, F_REG, align=PP_ALIGN.CENTER)
for x1, x2 in [(3.35, 3.89), (6.39, 6.93), (9.43, 9.97)]:
    arrow(s, x1, 3.85, x2, 3.85, BLUE, 1.5)
add_text(s, 9.43, 4.5, 1.2, 0.25, "webhook", 9, INK48, F_REG, align=PP_ALIGN.CENTER)
w, xs = grid(3, 0.30)
desc = [("Crawl", "게시판·정적·첨부 수집 → 청킹 → 1024차원 벡터 적재"),
        ("Retrieve & Generate", "하이브리드 검색 → 다신호 리랭킹 → LLM 답변 생성"),
        ("Serve", "카카오 웹훅 수신 · 사용자 잠금 · 로그 적재")]
for (t, b), x in zip(desc, xs):
    card(s, x, 4.85, w, 1.45, t, b, fill=PARCH, tsize=14, bsize=12)
hairline(s, 0.85, 6.55, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.62, 11.63, 0.3,
         "각 컨테이너는 독립 배포·재시작 — 장애가 번지지 않게 격리됩니다.", 12, INK80, F_REG)
footer(s, 3, "시스템 개요")

# ===================================================================
# 4. 구성 요소 (D2 + D3)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.1", "시스템 구성 요소", "수집의 입구(크롤러)와 응답의 출구(RAG·백엔드).")
# D2 left vertical flow
add_text(s, 0.85, 2.68, 6.55, 0.3, "Crawler data flow", 14, BLUE, F_SEMI)
steps = [("Collect", "board + static pages"), ("Parse / OCR", "PDF · HWP · image"),
         ("Chunk", "search-unit split"), ("Embed (KoE5)", "1024-dim vector"),
         ("Load", "pgvector store")]
yy = 3.05
for i, (t, c) in enumerate(steps):
    rrect(s, 0.85, yy, 6.55, 0.62, fill=WHITE, line=HAIR, radius=0.12)
    pill(s, 1.02, yy + 0.17, 0.28, 0.28, BLUE, str(i + 1), 12, WHITE)
    add_text(s, 1.45, yy + 0.06, 3.0, 0.3, t, 14, INK, F_SEMI)
    add_text(s, 4.3, yy + 0.08, 2.9, 0.3, c, 11, INK48, F_REG, align=PP_ALIGN.RIGHT)
    if i < len(steps) - 1:
        arrow(s, 4.12, yy + 0.62, 4.12, yy + 0.77, BLUE, 1.4)
    yy += 0.77
add_text(s, 0.85, 6.80, 6.55, 0.3, "run/run_crawl_to_rag.py", 11, INK48, F_MONO)
# D3 right two cards
add_text(s, 7.80, 2.68, 4.68, 0.3, "Ask → Answer", 14, BLUE, F_SEMI)
card(s, 7.80, 3.05, 4.68, 1.75, "Backend",
     "카카오 웹훅 수신 · 사용자 잠금\n비속어 필터 · 로그 적재", fill=WHITE, bsize=13)
card(s, 7.80, 5.00, 4.68, 1.75, "RAG Pipeline",
     "검색 · 리랭킹 · 선택\n규칙 게이트 · LLM 생성", fill=WHITE, accent=BLUE, bsize=13)
arrow(s, 10.14, 4.80, 10.14, 5.00, BLUE, 1.4)
add_text(s, 10.3, 4.78, 2.0, 0.24, "internal API", 9, INK48, F_REG)
footer(s, 4, "시스템 구성 요소")

# ===================================================================
# 5. 시스템 설계 (D4 + D5) — DARK
# ===================================================================
s = slide(DARK)
header(s, "03 · 최종 결과 · 3.1", "시스템 설계", "품질 게이트와 폴백 체인으로 끝까지 답을 찾는다.", dark=True)
stages = ["Intent", "Preprocess", "Embed", "Retrieve", "Rerank", "Select", "Generate", "Postprocess"]
cw = 1.28; gap = 0.198
for i, st in enumerate(stages):
    x = 0.85 + i * (cw + gap)
    core = st in ("Retrieve", "Rerank")
    pill(s, x, 3.05, cw, 0.7, SKY if core else DARK2, st, 11,
         (DARK if core else WHITE))
    if i < len(stages) - 1:
        arrow(s, x + cw, 3.40, x + cw + gap, 3.40, SKY, 1.2)
add_text(s, 0.85, 3.85, 11.63, 0.3,
         "각 단계의 점수·소요시간은 state.metadata에 기록됩니다.", 11, MUTE_D, F_REG)
add_text(s, 0.85, 4.55, 8.0, 0.3, "On quality-gate fail  →", 13, SKY, F_SEMI)
fb = [("vector_only_retry", "drop lexical"), ("original_query", "no rewrite"),
      ("relaxed_filters", "loosen src/type"), ("increase_top_k", "widen candidates"),
      ("lexical_only", "BM25 only")]
fw = 2.0; fgap = 0.40
for i, (t, c) in enumerate(fb):
    x = 0.85 + i * (fw + fgap)
    rrect(s, x, 5.00, fw, 0.85, fill=DARK2, line=HAIR_D, radius=0.12)
    add_text(s, x + 0.12, 5.10, fw - 0.24, 0.35, t, 11, WHITE, F_SEMI, line_spacing=1.0)
    add_text(s, x + 0.12, 5.46, fw - 0.24, 0.3, c, 9, MUTE_D, F_REG)
    if i < len(fb) - 1:
        arrow(s, x + fw, 5.42, x + fw + fgap, 5.42, SKY, 1.2)
hairline(s, 0.85, 6.55, 11.63, SKY, 1.0)
add_text(s, 0.85, 6.62, 11.63, 0.3, "순서는 RAG_FALLBACK_ORDER로 설정 가능.", 11, MUTE_D, F_MONO)
footer(s, 5, "시스템 설계", dark=True)

# ===================================================================
# 5b. RAG 파이프라인 상세 (#7 — 상세 파이프라인 그림 보강)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.1", "RAG 파이프라인 상세",
       "질문 하나가 거치는 단계와 분기 — 실제 코드 흐름 기반.")
# main spine
spine = ["Intent", "Preprocess", "Embed", "Retrieve", "Rerank", "Select", "Generate"]
caps = ["INFO 판정", "정규화·키워드·재작성×4", "KoE5 1024-d", "lexical+vector",
        "다신호 점수", "dedup·top-k", "LLM 생성"]
pw = 1.5; pgap = 0.155; pstep = pw + pgap
ys = 2.78
for i, (st, cap) in enumerate(zip(spine, caps)):
    x = 0.85 + i * pstep
    core = st in ("Retrieve", "Rerank")
    rrect(s, x, ys, pw, 0.86, fill=(BLUE if core else WHITE),
          line=(None if core else HAIR), radius=0.12)
    add_text(s, x, ys + 0.14, pw, 0.34, st, 13,
             (WHITE if core else INK), F_SEMI, align=PP_ALIGN.CENTER)
    add_text(s, x + 0.06, ys + 0.5, pw - 0.12, 0.3, cap, 8.5,
             (WHITE if core else INK48), F_REG, align=PP_ALIGN.CENTER, line_spacing=1.0)
    if i < len(spine) - 1:
        arrow(s, x + pw, ys + 0.43, x + pw + pgap, ys + 0.43, BLUE, 1.3)
# branch A: Intent → non-INFO direct answer
ix = 0.85
arrow(s, ix + 0.4, ys + 0.86, ix + 0.4, 4.1, INK48, 1.2)
rrect(s, 0.85, 4.1, 2.55, 0.62, fill=PARCH, line=HAIR, radius=0.12)
add_text(s, 0.95, 4.18, 2.4, 0.5, "non-INFO / 비속어\n→ 검색 생략·직접 응답", 10.5, INK80,
         F_REG, align=PP_ALIGN.CENTER, line_spacing=1.05)
# branch B: Retrieve → lexical / vector → hybrid (SRRF)
rx = 0.85 + 3 * pstep  # Retrieve x
arrow(s, rx + pw / 2, ys + 0.86, rx + pw / 2, 4.18, BLUE, 1.3)
rrect(s, 4.55, 4.18, 1.7, 0.55, fill=WHITE, line=HAIR, radius=0.1)
add_text(s, 4.55, 4.30, 1.7, 0.3, "Lexical · BM25", 11, INK, F_SEMI, align=PP_ALIGN.CENTER)
rrect(s, 4.55, 4.86, 1.7, 0.55, fill=WHITE, line=HAIR, radius=0.1)
add_text(s, 4.55, 4.98, 1.7, 0.3, "Vector · KoE5", 11, INK, F_SEMI, align=PP_ALIGN.CENTER)
rrect(s, 7.05, 4.5, 2.05, 0.62, fill=BLUE, line=None, radius=0.12)
add_text(s, 7.05, 4.6, 2.05, 0.4, "Hybrid Fusion\nSRRF", 12, WHITE, F_SEMI,
         align=PP_ALIGN.CENTER, line_spacing=1.0)
arrow(s, 6.25, 4.45, 7.05, 4.7, BLUE, 1.2)
arrow(s, 6.25, 5.13, 7.05, 4.92, BLUE, 1.2)
add_text(s, 7.05, 5.16, 2.05, 0.24, "→ Rerank", 9, INK48, F_REG, align=PP_ALIGN.CENTER)
# branch C: Select/Generate → rule gate
gx = 0.85 + 6 * pstep
rrect(s, 9.7, 4.18, 2.78, 0.62, fill=PARCH, line=HAIR, radius=0.12)
add_text(s, 9.8, 4.26, 2.6, 0.5, "규칙 게이트 적중\n→ 구조화 답변 (LLM 우회)", 10.5, INK80,
         F_REG, align=PP_ALIGN.CENTER, line_spacing=1.05)
arrow(s, gx + pw / 2, ys + 0.86, gx + pw / 2, 4.18, INK48, 1.2)
hairline(s, 0.85, 5.95, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.05, 11.63, 0.6,
         "단계별 점수·소요시간은 state.metadata에 누적 · 품질 게이트 미달 시 폴백 체인으로 재검색.",
         12, INK80, F_REG, line_spacing=1.2)
footer(s, 0, "파이프라인 상세")

# ===================================================================
# 6. 하이브리드 융합 / 검색 품질 (D6)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.1", "검색 설계 — 융합과 품질", "어휘·벡터를 합치고, 도메인 신호로 노이즈를 거른다.")
add_text(s, 0.85, 2.68, 4.68, 0.3, "Score fusion", 14, BLUE, F_SEMI)
fusion = [("weighted", "lexical .55 + vector .45", False),
          ("rrf", "Reciprocal Rank Fusion", False),
          ("srrf", "Softmax-RRF · 운영 적용", True),
          ("max", "max of two scores", False)]
yy = 3.10
for name, desc, hot in fusion:
    if hot:
        rrect(s, 0.85, yy, 4.68, 0.78, fill=PARCH, line=HAIR, radius=0.1)
    add_text(s, 1.05, yy + 0.12, 1.4, 0.4, name, 14, BLUE if hot else INK, F_SEMI)
    add_text(s, 2.5, yy + 0.16, 2.9, 0.4, desc, 12, INK80, F_REG)
    if not hot:
        hairline(s, 0.85, yy + 0.78, 4.68, HAIR, 0.5)
    yy += 0.85
add_text(s, 5.93, 2.68, 6.55, 0.3, "Retrieval-quality techniques", 14, BLUE, F_SEMI)
tech = [("source_type prefilter", "source_policy.py", "noise 제거"),
        ("exchange filter", "retriever.py", "혼입 방지"),
        ("sub03 URL priority", "retriever.py", "이수표 rank↑"),
        ("attachment exempt", "reranker.py", "커리큘럼 보호"),
        ("dept boost/penalty", "reranker.py", "타 학과 억제"),
        ("career boost", "reranker.py", "취업 페이지 우선")]
yy = 3.10
for t, where, eff in tech:
    add_text(s, 5.93, yy, 3.0, 0.3, t, 12, INK, F_SEMI)
    add_text(s, 8.95, yy + 0.02, 1.9, 0.3, where, 10, INK48, F_MONO)
    add_text(s, 10.9, yy, 1.58, 0.3, eff, 11, INK80, F_REG)
    hairline(s, 5.93, yy + 0.40, 6.55, HAIR, 0.5)
    yy += 0.52
hairline(s, 0.85, 6.6, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.67, 11.63, 0.3, "모든 임계값은 rag/retrieval/quality.py 한 곳에서 관리.", 11, INK48, F_REG)
footer(s, 6, "검색 설계")

# ===================================================================
# 6b. 검색 융합 RRF vs SRRF (대본 9 도식화)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.1", "검색 융합 — RRF vs SRRF",
       "순위만 보는 RRF에서, ‘강한 1등’까지 보는 SRRF로.")
# 좌: 개념 카드 2개
rrect(s, 0.85, 2.72, 5.45, 1.78, fill=WHITE, line=HAIR, radius=0.14)
add_text(s, 1.08, 2.9, 5.0, 0.3, "RRF — 순위 기반 융합", 15, INK, F_SEMI)
add_text(s, 1.08, 3.34, 5.05, 1.1,
         "점수 대신 순위만 사용. BM25 1등 + 벡터 3등이면 두 순위를 점수로 바꿔 합산 — "
         "“두 검색 모두 상위권인가?”를 평가.\n단, 압도적 1등과 간신히 1등을 구분하지 못함.",
         12, INK80, F_REG, line_spacing=1.22)
rrect(s, 0.85, 4.62, 5.45, 1.85, fill=PARCH, line=HAIR, radius=0.14)
bar(s, 0.85, 4.62, 5.45, 0.06, BLUE)
add_text(s, 1.08, 4.8, 5.0, 0.3, "SRRF — Softmax-RRF · 운영 채택", 15, BLUE, F_SEMI)
add_text(s, 1.08, 5.24, 5.05, 1.15,
         "RRF에 Softmax를 더해 점수 분포를 반영. “상위권 중에서도 얼마나 강한 후보인가”까지 "
         "평가 → 두 검색이 모두 강하게 지지하는 문서가 상단으로.",
         12, INK80, F_REG, line_spacing=1.22)
# 우: 그룹 막대 (Top-1 / Context Hit)
add_text(s, 6.6, 2.66, 5.88, 0.3, "융합 방식 비교 — 골드셋 66문항", 13, BLUE, F_SEMI)
bar(s, 6.6, 3.06, 0.22, 0.16, BLUE)
add_text(s, 6.88, 3.0, 1.4, 0.3, "Top-1 Hit", 11, INK80, F_REG)
bar(s, 8.55, 3.06, 0.22, 0.16, SKY)
add_text(s, 8.83, 3.0, 1.7, 0.3, "Context Hit", 11, INK80, F_REG)
base = 6.15
maxh = 2.5
groups = [("가중합", 37.9, 78.8, False), ("RRF", 54.5, 83.3, False), ("SRRF", 56.1, 84.8, True)]
gx0 = 7.0; gstep = 1.85; bw = 0.52
for i, (name, t1, ch, hot) in enumerate(groups):
    gx = gx0 + i * gstep
    if hot:
        rrect(s, gx - 0.2, 3.5, 1.5, base - 3.5 + 0.02, fill="EAF3FF", line=None, radius=0.08)
    h1 = t1 / 100 * maxh; h2 = ch / 100 * maxh
    bar(s, gx, base - h1, bw, h1, BLUE)
    bar(s, gx + 0.58, base - h2, bw, h2, SKY)
    add_text(s, gx - 0.05, base - h1 - 0.28, bw + 0.1, 0.3, f"{t1}", 10.5, BLUE, F_SEMI, align=PP_ALIGN.CENTER)
    add_text(s, gx + 0.53, base - h2 - 0.28, bw + 0.1, 0.3, f"{ch}", 10.5, SKY, F_SEMI, align=PP_ALIGN.CENTER)
    add_text(s, gx - 0.1, base + 0.06, 1.3, 0.3, name, 12, (BLUE if hot else INK), F_SEMI, align=PP_ALIGN.CENTER)
hairline(s, 6.6, base, 5.88, HAIR, 1.0)
hairline(s, 0.85, 6.7, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.77, 11.63, 0.3,
         "SRRF가 Top-1·Context Hit 모두 1위 → 운영 기본값으로 채택.", 12, INK80, F_REG)
footer(s, 0, "검색 융합")

# ===================================================================
# 7. DB 구성 (D7)
# ===================================================================
s = slide(PARCH)
header(s, "03 · 최종 결과 · 3.2", "데이터베이스 구성", "수집 문서 저장군과 RAG 로그군으로 나뉜다.")
docs = [("document", "title · source · url (meta only)", 2.70, 0.85),
        ("document_contents", "raw/clean/table/attachment/image/html", 3.65, 0.85),
        ("chunks", "search-unit text", 4.60, 0.75),
        ("chunk_embeddings", "1024-dim vector (pgvector)", 5.45, 0.85)]
for name, fields, y, h in docs:
    rrect(s, 0.85, y, 5.2, h, fill=WHITE, line=HAIR, radius=0.12)
    bar(s, 1.02, y + h / 2 - 0.06, 0.12, 0.12, BLUE)
    add_text(s, 1.3, y + 0.12, 4.6, 0.3, name, 14, INK, F_SEMI)
    hot = name == "chunk_embeddings"
    add_text(s, 1.3, y + 0.45, 4.7, 0.3, fields, 11, BLUE if hot else INK80, F_REG)
for y in (3.40, 4.35, 5.30):
    arrow(s, 0.70, y, 0.70, y + 0.2, BLUE, 1.2)
add_text(s, 0.35, 3.9, 0.3, 1.5, "1:N", 9, INK48, F_REG)
add_text(s, 7.0, 2.70, 5.48, 0.3, "RAG logs", 12, BLUE, F_SEMI)
logs = [("query_logs", "질문 · 의도 · 카테고리", 3.05),
        ("response_logs", "LLM 응답 · 지연시간(ms)", 4.35),
        ("retrieval_logs", "검색 전략 · 점수 · 사용 청크", 5.65)]
for name, fields, y in logs:
    rrect(s, 7.0, y, 5.48, 1.15, fill=PARCH, line=HAIR, radius=0.12)
    add_text(s, 7.25, y + 0.22, 5.0, 0.3, name, 14, INK, F_SEMI)
    add_text(s, 7.25, y + 0.62, 5.0, 0.3, fields, 12, INK80, F_REG)
bar(s, 0.85, 6.74, 0.1, 0.1, BLUE)
add_text(s, 1.05, 6.7, 11.0, 0.3, "현재 documents ≈ 4,000 · chunks ≈ 17,000 적재.", 11, INK48, F_REG)
footer(s, 7, "데이터베이스 구성")

# ===================================================================
# 7b. 수집 규모 (#3 — 크롤링 규모 가시화)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.2", "수집 규모",
       "144개 시드에서 출발해 약 17,000개 청크까지 — 학교 정보를 통째로.")
# 좌: 수집 대상 막대 (정적/게시판) — 실측 seeds.py
add_text(s, 0.85, 2.68, 5.6, 0.3, "수집 대상 — 시드 144개", 14, BLUE, F_SEMI)
targets = [("정적 안내 페이지", 124), ("게시판(목록)", 20)]
bx, bmaxw, bmax = 2.55, 3.3, 144
yy = 3.2
for lab, val in targets:
    add_text(s, 0.85, yy + 0.02, 1.7, 0.3, lab, 12, INK, F_REG)
    bar(s, bx, yy + 0.05, max(0.05, val / bmax * bmaxw), 0.26, BLUE)
    add_text(s, bx + val / bmax * bmaxw + 0.1, yy, 0.8, 0.3, str(val), 13, INK, F_SEMI)
    yy += 0.62
rrect(s, 0.85, 4.55, 5.6, 1.05, fill=PARCH, line=HAIR, radius=0.12)
add_text(s, 1.1, 4.72, 5.2, 0.7,
         "학과·기관·입학·기숙사·도서관 등 50여 개 부서·기관을 출처 단위로 분류해 수집.",
         12, INK80, F_REG, line_spacing=1.2)
# 우: 첨부 파서 7종 — 실측 file_text_router
add_text(s, 6.85, 2.68, 5.6, 0.3, "첨부 파서 — 7종 형식 지원", 14, BLUE, F_SEMI)
parsers = ["PDF", "HWP", "HWPX", "DOCX", "XLSX", "PPTX", "이미지·OCR"]
pcw, pch, pgx = 1.72, 0.5, 0.12
for i, p in enumerate(parsers):
    col = i % 3
    row = i // 3
    px = 6.85 + col * (pcw + pgx)
    py = 3.15 + row * (pch + 0.14)
    hot = p == "이미지·OCR"
    pill(s, px, py, pcw, pch, BLUE if hot else PARCH, p, 12,
         WHITE if hot else INK80, F_SEMI)
add_text(s, 6.85, 4.55, 5.6, 0.9,
         "PDF·HWP·이미지의 표/텍스트를 파서와 한국어 OCR로 추출 → 검색 가능한 청크로 변환.",
         12, INK80, F_REG, line_spacing=1.2)
# 하단: 수집 결과 큰 숫자
hairline(s, 0.85, 5.85, 11.63, HAIR, 1.0)
res = [("≈ 4,000", "수집 문서", 0.85), ("≈ 17,000", "검색 청크", 4.72),
       ("50+", "부서·기관 출처", 8.59)]
for num, lab, x in res:
    add_text(s, x, 6.0, 3.7, 0.6, num, 34, BLUE, F_SEMI, align=PP_ALIGN.CENTER,
             tracking=-0.5, line_spacing=1.0)
    add_text(s, x, 6.66, 3.7, 0.3, lab, 12, INK48, F_REG, align=PP_ALIGN.CENTER)
footer(s, 0, "수집 규모")

# ===================================================================
# 8. 소스 구성 (D8) — DARK
# ===================================================================
s = slide(DARK)
header(s, "03 · 최종 결과 · 3.3", "소스 파일 구성", "세 컨테이너 단위로 정리한 핵심 모듈.", dark=True)
w, xs = grid(3, 0.30)
cols = [("rag/", "pipeline/chat_pipeline.py\nretrieval/{retriever, search_strategy, quality}\nselection/{reranker, topk_selector}\npreprocess/* · generation/answer_postprocessor\nprompt/prompt_builder · embedding/koe5_embedder\nevaluation/goldset"),
        ("backend/", "api/{chat, kakao, health}\nservices/rag_client\nutils/{intent_classifier,\n       kakao_template, profanity_filter}\ndatabase/{query, response, retrieval}_logs"),
        ("crawler/", "extractors/{board, static, image_text}\nparsers/{pdf, hwp, hwpx, ooxml, image}\ningestion/{chunker, pgvector_loader,\n          embed_worker}\nocr/korean_ocr · run/run_crawl_to_rag")]
for (name, body), x in zip(cols, xs):
    rrect(s, x, 2.75, w, 3.6, fill=DARK2, line=HAIR_D, radius=0.16)
    add_text(s, x + 0.24, 2.95, w - 0.48, 0.4, name, 18, WHITE, F_SEMI)
    bar(s, x + 0.24, 3.42, 0.5, 0.03, SKY)
    add_text(s, x + 0.24, 3.55, w - 0.42, 2.7, body, 11.5, MUTE_D, F_MONO, line_spacing=1.3)
hairline(s, 0.85, 6.55, 11.63, SKY, 1.0)
add_text(s, 0.85, 6.62, 11.63, 0.3, "세 컨테이너 · 하나의 파이프라인.", 11, MUTE_D, F_REG)
footer(s, 8, "소스 구성", dark=True)

# ===================================================================
# 9. 시나리오 1-① 전처리·검색 (C1)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.4", "시나리오 1 — 학사 일정 ①", "“1학기 중간고사 기간 알려줘”를 실제 파이프라인에 태운 state.")
add_text(s, 0.85, 2.68, 4.6, 0.3, "전처리 → 검색", 14, BLUE, F_SEMI)
add_text(s, 0.85, 3.05, 4.6, 3.6,
         "• INFO로 분류되어 검색 단계로 진입\n\n"
         "• 키워드 10개 추출, 시간신호 ‘1학기’ 인식\n\n"
         "• 학사일정(academic_schedule) 패밀리로\n  벡터 검색 강제\n\n"
         "• canonical 필터로 후보 10→4건 축소\n\n"
         "• 품질 게이트 통과 → 폴백 미발동",
         14, INK80, F_REG, line_spacing=1.2)
codetile(s, 5.75, 2.68, 6.73, 3.85, [
    [('$ query: "1학기 중간고사 기간 알려줘"', MUTE_D)],
    [("primary_intent      : ", MUTE_D), ("INFO", SKY)],
    [("query_family        : ", MUTE_D), ("academic_schedule", SKY)],
    [("keywords            : 중간고사 · 1학기 · 기간 …(10)", WHITE)],
    [("temporal_signals    : {semesters:[1학기]}", WHITE)],
    [("rewritten_queries   : 4", WHITE)],
    [("query_vector_size   : ", MUTE_D), ("1024", SKY)],
    [("effective_strategy  : ", MUTE_D), ("vector", SKY), ("  (fallback: false)", MUTE_D)],
    [("retrieval_quality   : {ok:true, top1:1.15,", WHITE)],
    [("                       context_chars:13194}", WHITE)],
    [("temporal_validation : ", MUTE_D), ("matched [true]", SKY)],
])
hairline(s, 0.85, 6.7, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.77, 11.63, 0.3,
         "모든 수치는 state.to_log_dict() 실제 출력 (2026-06-02).", 11, INK48, F_REG)
footer(s, 9, "시나리오 1")

# ===================================================================
# 10. 시나리오 1-② 리랭킹·생성 (C2/C3)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.4", "시나리오 1 — 학사 일정 ②", "다신호 리랭킹이 공식 페이지를 1등으로, LLM이 근거로 답한다.")
codetile(s, 0.85, 2.68, 7.4, 2.95, [
    [("reranked → selected : 20 → 3", WHITE)],
    [("[1] 학사일정 페이지   rerank_score: ", MUTE_D), ("8.99", SKY)],
    [("    signals: canonical 3.0 + family_boost 2.48", WHITE)],
    [("             + verified_title 1.5 + heading 0.8", WHITE)],
    [("    (attachment chunk: family_penalty -2.8)", MUTE_D)],
    [("answer_input : context 3,989 · prompt 4,551", WHITE)],
    [("negative_repair : null", WHITE)],
])
codetile(s, 0.85, 5.78, 7.4, 1.1, [
    [("timings(ms): classify 0 · preprocess 5569 · embed 458", MUTE_D)],
    [("   retrieve 13057 · select 11 · generate 2961  (cold start)", MUTE_D)],
])
rrect(s, 8.55, 2.68, 3.93, 4.2, fill=PARCH, line=HAIR, radius=0.16)
add_text(s, 8.79, 2.92, 3.45, 0.3, "최종 답변", 14, BLUE, F_SEMI)
add_text(s, 8.79, 3.45, 3.45, 2.0,
         "“1학기 중간고사 기간은 4월 21일부터 27일까지입니다.”",
         18, INK, F_SEMI, line_spacing=1.25, tracking=-0.2)
hairline(s, 8.79, 5.75, 3.45, BLUE, 1.0)
add_text(s, 8.79, 5.88, 3.45, 0.9,
         "학교 공식 학사일정 페이지에 근거한, 군더더기 없는 답.", 12, INK80, F_REG)
footer(s, 10, "시나리오 1")

# ===================================================================
# 11. 시나리오 2 비정보성 (C4)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.4", "시나리오 2 — 비정보성 질의", "“안녕”은 검색을 타지 않고 입구에서 바로 처리한다.")
add_text(s, 0.85, 2.68, 4.6, 0.3, "입구에서 분기", 14, BLUE, F_SEMI)
add_text(s, 0.85, 3.05, 4.6, 3.4,
         "• GENERAL로 분류\n\n"
         "• 전처리·임베딩·검색·생성을\n  전부 건너뜀\n\n"
         "• 실행된 단계는 classify 하나\n\n"
         "• 비속어는 PROFANITY로 차단\n\n"
         "• 불필요한 검색 비용·오답을 원천 차단",
         14, INK80, F_REG, line_spacing=1.2)
codetile(s, 5.75, 2.68, 6.73, 3.55, [
    [('$ query: "안녕"', MUTE_D)],
    [("primary_intent      : ", MUTE_D), ("GENERAL", SKY)],
    [("timings             : [classify_primary_intent]", WHITE)],
    [("                       ← only stage", MUTE_D)],
    [("retrieved_doc_count : ", MUTE_D), ("0", SKY)],
    [("selected_doc_count  : ", MUTE_D), ("0", SKY)],
    [("answer >> 안녕하세요. 동의대학교 정보 안내를", WHITE)],
    [("          도와드리고 있어요…", WHITE)],
])
hairline(s, 0.85, 6.7, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.77, 11.63, 0.3,
         "입구에서 질문 성격을 가리면 속도와 품질을 동시에 지킨다.", 12, INK80, F_REG)
footer(s, 11, "시나리오 2")

# ===================================================================
# 11b. 마주친 문제 → 해결 (#4 — RAG가 왜 어려웠나)
# ===================================================================
RED = "C0392B"
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.5", "마주친 문제 → 해결",
       "데이터가 지저분할수록 RAG는 어렵다 — 발견하고, 고치고, 숫자로 확인했다.")
cols = [("발견한 문제", 0.85, 3.5, RED), ("해결 방법", 4.55, 4.6, INK),
        ("효과", 9.35, 3.13, BLUE)]
for lab, x, w, c in cols:
    add_text(s, x, 2.66, w, 0.3, lab, 12, c, F_SEMI)
hairline(s, 0.85, 3.0, 11.63, HAIR, 1.0)
rows = [
    ("PDF 바이너리·메뉴 노이즈 유입", "source_type 프리필터 + 파서 라우팅", "검색 노이즈 제거"),
    ("HWP·이미지 첨부 본문 누락", "HWP/HWPX 파서 + 한국어 OCR", "첨부 표·텍스트 확보"),
    ("중복 청크가 컨텍스트 점유", "dedup·다양성 기반 top-k 선택", "근거 다양성 ↑"),
    ("타 학과명 혼입(substring 오매칭)", "학과 경계 매칭(_dept_token_in_text)", "학과 Context 67→83%"),
    ("게시판 복제 공지가 정답 밀어냄", "board-noise 페널티 + 규칙 게이트", "공식 페이지 우선"),
    ("근거 있어도 답변 거절", "거절 프롬프트 재설계 + repair 강화", "거절 12.1→3.0%"),
]
yy = 3.14
for prob, sol, eff in rows:
    bar(s, 0.85, yy + 0.13, 0.08, 0.08, RED)
    add_text(s, 1.05, yy, 3.35, 0.5, prob, 12, INK, F_REG, line_spacing=1.05)
    add_text(s, 4.55, yy, 4.55, 0.5, sol, 12, INK80, F_REG, line_spacing=1.05)
    add_text(s, 9.35, yy, 3.13, 0.5, eff, 12, BLUE, F_SEMI, line_spacing=1.05)
    yy += 0.56
    hairline(s, 0.85, yy - 0.05, 11.63, HAIR, 0.5)
add_text(s, 0.85, 6.62, 11.63, 0.3,
         "“잘 만든 것”이 아니라 “무슨 문제를 풀었는가” — 데이터 품질이 RAG 품질의 8할.",
         12, INK80, F_REG)
footer(s, 0, "문제 → 해결")

# ===================================================================
# 12. 독창성 및 차별성 (D9)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.5", "독창성 및 차별성", "감이 아니라 숫자로 검증하며 만든 검색 품질.")
w, xs = grid(4, 0.30)
diff = [("01", "SRRF Fusion", "Softmax-RRF를 직접 구현하고 운영에 적용"),
        ("02", "Rule Gate", "정형 질의는 LLM 우회 → 환각 차단"),
        ("03", "Fallback + Rerank", "실패 시 전략 전환·다신호 재정렬"),
        ("04", "66-Q Eval", "정량 평가 + 측정 정직화 가드")]
for (num, t, b), x in zip(diff, xs):
    card(s, x, 2.75, w, 3.7, t, b, number=num, tsize=15, bsize=12)
hairline(s, 0.85, 6.6, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.67, 11.63, 0.3, "Measured, not guessed.", 13, BLUE, F_SEMI)
footer(s, 12, "독창성 및 차별성")

# ===================================================================
# 13. 분담 (예시 이름)
# ===================================================================
s = slide(PARCH)
header(s, "03 · 최종 결과 · 3.6", "분담 내용 및 수행 내용", "역할 분담 (이름은 예시 — 실제 팀원으로 교체).")
roles = [("조장", "RAG 파이프라인", "오케스트레이터 · 폴백 · 품질 게이트 · 아키텍처"),
         ("팀원 A", "크롤러", "게시판·첨부 파싱 · pgvector 적재"),
         ("팀원 B", "검색·리랭킹", "retriever · reranker · 하이브리드 융합"),
         ("팀원 C", "백엔드·인프라", "FastAPI · 카카오 웹훅 · Docker · Supabase"),
         ("팀원 D", "전처리·평가", "쿼리 전처리 · 골드셋 · 자동 평가")]
yy = 2.75
for who, mod, work in roles:
    rrect(s, 0.85, yy, 11.63, 0.72, fill=WHITE, line=HAIR, radius=0.1)
    add_text(s, 1.1, yy + 0.18, 1.8, 0.4, who, 14, BLUE, F_SEMI)
    add_text(s, 3.1, yy + 0.18, 2.6, 0.4, mod, 14, INK, F_SEMI)
    add_text(s, 5.9, yy + 0.2, 6.4, 0.4, work, 13, INK80, F_REG)
    yy += 0.82
footer(s, 13, "분담 내용")

# ===================================================================
# 14. 느낀점 (예시 문구)
# ===================================================================
s = slide(PARCH)
header(s, "03 · 최종 결과 · 3.7", "배우고 느낀 점", "예시 문구 — 실제 팀원 소감으로 교체하세요.")
w, xs = grid(3, 0.30)
notes = [("조장", "검색 품질은 한 기법이 아니라 여러 신호의 조합이라는 걸 체감했다. 정량 평가가 없었다면 자기만족에 그쳤을 것."),
         ("크롤러", "PDF·HWP·이미지처럼 제각각인 첨부를 일관된 텍스트로 만들며, 데이터 전처리가 품질의 8할임을 실감했다."),
         ("평가", "90%대 점수에 만족하다 평가 매칭 버그를 발견했고, 정직한 측정이 좋은 점수보다 중요함을 배웠다.")]
for (who, body), x in zip(notes, xs):
    card(s, x, 2.75, w, 3.7, who, body, fill=WHITE, tsize=15, bsize=13)
hairline(s, 0.85, 6.6, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.67, 11.63, 0.3, "한 번에 서비스가 굴러가는 전 과정을 경험한 프로젝트.", 12, INK80, F_REG)
footer(s, 14, "느낀 점")

# ===================================================================
# 14b. 평가 데이터셋 구성 (#8 — 평가 신뢰성)
# ===================================================================
s = slide(WHITE)
header(s, "03 · 최종 결과 · 3.8", "평가 데이터셋 — 66문항 골드셋",
       "감이 아니라 숫자로 — 팀이 직접 만들고 공식 출처로 검증한 정답셋.")
# 좌: 카테고리 파이 (22개 세부 → 6개 묶음, 합 66)
add_text(s, 0.85, 2.66, 5.4, 0.3, "질문 카테고리 (22종 → 6묶음)", 13, BLUE, F_SEMI)
cd = CategoryChartData()
cd.categories = ["학사·수강 24", "생활·시설 13", "학과·교직원 13",
                 "장학·등록 9", "첨부·표 4", "공지·국제 3"]
cd.add_series("문항", (24, 13, 13, 9, 4, 3))
gframe = s.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(0.7), Inches(2.95),
                            Inches(5.5), Inches(3.7), cd)
chart = gframe.chart
chart.has_title = False
chart.has_legend = True
chart.legend.position = XL_LEGEND_POSITION.RIGHT
chart.legend.include_in_layout = False
chart.legend.font.size = Pt(11)
plot = chart.plots[0]
plot.has_data_labels = True
plot.data_labels.show_value = True
plot.data_labels.number_format = '0'
plot.data_labels.number_format_is_linked = False
plot.data_labels.font.size = Pt(10)
plot.data_labels.font.color.rgb = rgb(WHITE)
pie_colors = [BLUE, SKY, "5AB0FF", "9AC8FF", INK48, MUTE_D]
for i, pt in enumerate(plot.series[0].points):
    pt.format.fill.solid()
    pt.format.fill.fore_color.rgb = rgb(pie_colors[i % len(pie_colors)])
# 우상: 검증 방법
add_text(s, 6.6, 2.66, 5.88, 0.3, "어떻게 검증했나", 13, BLUE, F_SEMI)
rrect(s, 6.6, 3.0, 5.88, 1.5, fill=PARCH, line=HAIR, radius=0.12)
add_text(s, 6.84, 3.18, 5.4, 1.2,
         "• 팀이 실제 학생 질문 유형으로 66문항 직접 작성\n"
         "• 정답 근거를 DB document_id로 조회 검증\n"
         "• 웹 출처는 공식 URL을 직접 열어 교차 확인",
         12.5, INK80, F_REG, line_spacing=1.35)
# 우하: source_type / 난이도 막대
add_text(s, 6.6, 4.72, 5.88, 0.3, "출처 유형 · 난이도", 13, BLUE, F_SEMI)
mini = [("DB 기반", 36, BLUE), ("웹페이지", 28, SKY), ("첨부파일", 2, INK48)]
yy = 5.08
for lab, val, c in mini:
    add_text(s, 6.6, yy, 1.5, 0.3, lab, 11, INK, F_REG)
    bar(s, 8.2, yy + 0.04, max(0.05, val / 66 * 3.4), 0.2, c)
    add_text(s, 8.2 + val / 66 * 3.4 + 0.1, yy, 0.7, 0.3, str(val), 11, INK80, F_SEMI)
    yy += 0.42
add_text(s, 6.6, 6.42, 5.88, 0.3,
         "난이도: easy 24 · medium 28 · hard 14", 11, INK48, F_REG)
footer(s, 0, "평가 데이터셋")

# ===================================================================
# 15. 주요 성과 (D10) — DARK
# ===================================================================
s = slide(DARK)
header(s, "03 · 최종 결과 · 3.8", "주요 성과", "골드셋 66문항 — 결정적 지표 중심으로, 정직하게.", dark=True)
stats = [("87.9%", "Top-5 Hit", 0.85), ("87.9%", "Context Hit", 3.18),
         ("95.9%", "Grounded", 5.51), ("80.3%", "Correct", 7.84),
         ("3.0%", "Refused", 10.17)]
sw = 2.31
for num, lab, x in stats:
    add_text(s, x, 2.78, sw, 0.8, num, 46, SKY, F_SEMI, align=PP_ALIGN.CENTER,
             tracking=-0.5, line_spacing=1.0)
    add_text(s, x, 3.7, sw, 0.3, lab, 13, MUTE_D, F_REG, align=PP_ALIGN.CENTER)
hairline(s, 0.85, 4.25, 11.63, HAIR_D, 1.0)
# improvement bars (left)
add_text(s, 0.85, 4.42, 5.5, 0.3, "Baseline → Final", 13, SKY, F_SEMI)
imp = [("Answer Refused", 12.1, 3.0, "12.1 → 3.0"),
       ("Answer Correct", 71.2, 80.3, "71.2 → 80.3"),
       ("학과별 Context", 67.0, 83.0, "67 → 83")]
yy = 4.84
for lab, a, b, txt in imp:
    add_text(s, 0.85, yy, 2.2, 0.3, lab, 11.5, WHITE, F_REG)
    bar(s, 3.0, yy + 0.04, a / 100 * 2.6, 0.13, "555555")
    bar(s, 3.0, yy + 0.23, b / 100 * 2.6, 0.13, SKY)
    add_text(s, 5.7, yy + 0.02, 1.7, 0.3, txt, 11, MUTE_D, F_MONO)
    yy += 0.58
# narrative card (right)
rrect(s, 7.5, 4.5, 4.98, 2.0, fill=DARK2, line=HAIR_D, radius=0.14)
add_text(s, 7.74, 4.7, 4.5, 1.3,
         "Context Hit이 92.4%까지 올랐지만, 평가 매칭 버그를 바로잡아 정직한 87.9%로 보고합니다.",
         13, WHITE, F_REG, line_spacing=1.25)
add_text(s, 7.74, 5.95, 4.5, 0.4, "남은 과제: 기숙사 DB 갭 · LLM 분산", 11, MUTE_D, F_REG)
add_text(s, 6.48, 6.7, 6.0, 0.3, "Goldset 66 Q · 2026-06-02", 10, MUTE_D, F_REG,
         align=PP_ALIGN.RIGHT)
footer(s, 15, "주요 성과", dark=True)

# ===================================================================
# 16. 결론 및 향후 과제
# ===================================================================
s = slide(WHITE)
header(s, "04 · 결론", "결론 및 향후 과제", "흩어진 정보를, 한 곳에서, 근거와 함께.")
# 좌: 유사 서비스 비교 표 (#6)
add_text(s, 0.85, 2.62, 6.6, 0.3, "유사 서비스 비교", 13, BLUE, F_SEMI)
tx0, tw_item, tw_col = 0.85, 2.55, 1.35
cx = [tx0, tx0 + tw_item, tx0 + tw_item + tw_col, tx0 + tw_item + 2 * tw_col]
rrect(s, cx[3] - 0.06, 3.0, tw_col + 0.12, 3.2, fill="EAF3FF", line=None, radius=0.1)
heads = ["항목", "홈페이지", "ChatGPT", "dong-gu"]
for i, h in enumerate(heads):
    add_text(s, cx[i], 3.08, (tw_item if i == 0 else tw_col), 0.4, h, 13,
             BLUE if i == 3 else INK, F_SEMI,
             align=(PP_ALIGN.LEFT if i == 0 else PP_ALIGN.CENTER))
hairline(s, tx0, 3.52, tw_item + 3 * tw_col, INK, 1.0)
crows = [("자연어 질의", "✗", "✓", "✓"), ("공식 문서 기반", "✓", "✗", "✓"),
         ("첨부파일 검색", "✗", "✗", "✓"), ("카카오톡 사용", "✗", "✗", "✓"),
         ("근거 출처 제시", "△", "✗", "✓")]
ry = 3.66
for item, a, b, d in crows:
    add_text(s, cx[0], ry, tw_item, 0.4, item, 12.5, INK80, F_REG)
    for j, mark in enumerate([a, b, d]):
        col = BLUE if (j == 2 and mark == "✓") else INK48
        add_text(s, cx[j + 1], ry, tw_col, 0.4, mark, 15, col, F_SEMI,
                 align=PP_ALIGN.CENTER)
    ry += 0.50
    hairline(s, tx0, ry - 0.04, tw_item + 3 * tw_col, HAIR, 0.5)
# 우: 향후 과제
card(s, 7.65, 2.95, 4.83, 3.45, "향후 과제",
     "• 평가 다회 평균화로 분산 완화\n• 재크롤링 확대로 DB 갭 보완\n• cross-encoder 리랭커 도입\n• repair 커버리지 확대",
     fill=PARCH, accent=BLUE, bsize=13)
hairline(s, 0.85, 6.6, 11.63, BLUE, 1.5)
add_text(s, 0.85, 6.67, 11.63, 0.3,
         "학생이 늘 쓰는 카카오톡에서, 공식 문서에 근거한 답을.", 12, INK80, F_REG)
footer(s, 16, "결론")

# ===================================================================
# 17. 참고문헌 & 설치
# ===================================================================
s = slide(PARCH)
header(s, "05 · 참고문헌 · 설치", "참고문헌 & 설치 안내", "원논문·핵심 라이브러리와 한 줄 설치 절차.")
card(s, 0.85, 2.65, 5.615, 3.9, "References",
     "1. Lewis et al. (2020) — RAG, NeurIPS\n2. Robertson & Zaragoza (2009) — BM25\n3. NAVER (2023) — KoE5 embedding\n4. Supabase pgvector docs\n5. Kakao i 오픈빌더 가이드\n6. bab2min (2021) — Kiwi",
     fill=WHITE, bsize=13)
card(s, 6.865, 2.65, 5.615, 3.9, "Install (요약)",
     "1) docker compose up -d  (3 services)\n2) .env 설정 (OpenAI · KoE5 · srrf)\n3) DB 초기화 + pgvector\n4) 크롤러로 문서 적재\n5) 카카오 오픈빌더에 스킬 URL 연결",
     fill=WHITE, accent=BLUE, bsize=13)
add_text(s, 7.105, 5.95, 5.1, 0.5, "자세한 절차는 부록 매뉴얼 참고.", 11, INK48, F_REG)
footer(s, 17, "참고문헌 · 설치")

# ===================================================================
# 18. CLOSING — DARK
# ===================================================================
s = slide(DARK)
add_text(s, 0.85, 0.55, 11.63, 0.30, "Q & A", 12, SKY, F_SEMI)
add_text(s, 0.85, 2.9, 11.63, 1.2, "감사합니다", 54, WHITE, F_SEMI,
         tracking=-0.5, line_spacing=1.0, align=PP_ALIGN.CENTER)
add_text(s, 0.85, 4.3, 11.63, 0.6,
         "흩어진 학교 정보를, 카카오톡 한 곳에서, 공식 문서에 근거해.",
         18, MUTE_D, F_REG, align=PP_ALIGN.CENTER)
hairline(s, 4.0, 5.6, 5.33, HAIR_D, 1.0)
add_text(s, 0.85, 5.8, 11.63, 0.4, "dong-gu · 동의대학교 RAG 챗봇", 12, MUTE_D, F_REG,
         align=PP_ALIGN.CENTER)

import os
# 주의: pt2.pptx는 수동 편집된 마스터(목차·캡쳐 이미지·설치 메뉴얼 포함)이므로 덮어쓰지 않는다.
# 본 스크립트는 pt2.generated.pptx로만 출력하고, 신규/수정 슬라이드는 PowerPoint에서 마스터로 복사한다.
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pt2.generated.pptx")
prs.save(out)
print("SAVED:", out, "slides:", len(prs.slides._sldIdLst))
