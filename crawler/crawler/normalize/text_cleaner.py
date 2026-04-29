# crawler/normalize/text_cleaner.py

import re


class TextCleaner:                                          # raw데이터 -> clean데이터
    def normalize_spaces(self, text: str) -> str:           # 공백, 줄바꿈 정리 함수
        if not text:
            return ""
        text = text.replace("\xa0", " ")                    # non-breaking space을 공백으로
        text = re.sub(r"[ \t]+", " ", text)                 # 연속된 공백이나 탭을 한 칸 공백으로
        text = re.sub(r"\n{3,}", "\n\n", text)              # \n은 최대 두개
        return text.strip()                                 # 앞뒤 공백/줄바꿈 제거

    def remove_common_noise(self, text: str) -> str:        # 웹페이지 공통 노이즈 제거
        if not text:
            return ""

        noise_patterns = [                                  # 노이즈 패턴 목록
            r"본문 바로가기",
            r"이전글\s*다음글",
            r"목록\s*$",
            r"인쇄\s*$",
            r"공유\s*$",
            r"저작권자.*",
        ]

        cleaned = text
        for pattern in noise_patterns:                      # 노이즈 패턴 순차적으로 제거
            cleaned = re.sub(pattern, "", cleaned, flags=re.MULTILINE)

        return cleaned.strip()

    def drop_too_short_lines(self, text: str, min_len: int = 2) -> str:     # 너무 짧은 줄을 제거하는 함수
        if not text:
            return ""

        lines = [line.strip() for line in text.splitlines()]                # 텍스트를 줄 단위로 나눈 뒤, 각 줄 앞뒤 공백 제거 ex) "안내\n \n가\n수강신청" -> ["안내", "", "가", "수강신청"]
        lines = [line for line in lines if len(line) >= min_len]            # 길이 2 미만 줄은 제거 ex) ["안내", "", "가", "수강신청"] -> ["안내", "수강신청"]
        return "\n".join(lines).strip()                                     # 남은 줄들을 줄바꿈으로 다시 이어붙임

    def build_clean_text(self, raw_text: str, table_text: str | None = None) -> str:        # 메인 함수
        # 정리 공백/줄바꿈 제거, 노이즈 제거, 짧은 줄 제거
        text = self.normalize_spaces(raw_text)
        text = self.remove_common_noise(text)
        text = self.drop_too_short_lines(text)
        
        if table_text:                                          # 표 텍스트가 있는 경우만 최소 공백/줄 제거
            table_text = self.normalize_spaces(table_text)
            if table_text:
                text = f"{text}\n\n{table_text}".strip()

        return text