"""키워드 추출 모듈
- 사용자 질문에서 핵심 키워드 추출
- 엔티티 그룹별 대표 키워드 선정
- 불용어 제거 및 정규화
- 최대 12개 키워드 반환
"""


from __future__ import annotations

import re

from rag.preprocess.domain_knowledge import ENTITY_LEXICON


_STOPWORDS = {
    "은", "는", "이", "가", "을", "를", "에", "의",
    "좀", "좀요", "요", "해", "줘", "주세요",
    "알려줘", "알려주세요", "궁금해", "궁금합니다",
    "가능", "있어", "있나요", "뭐", "무엇", "어디",
}
_ENTITY_GROUP_STOPWORDS = {"기간", "시점"}

def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", text)

    cleaned_tokens: list[str] = []
    for token in tokens:
        if len(token) > 1:
            token = re.sub(r"(은|는|이|가|을|를|에|의|로|으로|에서|부터|까지|도)$", "", token)
        cleaned_tokens.append(token)

    return cleaned_tokens

def extract_keywords(query: str) -> list[str]:
    if not query:
        return []

    keywords_dict: dict[str, None] = {}

    for entity, lexemes in ENTITY_LEXICON.items():
        if entity in _ENTITY_GROUP_STOPWORDS:
            continue
        # 서브스트링 매칭 시 노이즈 방지를 위해 최소 2글자 이상인 lexeme만 서브스트링 허용
        if any(lexeme in query for lexeme in lexemes if len(lexeme) >= 2):
            keywords_dict[entity] = None

    for token in _tokenize(query):
        normalized = token.lower().strip()

        if len(normalized) <= 1 and not re.match(r"[a-z0-9]", normalized):
            continue

        if normalized in _STOPWORDS:
            continue

        keywords_dict[normalized] = None

    return list(keywords_dict.keys())[:12]
