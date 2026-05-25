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

if __name__ == "__main__":
    unittest.main()
