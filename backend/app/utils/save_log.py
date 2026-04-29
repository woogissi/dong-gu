import os
import psycopg2
import uuid
from dotenv import load_dotenv

load_dotenv()

def save_qa_log(user_id, question, intent_type):
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL 환경변수가 설정되지 않았습니다.")

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    query = """
    INSERT INTO query_logs 
    (request_id, user_id, question, intent_type)
    VALUES (%s, %s, %s, %s);
    """

    cur.execute(query, (
        str(uuid.uuid4()),  # UUID 생성
        user_id,
        question,
        intent_type
    ))

    conn.commit()
    cur.close()
    conn.close()
    