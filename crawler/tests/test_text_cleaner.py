import unittest

from crawler.normalize.text_cleaner import TextCleaner


class TextCleanerTest(unittest.TestCase):
    def test_build_clean_text_removes_common_navigation_noise(self) -> None:
        cleaner = TextCleaner()

        clean = cleaner.build_clean_text(
            "\n".join(
                [
                    "본문 바로가기",
                    "로그인",
                    "회원가입",
                    "게시물 좌측으로 이동",
                    "장학금 신청 안내 본문입니다.",
                    "작성일: 2026-05-20",
                    "조회수: 123",
                    "홈페이지 새창 열기",
                ]
            )
        )

        self.assertIn("장학금 신청 안내 본문입니다.", clean)
        self.assertNotIn("본문 바로가기", clean)
        self.assertNotIn("로그인", clean)
        self.assertNotIn("회원가입", clean)
        self.assertNotIn("게시물 좌측으로 이동", clean)
        self.assertNotIn("작성일", clean)
        self.assertNotIn("조회수", clean)
        self.assertNotIn("홈페이지 새창 열기", clean)

    def test_build_clean_text_does_not_append_table_text(self) -> None:
        cleaner = TextCleaner()

        clean = cleaner.build_clean_text(
            raw_text="본문 안내입니다.",
            table_text="구분 | 내용\nA | B",
        )

        self.assertEqual(clean, "본문 안내입니다.")
        self.assertNotIn("구분 | 내용", clean)


if __name__ == "__main__":
    unittest.main()
