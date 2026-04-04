"""
사용자 입력 쿼리 키워드(엔티티) 추출
ex) 중앙도서관 주말에도 열어?
-> 시설 : 중앙도서관, 조건 : 주말, 의도 : 운영시간
"""

from typing import List

def extract_keywords(query: str) -> List[str]:
    return query.split()