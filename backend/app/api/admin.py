from fastapi import APIRouter

router = APIRouter()


@router.get("/logs")
def get_logs(page: int = 1, size: int = 20):
    return {
        "success": True,
        "code": "LOGS_FETCHED",
        "message": "아직 DB 연동 전입니다. 추후 로그 목록 조회 구현 예정입니다.",
        "data": {"items": []},
        "meta": {
            "page": page,
            "size": size,
            "total": 0,
            "pages": 0,
        },
    }


@router.get("/stats")
def get_stats():
    return {
        "success": True,
        "code": "STATS_FETCHED",
        "message": "아직 통계 집계 전입니다.",
        "data": {
            "total_requests": 0,
            "success_rate": 0,
            "avg_response_time_ms": 0,
        },
    }
