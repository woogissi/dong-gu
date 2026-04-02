"""
사용자 입력 쿼리 일반화
공백, 특수문자 제거 등
"""

def normalize_query(query: str) -> str:
    return query.strip()