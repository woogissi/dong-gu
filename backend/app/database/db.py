import os
from psycopg2.pool import SimpleConnectionPool

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> None:
        return None


load_dotenv()


def _database_dsn() -> str:
    database_url = (os.getenv("DATABASE_URL") or "").strip()
    if database_url:
        if database_url.startswith("postgresql+psycopg2://"):
            return database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
        return database_url

    return " ".join(
        [
            f"host={os.getenv('POSTGRES_HOST', 'postgres')}",
            f"port={os.getenv('POSTGRES_PORT', '5432')}",
            f"dbname={os.getenv('POSTGRES_DB', 'chatbot')}",
            f"user={os.getenv('POSTGRES_USER', 'chatbot')}",
            f"password={os.getenv('POSTGRES_PASSWORD', 'chatbot')}",
        ]
    )


db_pool = SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=_database_dsn(),
)


def get_conn():
    return db_pool.getconn()


def put_conn(conn):
    db_pool.putconn(conn)
