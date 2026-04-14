import re
from functools import lru_cache


# 오탐 가능성이 비교적 낮은 직접 차단 단어
BAD_WORDS = {
    "개년", "개놈", "개돼지", "개새끼", "개자식", "개지랄", "개쓰레기",
    "걸레", "고자", "광년이", "구라", "구라쟁이",
    "노답", "놈", "놈새끼",
    "닥쳐", "대가리", "대갈통", "도라이", "돌아이", "또라이",
    "뒤져", "뒤져라", "디져", "디져라",
    "레기", "루저",
    "미친놈", "미친년", "멍청이", "머저리", "못난이",
    "병신", "븅신", "바보", "바보새끼", "버러지", "벌레", "븅딱",
    "시발", "씨발", "시발놈", "씨발놈", "시발년", "씨발년",
    "시발새끼", "씨발새끼", "시발련", "씨발련", "시발럼", "씨발럼",
    "씹", "씹새끼", "씹년", "씹놈", "씹자식", "씹창",
    "썅", "썅놈", "썅년",
    "아가리", "아닥", "양아치", "얼간이", "염병",
    "우라질", "인간쓰레기", "인간말종",
    "좆", "좆밥", "좆병신", "좆망", "지랄", "존나",
    "찐따", "찐따새끼", "초딩",
    "꺼져",
    "틀딱", "틀딱새끼",
    "패버려",
    "한심충", "호로새끼", "호로자식",
}

# 문맥에 따라 욕설 아닐 수도 있어서 따로 관리
# 예: "우리 자식", "엿 사왔어"
SOFT_BAD_WORDS = {
    "자식",
    "엿",
}

# 자주 나오는 우회 패턴
PATTERN_STRINGS = [
    r"시+\s*발+",
    r"씨+\s*발+",
    r"ㅅ+\s*ㅂ+",
    r"ㅆ+\s*ㅂ+",
    r"병+\s*신+",
    r"븅+\s*신+",
    r"개+\s*새+\s*끼+",
    r"닥+\s*쳐+",
    r"좆+",
    r"존+\s*나+",
    r"지+\s*랄+",
    r"꺼+\s*져+",
    r"뒤+\s*져+",
    r"미+\s*친+\s*[년놈]+",
    r"씹+",
    r"썅+",
]

# 자모 분리로 욕설을 쓰는 경우 일부 대응
JAMO_BAD_PATTERNS = [
    r"ㅅ\s*ㅣ\s*ㅂ\s*ㅏ\s*ㄹ",
    r"ㅆ\s*ㅣ\s*ㅂ\s*ㅏ\s*ㄹ",
    r"ㅂ\s*ㅕ\s*ㅇ\s*ㅅ\s*ㅣ\s*ㄴ",
    r"ㄱ\s*ㅐ\s*ㅅ\s*ㅐ\s*ㄲ\s*ㅣ",
    r"ㅈ\s*ㅗ\s*ㅈ",
]

# 숫자/영문 우회 일부 보정
CHAR_SUBSTITUTIONS = str.maketrans({
    "1": "ㅣ",
    "2": "ㅣ",
    "3": "e",
    "5": "s",
    "7": "ㄱ",
    "@": "a",
    "$": "s",
})


@lru_cache(maxsize=1)
def compile_patterns():
    return [re.compile(p, re.IGNORECASE) for p in PATTERN_STRINGS + JAMO_BAD_PATTERNS]


def normalize_text(text: str) -> str:
    """
    일반 비교용 정규화
    - 소문자화
    - 숫자/특수기호 일부 치환
    - 공백/구두점 제거
    - 반복 문자 축약 (시이이발 -> 시이발 정도)
    """
    if not text:
        return ""

    text = text.lower().strip()
    text = text.translate(CHAR_SUBSTITUTIONS)

    # 한글/영문/숫자/자모 외 대부분 제거 전에 공백 개념만 날림
    text = re.sub(r"[\s\.\,\!\?\~\-_\/\\\|\(\)\[\]\{\}\+]+", "", text)

    # 같은 문자가 3번 이상 반복되면 2번으로 축약
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)

    return text


def normalize_for_pattern(text: str) -> str:
    """
    패턴 매칭용 정규화
    - 공백은 남겨두되 특수문자 정리
    - 너무 과격하게 붙이지 않아서 패턴식이 먹도록 함
    """
    if not text:
        return ""

    text = text.lower().strip()
    text = text.translate(CHAR_SUBSTITUTIONS)

    # 특수문자는 공백으로 치환
    text = re.sub(r"[^0-9a-zA-Z가-힣ㄱ-ㅎㅏ-ㅣ]+", " ", text)

    # 공백 정리
    text = re.sub(r"\s+", " ", text).strip()

    # 반복 문자 축약
    text = re.sub(r"(.)\1{2,}", r"\1\1", text)

    return text


def contains_soft_bad_word(text: str) -> bool:
    """
    오탐 가능성이 있는 단어는 조금 더 조심해서 검사
    """
    normalized = normalize_text(text)
    pattern_ready = normalize_for_pattern(text)

    # "자식아", "엿먹어" 같은 경우는 잡고
    # 일반 명사로 쓰인 경우는 가능한 덜 잡도록 보수적으로 처리
    soft_patterns = [
        r"자식[아이은을도]?",
        r"엿\s*먹",
        r"엿\s*같",
    ]

    for word in SOFT_BAD_WORDS:
        if word in normalized:
            for p in soft_patterns:
                if re.search(p, pattern_ready):
                    return True

    return False


def contains_profanity(text: str) -> bool:
    if not text or not text.strip():
        return False

    normalized = normalize_text(text)
    pattern_ready = normalize_for_pattern(text)
    compiled_patterns = compile_patterns()

    # 1. 직접 단어 포함 검사
    for word in BAD_WORDS:
        if word in normalized:
            return True

    # 2. 정규식 검사
    for pattern in compiled_patterns:
        if pattern.search(text):
            return True
        if pattern.search(pattern_ready):
            return True
        if pattern.search(normalized):
            return True

    # 3. 오탐 가능 단어 별도 처리
    if contains_soft_bad_word(text):
        return True

    return False