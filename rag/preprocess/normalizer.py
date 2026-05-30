"""규칙 기반 정규화
- 불필요한 공백 제거
- 특수문자 제거
- 자주 쓰이는 구어체 표현 교정"""


from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

try:  # pragma: no cover - fallback behavior is covered when Kiwi is patched out
    from kiwipiepy import Kiwi as _KiwiClass
except ImportError:  # pragma: no cover
    _KiwiClass = None

_CONTEXTUAL_REPLACEMENTS: dict[str, str] = {
    "어케": "어떻게",
    "어떡해": "어떻게",
    "공지사항": "공지",
    "기한이야": "기한",
    "마감이야": "마감",
    "동위대학교": "동의대",
    "동위대": "동의대",
    "동의대학교": "동의대",
    "DEU": "동의대",
    "deu": "동의대",
    "통버": "통학버스",
    "셔틀버스": "통학버스",
    "셔틀": "통학버스",
    "학식": "학생식당",
    "식단": "학생식당",
    "정보관": "정보공학관",
    "23번건물": "정보공학관",
    "23번 건물": "정보공학관",
    "컴공": "컴퓨터공학과",
    "국장": "국가장학금",
    # 건물/시설 줄임말
    "산학관": "산학협력관",
    "의보대": "의료보건관",
    "공대": "공학관",
    "생과대": "생활과학관",
    # 기숙사 줄임말
    "행긱": "행복기숙사",
    "효긱": "효민생활관",
    "긱사": "기숙사",
    # 기타 구어체
    "오티": "오리엔테이션",
    "도어": "DOOR",
    # 학과명 별칭 (시각디자인과 → 실제 학과명)
    "시각디자인과": "디자인조형학과",
    "시각디자인학과": "디자인조형학과",
}
_SPACED_PHRASE_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![0-9A-Za-z가-힣])언제\s+까지(?![0-9A-Za-z가-힣])"), "언제까지"),
    # 종강일 → 학기별 방학 시작일로 정규화 (스케줄 검색 개선)
    (re.compile(r"1학기\s*종강일?"), "1학기 하계방학 시작일"),
    (re.compile(r"2학기\s*종강일?"), "2학기 동계방학 시작일"),
    (re.compile(r"하계방학\s+시작일?"), "하계방학 시작일"),
    (re.compile(r"동계방학\s+시작일?"), "동계방학 시작일"),
)
_REPLACEMENT_WORD_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])"
    r"(?:"
    + "|".join(
        re.escape(term)
        for term in sorted(_CONTEXTUAL_REPLACEMENTS, key=len, reverse=True)
    )
    + r")"
    r"(?![0-9A-Za-z가-힣])"
)


def normalize_query(query: str) -> str:
    if not query:
        return ""

    text = unicodedata.normalize("NFKC", str(query))
    text = text.replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()

    text = re.sub(r"[^0-9A-Za-z가-힣\s\-/?.:]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    text = _apply_contextual_replacements(text)

    # 중복된 특수문자 제거 및 공백 정리
    text = re.sub(r"([?.:])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _apply_contextual_replacements(text: str) -> str:
    for pattern, replacement in _SPACED_PHRASE_REPLACEMENTS:
        text = pattern.sub(replacement, text)

    token_spans = _kiwi_token_spans(text)
    if token_spans:
        text = _replace_spans(text, token_spans)

    return _replace_regex_words(text)


def _kiwi_token_spans(text: str) -> list[tuple[int, int]]:
    kiwi = _get_kiwi()
    if kiwi is None:
        return []

    spans: list[tuple[int, int]] = []
    try:
        tokens = kiwi.tokenize(text)
    except Exception:  # pragma: no cover - defensive fallback for broken runtimes
        return []

    for token in tokens:
        start = getattr(token, "start", None)
        length = getattr(token, "len", None)
        if start is None or length is None:
            continue
        spans.append((int(start), int(start) + int(length)))
    return spans


def _replace_spans(text: str, spans: list[tuple[int, int]]) -> str:
    if not spans:
        return text

    pieces: list[str] | None = None
    cursor = 0
    for start, end in spans:
        if start < cursor:
            continue
        token = text[start:end]
        replacement = _CONTEXTUAL_REPLACEMENTS.get(token)
        if replacement is None:
            continue
        if pieces is None:
            pieces = []
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    if pieces is None:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces)


def _replace_regex_words(text: str) -> str:
    return _REPLACEMENT_WORD_RE.sub(
        lambda match: _CONTEXTUAL_REPLACEMENTS[match.group(0)],
        text,
    )


@lru_cache(maxsize=1)
def _get_kiwi() -> Any:
    if _KiwiClass is None:
        return None
    try:
        return _KiwiClass()
    except Exception:  # pragma: no cover - defensive fallback for broken installs
        return None
