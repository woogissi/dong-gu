"""
llm 입력용 프롬포트 생성
"""
def build_prompt(query: str, context: str) -> str:
    return f"""llm 입력용 프롬포트 생성
"""


# def build_prompt(query: str, context: str) -> str:
#     return f"""질문:
# {query}

# 문맥:
# {context}

# 위 문맥만 바탕으로 답변하세요.
# """