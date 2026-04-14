from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query

pipeline = ChatPipeline()
result = pipeline.run(Query(text="휴학 어떻게 해?"))