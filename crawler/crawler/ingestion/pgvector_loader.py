# crawler/ingestion/pgvector_loader.py

import os
import json
import psycopg2
from psycopg2.extras import execute_values


class PGVectorLoader:
    def __init__(self):
        self.conn = psycopg2.connect(                               # DB 연결 초기화
            host=os.getenv("POSTGRES_HOST", "localhost"),           # DB 호스트
            port=os.getenv("POSTGRES_PORT", "5432"),                # 포트 번호
            dbname=os.getenv("POSTGRES_DB", "chatbot"),             # DB 이름
            user=os.getenv("POSTGRES_USER", "chatbot"),             # DB 사용자명
            password=os.getenv("POSTGRES_PASSWORD", "chatbot"),     # DB 비밀번호
        )
        self.conn.autocommit = False                                # 자동 커밋 해제

    def close(self):                                                # DB 연결 종료
        self.conn.close()

    def ensure_tables(self):                                        # DB 스키마 준비 함수
        with self.conn.cursor() as cur:
            cur.execute("""                     
            CREATE EXTENSION IF NOT EXISTS vector;                  
            """)                                                    # VECTOR(1024) 타입을 쓰려면 PostgreSQL에 vector extension이 설치되어 있어야 하므로 활성화

            cur.execute("""                                         
            CREATE TABLE IF NOT EXISTS chunks (
                id BIGSERIAL PRIMARY KEY,
                chunk_id TEXT NOT NULL UNIQUE,
                doc_id TEXT NOT NULL,
                chunk_index INT NOT NULL,
                source_type TEXT,
                title TEXT,
                source_url TEXT,
                published_at TEXT,
                department TEXT,
                category_lv1 TEXT,
                category_lv2 TEXT,
                content TEXT NOT NULL,
                content_length INT,
                content_hash TEXT,
                version INT,
                metadata JSONB,
                created_at TIMESTAMP NOT NULL DEFAULT NOW()
            );
            """)                                                    # chunk 메타데이터 테이블 생성
            """
            chunks 테이블과 chunk_embeddings를 분리 이유
            메타 조회와 벡터 관리가 분리됨
            벡터 모델 교체/재적재 관리에 유리할 수 있음
            정규화된 구조가 됨
            """
            cur.execute("""
            CREATE TABLE IF NOT EXISTS chunk_embeddings (
                chunk_id TEXT PRIMARY KEY,
                embedding VECTOR(1024),
                model_name TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT fk_embedding_chunk
                    FOREIGN KEY (chunk_id)
                    REFERENCES chunks(chunk_id)
                    ON DELETE CASCADE
            );
            """)

            self.conn.commit()

    def upsert_chunks(self, chunks: list[dict]):                    # chunks 테이블에 저장
        rows = []
        for chunk in chunks:
            metadata = {                                            # 일부 메타데이터 JSON형태로 한번 묶어서 저장
                "source_type": chunk.get("source_type"),
                "title": chunk.get("title"),
                "source_url": chunk.get("source_url"),
                "published_at": chunk.get("published_at"),
                "department": chunk.get("department"),
                "category_lv1": chunk.get("category_lv1"),
                "category_lv2": chunk.get("category_lv2"),
                "version": chunk.get("version"),
            }

            rows.append((                                           # 실제 INSERT에 들어갈 튜플
                chunk["chunk_id"],
                chunk["doc_id"],
                chunk["chunk_index"],
                chunk.get("source_type"),
                chunk.get("title"),
                chunk.get("source_url"),
                chunk.get("published_at"),
                chunk.get("department"),
                chunk.get("category_lv1"),
                chunk.get("category_lv2"),
                chunk["content"],
                chunk.get("content_length"),
                chunk.get("content_hash"),
                chunk.get("version"),
                json.dumps(metadata, ensure_ascii=False),
            ))

        with self.conn.cursor() as cur:                             # INSERT하는 배치 삽입 함수
            execute_values(
                cur,
                """
                INSERT INTO chunks (
                    chunk_id, doc_id, chunk_index,
                    source_type, title, source_url, published_at,
                    department, category_lv1, category_lv2,
                    content, content_length, content_hash, version, metadata
                )
                VALUES %s
                ON CONFLICT (chunk_id) DO UPDATE SET
                    doc_id = EXCLUDED.doc_id,
                    chunk_index = EXCLUDED.chunk_index,
                    source_type = EXCLUDED.source_type,
                    title = EXCLUDED.title,
                    source_url = EXCLUDED.source_url,
                    published_at = EXCLUDED.published_at,
                    department = EXCLUDED.department,
                    category_lv1 = EXCLUDED.category_lv1,
                    category_lv2 = EXCLUDED.category_lv2,
                    content = EXCLUDED.content,
                    content_length = EXCLUDED.content_length,
                    content_hash = EXCLUDED.content_hash,
                    version = EXCLUDED.version,
                    metadata = EXCLUDED.metadata
                """,
                rows,
            )                                                           #같은 chunk_id 처음 보면 insert, 이미 있으면 내용 덮어쓰기
            self.conn.commit()

    def upsert_embeddings(self, embedded_chunks: list[dict]):           # chunk_embeddings 테이블에 저장
        with self.conn.cursor() as cur:
            for chunk in embedded_chunks:                               # 임베딩이 포함된 chunk dict들을 하나씩 순회
                vector_str = "[" + ",".join(str(x) for x in chunk["embedding"]) + "]"       # Python list를 문자열 형태의 vector 표현으로 바꾼다.
                                                                                            # ex) [0.1, -0.2, 0.3] -> "[0.1,-0.2,0.3]"
                cur.execute(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, embedding, model_name)
                    VALUES (%s, %s::vector, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        model_name = EXCLUDED.model_name
                    """,
                    (
                        chunk["chunk_id"],                              # 어떤 chunk인지
                        vector_str,                                     # 벡터 값
                        chunk["embedding_model"],                       # 어떤 모델인지
                    ),
                )

            self.conn.commit()