"""OCR 레이아웃(표) 재구성 단위 테스트.

EasyOCR 엔진 호출 없이 reconstruct_layout 로직만 검증한다
(EasyOCR readtext가 반환하는 [bbox, text, conf] 형식의 합성 입력 사용).
"""

import unittest

from crawler.ocr.korean_ocr import KoreanOCREngine


def _box(x0, y0, x1, y1, text, conf=0.9):
    # EasyOCR bbox: 4점 좌표 [좌상, 우상, 우하, 좌하]
    return ([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], text, conf)


class ReconstructLayoutTest(unittest.TestCase):
    def setUp(self):
        self.engine = KoreanOCREngine()

    def test_same_row_cells_joined_with_tab(self):
        # 같은 y대역, x로 떨어진 3개 셀 → 한 행에 탭으로 결합
        raw = [
            _box(0, 0, 80, 20, "교과목명"),
            _box(200, 2, 260, 22, "학점"),
            _box(400, 1, 460, 21, "이수구분"),
        ]
        out = self.engine.reconstruct_layout(raw)
        self.assertEqual(out.count("\n"), 0, "같은 행은 한 줄이어야 한다")
        self.assertIn("\t", out, "열 간격이 큰 셀은 탭으로 구분돼야 한다")
        self.assertEqual(out, "교과목명\t학점\t이수구분")

    def test_different_rows_separated_by_newline(self):
        # y가 크게 다른 박스 → 다른 행
        raw = [
            _box(0, 0, 80, 20, "1학년"),
            _box(0, 100, 80, 120, "2학년"),
        ]
        out = self.engine.reconstruct_layout(raw)
        self.assertEqual(out, "1학년\n2학년")

    def test_table_grid_preserves_rows_and_columns(self):
        # 2x2 표: 행/열 구조 보존
        raw = [
            _box(0, 0, 80, 20, "간호학개론"),
            _box(300, 0, 360, 20, "2"),
            _box(0, 100, 80, 120, "기본간호학"),
            _box(300, 100, 360, 120, "3"),
        ]
        out = self.engine.reconstruct_layout(raw)
        lines = out.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "간호학개론\t2")
        self.assertEqual(lines[1], "기본간호학\t3")

    def test_single_cell_rows_have_no_tab(self):
        # 단일 셀 행(일반 본문)은 탭 없이 그대로
        raw = [
            _box(0, 0, 200, 20, "이수표 안내문입니다"),
            _box(0, 60, 200, 80, "아래 표를 참고하세요"),
        ]
        out = self.engine.reconstruct_layout(raw)
        self.assertNotIn("\t", out)
        self.assertEqual(out, "이수표 안내문입니다\n아래 표를 참고하세요")

    def test_empty_input_returns_empty(self):
        self.assertEqual(self.engine.reconstruct_layout([]), "")

    def test_malformed_bbox_falls_back_to_text(self):
        # bbox가 없는 항목도 텍스트는 보존
        raw = [(None, "텍스트만", 0.8)]
        out = self.engine.reconstruct_layout(raw)
        self.assertIn("텍스트만", out)


if __name__ == "__main__":
    unittest.main()
