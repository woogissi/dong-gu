from rag.pipeline.chat_pipeline import ChatPipeline
from rag.schemas.query import Query
from rag.embedding.koe5_embedder import KoE5Embedder

def test_pipeline_embedding() -> None:
    pipeline = ChatPipeline()
    query = Query(text="동의대학교 수강신청 기간은 언제인가요?")

    print("=== 파이프라인 실행 테스트 (임베딩 포함) ===")
    answer = pipeline.run(query)
    print(f"질문: {answer.question}")
    print(f"답변: {answer.answer}")
    print(f"소스 수: {len(answer.sources)}")
    print(f"성공 여부: {answer.success}")

    # 상태 로그 확인
    if pipeline.last_state:
        print(f"쿼리 벡터 길이: {len(pipeline.last_state.query_vector)}")
        if pipeline.last_state.query_vector:
            print(f"쿼리 벡터 앞 5개 값: {pipeline.last_state.query_vector[:5]}")

def test_embedding_direct() -> None:
    embedder = KoE5Embedder()

    print("\n=== 단일 텍스트 임베딩 테스트 ===")
    text = "동의대학교 수강신청 일정은 어디서 확인하나요?"
    vector = embedder.embed_text(text)
    print(f"벡터 길이: {len(vector)}")
    print(f"앞 5개 값: {vector[:5]}")

    print("\n=== 여러 chunk batch 임베딩 테스트 ===")
    texts = [
        "동의대학교 학사 일정 안내",
        "장학금 신청 기간 및 대상 안내",
        "도서관 이용 시간과 대출 규정",
    ]
    vectors = embedder.embed_documents(texts, batch_size=2)
    print(f"문서 수: {len(vectors)}")
    print(f"각 벡터 차원: {len(vectors[0])}")

    print("\n=== query 임베딩 테스트 ===")
    query = "수강신청 기간 알려줘"
    query_vector = embedder.embed_query(query)
    print(f"query 벡터 길이: {len(query_vector)}")

    print("\n=== 벡터 차원 수 확인 ===")
    dim = embedder.get_dimension()
    print(f"embedding dimension: {dim}")

def main() -> None:
    test_pipeline_embedding()
    # test_embedding_direct()

if __name__ == "__main__":
    main()