import asyncio
import unittest
from unittest.mock import patch

from backend.app.api import kakao


class DummyRequest:
    def __init__(self, body: dict) -> None:
        self._body = body

    async def json(self) -> dict:
        return self._body


class DummyPipeline:
    def __init__(self, answer: str) -> None:
        self.answer = answer

    def run(self, query):
        self.last_query = query.text
        return {
            "answer": self.answer,
        }


class KakaoWebhookTest(unittest.TestCase):
    def test_general_intent_returns_simple_text(self) -> None:
        request = DummyRequest(
            {
                "userRequest": {
                    "user": {"id": "general-user"},
                    "utterance": "\uc548\ub155",
                }
            }
        )

        with patch(
            "backend.app.api.kakao.general_chat_service.process_general_chat",
            return_value="\uc548\ub155\ud558\uc138\uc694",
        ), patch(
            "backend.app.api.kakao.acquire_user_lock",
            return_value=True,
        ), patch(
            "backend.app.api.kakao.release_user_lock",
            return_value=None,
        ):
            response = asyncio.run(kakao.kakao_webhook(request))

        output = response["template"]["outputs"][0]["simpleText"]["text"]
        self.assertEqual(output, "\uc548\ub155\ud558\uc138\uc694")

    def test_info_intent_returns_simple_text(self) -> None:
        request = DummyRequest(
            {
                "userRequest": {
                    "user": {"id": "info-user"},
                    "utterance": "\uc218\uac15\uc2e0\uccad \uae30\uac04 \uc54c\ub824\uc918",
                }
            }
        )
        pipeline = DummyPipeline("[DUMMY ANSWER] \uc218\uac15\uc2e0\uccad \uae30\uac04\uc740 \uacf5\uc9c0\uc0ac\ud56d\uc744 \ud655\uc778\ud574\uc8fc\uc138\uc694.")

        with patch(
            "backend.app.api.kakao.get_chat_pipeline",
            return_value=pipeline,
        ), patch(
            "backend.app.api.kakao.acquire_user_lock",
            return_value=True,
        ), patch(
            "backend.app.api.kakao.release_user_lock",
            return_value=None,
        ):
            response = asyncio.run(kakao.kakao_webhook(request))

        output = response["template"]["outputs"][0]["simpleText"]["text"]
        self.assertIn("\uc218\uac15\uc2e0\uccad \uae30\uac04\uc740 \uacf5\uc9c0\uc0ac\ud56d\uc744 \ud655\uc778\ud574\uc8fc\uc138\uc694.", output)
        # sources \uc5c6\uc73c\uba74 textCard(\ubc84\ud2bc) \ubbf8\ud3ec\ud568
        self.assertEqual(len(response["template"]["outputs"]), 1)
        self.assertEqual(pipeline.last_query, "\uc218\uac15\uc2e0\uccad \uae30\uac04 \uc54c\ub824\uc918")

    def test_build_info_response_no_button_when_no_sources(self) -> None:
        """\ubb38\uc11c \uc5c6\uc74c \ucf00\uc774\uc2a4: \ubc84\ud2bc \ubc0f \ucd9c\ucc98 \ud14d\uc2a4\ud2b8 \ubbf8\ud3ec\ud568"""
        result = {
            "answer": "\uc218\ub355\uc804 \ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04\uc740 \uc77c\ubc18\uc801\uc73c\ub85c \uc810\uc2ec\uc2dc\uac04\uc5d0 \uc6b4\uc601\ub429\ub2c8\ub2e4.",
            "sources": [],
            "retrieval_log": {"selected_docs": []},
        }

        response, final_answer = kakao.build_info_response(result, "\uc218\ub355\uc804 \ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04")

        output = response["template"]["outputs"][0]["simpleText"]["text"]
        self.assertIn("\uc218\ub355\uc804 \ud559\uc0dd\uc2dd\ub2f9", output)
        # \ubb38\uc11c \uc5c6\uc74c: \ubc84\ud2bc(textCard) \ubbf8\ud3ec\ud568
        self.assertEqual(len(response["template"]["outputs"]), 1)
        # \ucd9c\ucc98 \ud14d\uc2a4\ud2b8\ub3c4 \ubbf8\ud3ec\ud568
        self.assertNotIn("\ucd9c\ucc98/\uc0ac\uc774\ud2b8 \ubc14\ub85c\uac00\uae30", final_answer)

    def test_build_info_response_uses_rag_source_for_button(self) -> None:
        """문서 있음 케이스: RAG sources URL로 버튼 생성, 출처 텍스트는 답변에 미포함"""
        rag_url = "https://www.deu.ac.kr/www/source-notice.do"
        result = {
            "answer": "답변입니다.",
            "sources": [{"source": rag_url, "title": "공지"}],
            "retrieval_log": {
                "selected_docs": [
                    {"source": rag_url, "title": "공지"},
                ]
            },
        }

        response, final_answer = kakao.build_info_response(result, "수강신청 기간 알려줘")
        card_url = response["template"]["outputs"][1]["textCard"]["buttons"][0]["webLinkUrl"]

        self.assertEqual(card_url, rag_url)
        # 출처 텍스트는 답변 본문에 미포함
        self.assertNotIn("출처/사이트 바로가기", final_answer)

    def test_kakao_summary_trims_long_answer_within_limit(self) -> None:
        """긴 답변은 500자 이내로 축약 (출처 줄 없는 경우)"""
        long_answer = "가" * 650

        summary = kakao._build_kakao_simple_summary(
            full_answer=long_answer,
            utterance="등록금 납부 기간 알려줘",
            link="",
            result_dict={},
        )

        self.assertLessEqual(len(summary), 500)

if __name__ == "__main__":
    unittest.main()
