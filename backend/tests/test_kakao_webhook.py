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
                    "utterance": "안녕",
                }
            }
        )

        with patch(
            "backend.app.api.kakao.general_chat_service.process_general_chat",
            return_value="안녕하세요!",
        ), patch(
            "backend.app.api.kakao.acquire_user_lock",
            return_value=True,
        ), patch(
            "backend.app.api.kakao.release_user_lock",
            return_value=None,
        ):
            response = asyncio.run(kakao.kakao_webhook(request))

        output = response["template"]["outputs"][0]["simpleText"]["text"]
        self.assertEqual(output, "안녕하세요!")

    def test_info_intent_returns_text_card(self) -> None:
        request = DummyRequest(
            {
                "userRequest": {
                    "user": {"id": "info-user"},
                    "utterance": "수강신청 기간 알려줘",
                }
            }
        )
        pipeline = DummyPipeline("[DUMMY ANSWER] 수강신청 기간은 공지사항을 확인해주세요.")

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

        card = response["template"]["outputs"][0]["textCard"]
        self.assertIn("수강신청 기간은 공지사항을 확인해주세요.", card["description"])
        self.assertIn("사이트 바로가기:", card["description"])
        self.assertEqual(pipeline.last_query, "수강신청 기간 알려줘")


if __name__ == "__main__":
    unittest.main()
