"""Answer generation through the configured LLM provider."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from rag.fallback.extractive import build_extractive_fallback

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_OLLAMA_BASE_URL = "http://host.docker.internal:11434"
_DEFAULT_LLAMA_MODEL = "llama3.2:3b"
_DEFAULT_TIMEOUT_SECONDS = 90
_DEFAULT_MAX_TOKENS = 800
_DEFAULT_NUM_PREDICT = 256
# 고정 seed로 동일 입력의 출력 분산을 제거(재현성). rewrite·답변 생성 모두 적용된다.
# 환경변수 OPENAI_SEED / LLAMA_SEED 로 덮어쓸 수 있다.
_DEFAULT_LLM_SEED = 42


def generate_answer(prompt: str, *, system_prompt: str | None = None) -> str:
    try:
        return _generate_with_provider(prompt, system_prompt=system_prompt)
    except Exception as exc:
        return build_extractive_fallback(prompt, error=str(exc))


def _generate_with_provider(prompt: str, *, system_prompt: str | None = None) -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        return _generate_with_openai(prompt, system_prompt=system_prompt)
    if provider == "ollama":
        return _generate_with_ollama(prompt)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")


def _generate_with_openai(prompt: str, *, system_prompt: str | None = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    base_url = os.getenv("OPENAI_BASE_URL", _DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model = os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)))
    max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))

    if system_prompt:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
    else:
        messages = [{"role": "user", "content": prompt}]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "seed": int(os.getenv("OPENAI_SEED", str(_DEFAULT_LLM_SEED))),
    }
    request = urllib.request.Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {body}") from exc

    choices = response_payload.get("choices", [])
    if not choices:
        raise RuntimeError("OpenAI returned no choices.")
    message = choices[0].get("message", {})
    answer = str(message.get("content", "")).strip()
    if not answer:
        raise RuntimeError("OpenAI returned an empty response.")
    return answer


def _generate_with_ollama(prompt: str) -> str:
    base_url = os.getenv("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    model = os.getenv("LLAMA_MODEL", _DEFAULT_LLAMA_MODEL)
    timeout = float(os.getenv("LLAMA_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)))
    num_predict = int(os.getenv("LLAMA_NUM_PREDICT", str(_DEFAULT_NUM_PREDICT)))

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
            "top_p": 0.9,
            "num_predict": num_predict,
            "repeat_penalty": 1.15,
            "seed": int(os.getenv("LLAMA_SEED", str(_DEFAULT_LLM_SEED))),
        },
    }
    request = urllib.request.Request(
        url=f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc

    answer = str(response_payload.get("response", "")).strip()
    if not answer:
        raise RuntimeError("Ollama returned an empty response.")
    return answer

