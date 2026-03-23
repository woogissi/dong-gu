# crawler/normalize/text_cleaner.py

import re


class TextCleaner:
    def normalize_spaces(self, text: str) -> str:
        if not text:
            return ""
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def remove_common_noise(self, text: str) -> str:
        if not text:
            return ""

        noise_patterns = [
            r"본문 바로가기",
            r"이전글\s*다음글",
            r"목록\s*$",
            r"인쇄\s*$",
            r"공유\s*$",
            r"저작권자.*",
        ]

        cleaned = text
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE)

        return cleaned.strip()

    def drop_too_short_lines(self, text: str, min_len: int = 2) -> str:
        if not text:
            return ""

        lines = [line.strip() for line in text.splitlines()]
        lines = [line for line in lines if len(line) >= min_len]
        return "\n".join(lines).strip()

    def build_clean_text(self, raw_text: str, table_text: str | None = None) -> str:
        text = self.normalize_spaces(raw_text)
        text = self.remove_common_noise(text)
        text = self.drop_too_short_lines(text)

        if table_text:
            table_text = self.normalize_spaces(table_text)
            if table_text:
                text = f"{text}\n\n{table_text}".strip()

        return text