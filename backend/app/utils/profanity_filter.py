import re


BAD_WORDS = {
    "시발",
    "씨발",
    "ㅅㅂ",
    "병신",
    "븅신",
    "개새끼",
    "꺼져",
    "닥쳐",
    "지랄",
    "엿먹어",
}


PATTERNS = [
    r"시+\s*발+",
    r"ㅅ+\s*ㅂ+",
    r"병\s*신",
    r"개\s*새\s*끼",
    r"닥\s*쳐",
]


def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.lower().strip()
    text = re.sub(r"[\s\.\,\!\?\~\-_]+", "", text)
    return text


def contains_profanity(text: str) -> bool:
    if not text:
        return False

    normalized = text.lower().strip()
    compact = normalize_text(text)

    for word in BAD_WORDS:
        if word in compact:
            return True

    for pattern in PATTERNS:
        if re.search(pattern, normalized):
            return True
        if re.search(pattern, compact):
            return True

    return False