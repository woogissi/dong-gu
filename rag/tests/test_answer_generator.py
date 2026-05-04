import json
import os
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from rag.llm.answer_generator import generate_answer
from rag.prompt.prompt_builder import build_prompt


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.2:3b")


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"response": "수강정정 기간은 문서에 안내된 기간을 확인하세요."}).encode("utf-8")


def _ollama_has_model(model_name: str) -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False

    return any(model.get("name") == model_name or model.get("model") == model_name for model in payload.get("models", []))


class AnswerGeneratorTest(unittest.TestCase):
    def test_generate_answer_calls_ollama(self) -> None:
        prompt = build_prompt(
            query="수강정정 기간 알려줘",
            context="수강정정 기간은 2026년 3월 4일부터 3월 6일까지입니다.",
        )

        with patch("urllib.request.urlopen", return_value=_FakeResponse()) as urlopen:
            answer = generate_answer(prompt)

        self.assertIn("수강정정", answer)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], LLAMA_MODEL)
        self.assertIn("수강정정 기간 알려줘", payload["prompt"])

    def test_generate_answer_returns_extractive_fallback_when_ollama_fails(self) -> None:
        prompt = build_prompt(
            query="등록금 납부 방법 알려줘",
            context="등록금 납부 기간은 2026년 2월 19일부터 2월 24일까지입니다. 국민은행 가상계좌로 납부할 수 있습니다.",
        )

        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            answer = generate_answer(prompt)

        self.assertIn("등록금", answer)
        self.assertIn("가상계좌", answer)
        self.assertIn("Llama 연결 실패", answer)

    def test_live_llama_generated_answer_is_visible(self) -> None:
        if not _ollama_has_model(LLAMA_MODEL):
            self.skipTest(f"Ollama model is not available: {LLAMA_MODEL}")

        prompt = build_prompt(
            query="등록금 납부 방법 알려줘",
            context=(
                "2026-1학기 등록금 납부 기간은 2026년 2월 19일 목요일부터 "
                "2월 24일 화요일 16시까지입니다. 국민은행 가상계좌는 24시간 이체 가능하지만 "
                "마감일은 16시까지만 가능합니다. 재학생 및 복학생은 등록기간에 납부은행 창구 "
                "또는 국민은행 가상계좌로 납부할 수 있습니다."
            ),
        )

        answer = generate_answer(prompt)
        print("\n[Llama generated answer]\n" + answer)

        self.assertTrue(answer.strip())
        self.assertNotIn("[DUMMY ANSWER]", answer)
        self.assertNotIn("Llama 연결 실패", answer)


if __name__ == "__main__":
    unittest.main()
