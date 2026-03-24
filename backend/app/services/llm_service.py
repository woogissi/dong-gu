from app.services.llm.llm_client import ask_llm
from app.services.llm.response_parser import parse_llm_text
from app.services.rag.prompt import build_rag_prompt


async def generate_answer(question: str, search_results: list[dict]) -> str:
    prompt = build_rag_prompt(question, search_results)
    raw_answer = await ask_llm(prompt)
    return parse_llm_text(raw_answer)
