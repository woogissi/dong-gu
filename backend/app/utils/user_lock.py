from threading import Lock

# 현재 처리 중인 사용자 목록
_processing_users: set[str] = set()

# set 동시 접근 보호용 락
_processing_lock = Lock()


def acquire_user_lock(user_id: str) -> bool:
    """
    같은 사용자의 요청이 이미 처리 중이면 False
    아니면 락을 걸고 True
    """
    if not user_id:
        return False

    with _processing_lock:
        if user_id in _processing_users:
            return False

        _processing_users.add(user_id)
        return True


def release_user_lock(user_id: str) -> None:
    """
    사용자 처리 완료 후 락 해제
    """
    if not user_id:
        return

    with _processing_lock:
        _processing_users.discard(user_id)