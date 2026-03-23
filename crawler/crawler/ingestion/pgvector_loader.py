# crawler/ingestion/pgvector_loader.py

import os
import json
import psycopg2
from psycopg2.extras import execute_values


class PGVectorLoader:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "chatbot"),
            user=os.getenv("POSTGRES_USER", "chatbot"),
            password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
        )
        self.conn.autocommit = False

    def close(self):
        self.conn.close()

    def ensure_tables(self):
        with self.conn.cursor() as cur:
            cur.execute("""
            CREATE EXTENSION IF NOT EXISTS vector;
            """)

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
            """)

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

    def upsert_chunks(self, chunks: list[dict]):
        rows = []
        for chunk in chunks:
            metadata = {
                "source_type": chunk.get("source_type"),
                "title": chunk.get("title"),
                "source_url": chunk.get("source_url"),
                "published_at": chunk.get("published_at"),
                "department": chunk.get("department"),
                "category_lv1": chunk.get("category_lv1"),
                "category_lv2": chunk.get("category_lv2"),
                "version": chunk.get("version"),
            }

            rows.append((
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

        with self.conn.cursor() as cur:
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
            )
            self.conn.commit()

    def upsert_embeddings(self, embedded_chunks: list[dict]):
        with self.conn.cursor() as cur:
            for chunk in embedded_chunks:
                vector_str = "[" + ",".join(str(x) for x in chunk["embedding"]) + "]"

                cur.execute(
                    """
                    INSERT INTO chunk_embeddings (chunk_id, embedding, model_name)
                    VALUES (%s, %s::vector, %s)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        embedding = EXCLUDED.embedding,
                        model_name = EXCLUDED.model_name
                    """,
                    (
                        chunk["chunk_id"],
                        vector_str,
                        chunk["embedding_model"],
                    ),
                )

            self.conn.commit()