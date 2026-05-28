# crawler/normalize/text_cleaner.py

import re


class TextCleaner:
    """Build the RAG-facing clean text from already-extracted page text."""

    LINE_NOISE_EXACT = {
        "HOME",
        "TOP",
        "More",
        "SNS",
        "Quick Menu",
        "본문 바로가기",
        "메뉴 열기",
        "메뉴 닫기",
        "전체메뉴",
        "사이트맵",
        "로그인",
        "회원가입",
        "목록",
        "인쇄",
        "공유",
        "이전",
        "다음",
        "처음",
        "마지막",
        "구성원 보기",
        "바로가기",
        "홈페이지 새창 열기",
        "내용 상세 보기",
        "다운로드",
    }

    def normalize_spaces(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\s+\n", "\n", text)
        text = re.sub(r"\n\s+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def remove_common_noise(self, text: str) -> str:
        if not text:
            return ""

        noise_patterns = [
            r"본문\s*바로가기",
            r"메뉴\s*(열기|닫기)",
            r"전체\s*메뉴",
            r"사이트맵",
            r"로그인",
            r"회원가입",
            r"SNS\s*공유",
            r"페이스북|트위터|카카오스토리",
            r"게시물\s*(좌측|우측)으로\s*이동",
            r"이전\s*정지\s*시작\s*다음",
            r"이전글\s*[^\n]*다음글",
            r"작성일\s*:?\s*\d{4}[-.]\d{2}[-.]\d{2}",
            r"등록일\s*:?\s*\d{4}[-.]\d{2}[-.]\d{2}",
            r"작성자\s*:?\s*[^\n]+",
            r"조회수\s*:?\s*\d+",
        ]

        cleaned = text
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE | re.IGNORECASE)
        return cleaned.strip()

    def drop_too_short_lines(self, text: str, min_len: int = 2) -> str:
        if not text:
            return ""

        lines = [line.strip() for line in text.splitlines()]
        lines = [
            line
            for line in lines
            if len(line) >= min_len and not self._is_navigation_only_line(line)
        ]
        return "\n".join(lines).strip()

    def _is_navigation_only_line(self, line: str) -> bool:
        normalized = re.sub(r"\s+", " ", line).strip(" -*:/|")
        if not normalized:
            return True
        if normalized in self.LINE_NOISE_EXACT:
            return True
        if normalized.upper() in self.LINE_NOISE_EXACT:
            return True
        if re.fullmatch(r"(PDF|HWP|DOCX?|XLSX?)\s*다운로드", normalized, re.IGNORECASE):
            return True
        if re.fullmatch(r"[<>|·•-]+", normalized):
            return True
        return False

    def build_clean_text(self, raw_text: str, table_text: str | None = None) -> str:
        text = self.normalize_spaces(raw_text)
        text = self.remove_common_noise(text)
        text = self.drop_too_short_lines(text)
        return self.normalize_spaces(text)
