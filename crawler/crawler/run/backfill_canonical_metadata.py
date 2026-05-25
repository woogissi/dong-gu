from __future__ import annotations

from crawler.ingestion.pgvector_loader import PGVectorLoader
from crawler.utils.canonical_source import canonical_notice_metadata


def main() -> None:
    loader = PGVectorLoader(autocommit_writes=False)
    updated = 0
    try:
        with loader.conn.cursor() as cur:
            cur.execute(
                """
                SELECT doc_id, title, source_url, source_type, content_hash, metadata
                FROM documents;
                """
            )
            rows = cur.fetchall()

        with loader.conn.cursor() as cur:
            for doc_id, title, source_url, source_type, content_hash, metadata in rows:
                current = metadata if isinstance(metadata, dict) else {}
                canonical = canonical_notice_metadata(
                    {
                        "title": title,
                        "source_url": source_url,
                        "source_type": source_type,
                        "content_hash": content_hash,
                    }
                )
                next_metadata = {**current, **canonical}
                if next_metadata == current:
                    continue
                cur.execute(
                    """
                    UPDATE documents
                    SET metadata = %s,
                        db_updated_at = now()
                    WHERE doc_id = %s;
                    """,
                    (loader._json(next_metadata), doc_id),
                )
                updated += 1
        loader.commit()
        print(f"canonical_metadata_backfill updated={updated}")
    except Exception:
        loader.rollback()
        raise
    finally:
        loader.close()


if __name__ == "__main__":
    main()
