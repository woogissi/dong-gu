import json
import os
import unittest
import urllib.request
from unittest.mock import patch

from rag.llm.answer_generator import generate_answer
from rag.prompt.prompt_builder import build_prompt


OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.2:3b")


class _FakeOpenAIResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "Registration is open during the documented period."
                        }
                    }
                ]
            }
        ).encode("utf-8")


class _FakeOllamaResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {"response": "Registration is open during the documented period."}
        ).encode("utf-8")


class AnswerGeneratorTest(unittest.TestCase):
    def test_generate_answer_calls_openai_when_provider_is_openai(self) -> None:
        prompt = build_prompt(
            query="When is registration?",
            context="Registration is open from March 4 to March 6, 2026.",
        )

        env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            with patch("urllib.request.urlopen", return_value=_FakeOpenAIResponse()) as urlopen:
                answer = generate_answer(prompt)

        self.assertIn("Registration", answer)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(payload["model"], OPENAI_MODEL)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("When is registration?", payload["messages"][0]["content"])
        self.assertEqual(request.headers["Authorization"], "Bearer test-key")

    def test_generate_answer_calls_ollama_when_provider_is_ollama(self) -> None:
        prompt = build_prompt(
            query="When is registration?",
            context="Registration is open from March 4 to March 6, 2026.",
        )

        with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}, clear=False):
            with patch("urllib.request.urlopen", return_value=_FakeOllamaResponse()) as urlopen:
                answer = generate_answer(prompt)

        self.assertIn("Registration", answer)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "http://host.docker.internal:11434/api/generate")
        self.assertEqual(payload["model"], LLAMA_MODEL)
        self.assertIn("When is registration?", payload["prompt"])

    def test_generate_answer_returns_extractive_fallback_when_provider_fails(self) -> None:
        prompt = build_prompt(
            query="How do I pay tuition?",
            context=(
                "Tuition payment is available from February 19 to February 24, 2026. "
                "Students can pay through a virtual account."
            ),
        )

        env = {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
                answer = generate_answer(prompt)

        self.assertIn("Tuition", answer)
        self.assertIn("LLM", answer)
        self.assertIn("connection refused", answer)

    def test_generate_answer_returns_fallback_without_openai_key(self) -> None:
        prompt = build_prompt(
            query="How do I pay tuition?",
            context="Tuition payment is available from February 19 to February 24, 2026.",
        )

        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=True):
            answer = generate_answer(prompt)

        self.assertIn("Tuition", answer)
        self.assertIn("OPENAI_API_KEY is not set", answer)

    def test_live_openai_generated_answer_is_visible(self) -> None:
        if not os.getenv("OPENAI_API_KEY"):
            self.skipTest("OPENAI_API_KEY is not set.")

        prompt = build_prompt(
            query="How do I pay tuition?",
            context=(
                "Tuition payment is available from February 19 to February 24, 2026. "
                "Virtual account transfers are available 24 hours a day, but the final "
                "day closes at 16:00."
            ),
        )

        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=False):
            answer = generate_answer(prompt)
        print("\n[OpenAI generated answer]\n" + answer)

        self.assertTrue(answer.strip())
        self.assertNotIn("[DUMMY ANSWER]", answer)
        self.assertNotIn("LLM 연결 실패", answer)


if __name__ == "__main__":
    unittest.main()
