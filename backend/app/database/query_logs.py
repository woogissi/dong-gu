import uuid
from backend.app.database.db import get_conn, put_conn


def create_query_log(user_id: str, question: str) -> str:
    request_id = str(uuid.uuid4())

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO query_logs
                (request_id, user_id, question)
                VALUES (%s, %s, %s);
                """,
                (request_id, user_id, question),
            )
        conn.commit()
        return request_id

    except Exception:
        conn.rollback()
        raise

    finally:
        put_conn(conn)


def update_query_intent(request_id: str, intent_type: str) -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE query_logs
                SET intent_type = %s
                WHERE request_id = %s;
                """,
                (intent_type, request_id),
            )
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        put_conn(conn)