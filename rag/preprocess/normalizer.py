"""규칙 기반 정규화
- 불필요한 공백 제거
- 특수문자 제거
- 자주 쓰이는 구어체 표현 교정"""

# Aho-Corasick 알고리즘, Synonym 필터 적용 고려

from __future__ import annotations

import re
import unicodedata

_COLLOQUIAL_MAP: dict[str, str] = {
    "어케": "어떻게",
    "어떡해": "어떻게",
    "언제 까지": "언제까지",
    "기한이야": "기한",
    "마감이야": "마감",
    "공지사항": "공지",
}

def normalize_query(query: str) -> str:
    if not query:
        return ""

    text = unicodedata.normalize("NFKC", str(query))
    text = text.replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()

    text = re.sub(r"[^0-9A-Za-z가-힣\s\-/?.:]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    for src, dst in _COLLOQUIAL_MAP.items():
        text = text.replace(src, dst)

# 중복된 특수문자 제거 및 공백 정리
    text = re.sub(r"([?.:])\1+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text
