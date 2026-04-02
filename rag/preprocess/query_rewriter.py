"""
사용자 입력 질문 일반화, 키워드 추출 후
위 데이터 토대로 쿼리 재작성
"""

from typing import List

def rewrite_query(query: str, keywords: List[str]) -> str:
    return query