import unittest
from unittest.mock import patch

from rag.preprocess.dynamic_entities import build_aliases_from_rows
from rag.preprocess.query_features import extract_query_features


class DynamicEntityAliasTest(unittest.TestCase):
    def test_build_aliases_from_document_rows(self) -> None:
        aliases = build_aliases_from_rows(
            [
                {
                    "title": "컴퓨터공학과 사무실 위치 | 학과소개 | 컴퓨터공학과",
                    "department": "컴퓨터공학과",
                    "source_type": "department",
                    "source_url": "https://swcc.deu.ac.kr/computer/sub01_05.do",
                },
                {
                    "title": "수덕전 | 캠퍼스안내 | DEU",
                    "department": "",
                    "source_type": "institution",
                    "source_url": "https://www.deu.ac.kr/www/deu-campus-map.do",
                },
            ]
        )

        self.assertIn("컴퓨터공학과", aliases)
        self.assertIn("컴퓨터공학", aliases["컴퓨터공학과"])
        self.assertIn("수덕전", aliases)
        self.assertIn("computer", aliases["컴퓨터공학과"])

    def test_query_features_merge_dynamic_aliases(self) -> None:
        with patch(
            "rag.preprocess.query_features.get_dynamic_entity_aliases",
            return_value={"AI융합학과": ["AI융합", "ai convergence"]},
        ):
            features = extract_query_features("AI융합 사무실 위치", [])

        self.assertIn("AI융합학과", features.protected_terms)
        self.assertIn("AI융합", features.protected_terms)


if __name__ == "__main__":
    unittest.main()
