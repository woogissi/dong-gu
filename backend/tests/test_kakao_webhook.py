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
        self.assertIn("textCard", response["template"]["outputs"][1])
        self.assertEqual(pipeline.last_query, "\uc218\uac15\uc2e0\uccad \uae30\uac04 \uc54c\ub824\uc918")

    def test_build_info_response_handles_answer_without_url(self) -> None:
        result = {
            "answer": "\uc218\ub355\uc804 \ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04\uc740 \uc77c\ubc18\uc801\uc73c\ub85c \uc810\uc2ec\uc2dc\uac04\uc5d0 \uc6b4\uc601\ub429\ub2c8\ub2e4.",
            "sources": [],
            "retrieval_log": {"selected_docs": []},
        }

        response, final_answer = kakao.build_info_response(result, "\uc218\ub355\uc804 \ud559\uc0dd\uc2dd\ub2f9 \uc6b4\uc601\uc2dc\uac04")

        output = response["template"]["outputs"][0]["simpleText"]["text"]
        card_url = response["template"]["outputs"][1]["textCard"]["buttons"][0]["webLinkUrl"]

        self.assertIn("\uc218\ub355\uc804 \ud559\uc0dd\uc2dd\ub2f9", output)
        self.assertIn("\ucd9c\ucc98/\uc0ac\uc774\ud2b8 \ubc14\ub85c\uac00\uae30", final_answer)
        self.assertEqual(card_url, "https://www.deu.ac.kr/")

    def test_build_info_response_prefers_rag_source_for_card_and_dedupes_answer_link(self) -> None:
        rag_url = "https://www.deu.ac.kr/www/source-notice.do"
        fallback_like_url = "https://www.deu.ac.kr/www/other-page.do"
        result = {
            "answer": f"답변입니다.\n\n출처/사이트 바로가기: {fallback_like_url}",
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
        self.assertIn(rag_url, final_answer)
        self.assertNotIn(fallback_like_url, final_answer)
        self.assertEqual(final_answer.count(rag_url), 1)

    def test_kakao_summary_keeps_source_line_within_limit(self) -> None:
        source_url = "https://www.deu.ac.kr/www/source-notice.do"
        long_answer = "가" * 650
        full_answer = f"{long_answer}\n\n출처/사이트 바로가기: {source_url}"

        summary = kakao._build_kakao_simple_summary(
            full_answer=full_answer,
            utterance="등록금 납부 기간 알려줘",
            link=source_url,
            result_dict={},
        )

        self.assertLessEqual(len(summary), 500)
        self.assertIn(source_url, summary)

if __name__ == "__main__":
    unittest.main()
