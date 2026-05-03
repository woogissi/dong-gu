from backend.app.database.db import get_conn, put_conn


def save_response_log(
    request_id: str,
    answer_text: str | None,
    success: bool,
    error_message: str | None = None,
    response_time_ms: int | None = None,
) -> None:
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO response_logs
                (request_id, answer_text, success, error_message, response_time_ms)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (
                    request_id,
                    answer_text,
                    success,
                    error_message,
                    response_time_ms,
                ),
            )
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        put_conn(conn)