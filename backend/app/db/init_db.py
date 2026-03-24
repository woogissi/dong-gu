from app.db.base import Base
from app.db.session import engine
from app.models.document import Document  # noqa: F401
from app.models.embedding import Embedding  # noqa: F401
from app.models.query_log import QueryLog  # noqa: F401


def init_db():
    Base.metadata.create_all(bind=engine)
