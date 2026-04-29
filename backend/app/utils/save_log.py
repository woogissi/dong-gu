import psycopg2

def save_qa_log(user_id, question, answer, retrieved_chunks, response_time, intent_type):
    conn = psycopg2.connect(
        host="postgres",
        dbname="chatbot",
        user="chatbot",
        password="chatbot"
    )
    cur = conn.cursor()

    query = """
    INSERT INTO qa_logs 
    (user_id, question, answer, retrieved_chunks, response_time, intent_type)
    VALUES (%s, %s, %s, %s, %s, %s);
    """

    cur.execute(query, (
        user_id,
        question,
        answer,
        retrieved_chunks,
        response_time,
        intent_type
    ))

    conn.commit()
    cur.close()
    conn.close()