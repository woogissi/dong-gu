from app.services.logging.query_logger import log_query


async def save_query_log(**kwargs) -> None:
    await log_query(**kwargs)
