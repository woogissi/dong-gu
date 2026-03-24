"""
추후 query_log 테이블 CRUD를 담당할 repository.
현재는 구조만 미리 잡아둔다.
"""


class QueryLogRepository:
    def create(self, data: dict) -> None:
        pass

    def list(self, page: int = 1, size: int = 20) -> list[dict]:
        return []

    def get_by_id(self, log_id: int) -> dict | None:
        return None
