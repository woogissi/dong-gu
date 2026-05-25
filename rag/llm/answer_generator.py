"""Answer generation through the configured LLM provider."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

_DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
_DEFAULT_OLLAMA_BASE_URL = "http://host.docker.internal:11434"
_DEFAULT_LLAMA_MODEL = "llama3.2:3b"
_DEFAULT_TIMEOUT_SECONDS = 90
_DEFAULT_MAX_TOKENS = 512
_DEFAULT_NUM_PREDICT = 256


def generate_answer(prompt: str) -> str:
    try:
        return _generate_with_provider(prompt)
    except Exception as exc:
        return _build_extractive_fallback(prompt, error=str(exc))


def _generate_with_provider(prompt: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        return _generate_with_openai(prompt)
    if provider == "ollama":
        return _generate_with_ollama(prompt)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")


def _generate_with_openai(prompt: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    base_url = os.getenv("OPENAI_BASE_URL", _DEFAULT_OPENAI_BASE_URL).rstrip("/")
    model = os.getenv("OPENAI_MODEL", _DEFAULT_OPENAI_MODEL)
    timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)))
    max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", str(_DEFAULT_MAX_TOKENS)))

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "top_p": 0.9,
        "max_tokens": max_tokens,
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


def _build_extractive_fallback(prompt: str, *, error: str) -> str:
    context = _extract_section(prompt, "문서")
    query = _extract_section(prompt, "질문")
    sentences = _split_sentences(context)

    if not sentences:
        return "제공된 문서에서 관련 정보를 찾지 못했습니다."

    query_terms = set(_tokenize(query))
    ranked = sorted(
        sentences,
        key=lambda sentence: (
            _term_overlap_score(sentence, query_terms),
            len(sentence),
        ),
        reverse=True,
    )
    selected = [sentence for sentence in ranked[:4] if sentence.strip()]
    if not selected:
        return "제공된 문서에서 관련 정보를 찾지 못했습니다."

    answer = "\n".join(f"- {sentence.strip()}" for sentence in selected)
    return f"{answer}\n\n(텍스트 fallback: LLM 연결 실패 - {error})"


def _extract_section(prompt: str, section_name: str) -> str:
    next_sections = {
        "질문": "문서",
        "문서": "답변",
    }
    next_section = next_sections.get(section_name)
    if next_section:
        pattern = rf"\[{re.escape(section_name)}\]\n(.*?)(?=\n\[{re.escape(next_section)}\]\n|\Z)"
    else:
        pattern = rf"\[{re.escape(section_name)}\]\n(.*)"
    match = re.search(pattern, prompt, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _split_sentences(text: str) -> list[str]:
    content_lines = [
        line.strip()
        for line in text.splitlines()
        if _is_content_line(line.strip())
    ]
    normalized = re.sub(r"\s+", " ", " ".join(content_lines))
    chunks = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+", normalized)
    return [chunk.strip(" -")[:240] for chunk in chunks if len(chunk.strip()) >= 20]


def _is_content_line(line: str) -> bool:
    if not line:
        return False
    ignored_prefixes = (
        "[문서",
        "[TITLE]",
        "[BODY]",
        "[ATTACHMENT]",
        "title:",
        "source_url:",
        "source_type:",
        "content_type:",
        "published_at:",
        "scores:",
        "chunk_id:",
        "doc_id:",
        "section:",
        "content:",
    )
    if line in {"body"}:
        return False
    return not line.startswith(ignored_prefixes)


def _term_overlap_score(sentence: str, query_terms: set[str]) -> int:
    sentence_terms = set(_tokenize(sentence))
    return len(query_terms & sentence_terms)


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower())
