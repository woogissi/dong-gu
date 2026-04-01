from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query

pipeline = ChatPipeline()
result = pipeline.run(Query(text="수강신청 기간 알려줘"))

print(result.model_dump())