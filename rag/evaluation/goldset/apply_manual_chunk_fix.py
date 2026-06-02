"""수동 보정 청크 적재 + 재임베딩 인프라.

깨진 청크(이수표 OCR/PDF 손상 등)를 사람이 검증한 정확한 텍스트로 교체하고
KoE5로 재임베딩한다. 검색 임베딩과 동일 모델(nlpai-lab/KoE5)을 사용해 정합성을 유지한다.

- chunks.content / content_length / content_hash 갱신
- chunk_embeddings.embedding 재계산 (model_name=nlpai-lab/KoE5)
- chunks.metadata에 manual_override 플래그 기록 (재크롤링 덮어쓰기 보호용 표식)

입력 JSON 형식:
  [{"chunk_id": "...", "content": "정확한 텍스트", "note": "선택"}, ...]

실행(기본 dry-run):
  docker compose run --rm rag python -m rag.evaluation.goldset.apply_manual_chunk_fix --input fixes.json
  docker compose run --rm rag python -m rag.evaluation.goldset.apply_manual_chunk_fix --input fixes.json --execute
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import DictCursor, Json

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "nlpai-lab/KoE5")


def _dsn() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url.replace("postgresql+psycopg2://", "postgresql://")
    return (
        f"postgresql://{os.getenv('POSTGRES_USER','chatbot')}:{os.getenv('POSTGRES_PASSWORD','chatbot')}"
        f"@{os.getenv('POSTGRES_HOST','postgres')}:{os.getenv('POSTGRES_PORT','5432')}/{os.getenv('POSTGRES_DB','chatbot')}"
    )


def _to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def main() -> None:
    parser = argparse.ArgumentParser(description="수동 보정 청크 적재 + 재임베딩")
    parser.add_argument("--input", required=True, help="보정 청크 JSON 파일 경로")
    parser.add_argument("--execute", action="store_true", help="실제 DB 반영 (기본 dry-run)")
    args = parser.parse_args()

    fixes = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if isinstance(fixes, dict):
        fixes = [fixes]
    print(f"[fix] 보정 대상 청크: {len(fixes)}개 | execute={args.execute}")

    conn = psycopg2.connect(_dsn())
    conn.autocommit = False

    # 대상 청크 사전 검증
    valid = []
    with conn.cursor(cursor_factory=DictCursor) as cur:
        for fix in fixes:
            chunk_id = fix.get("chunk_id")
            content = fix.get("content")
            if not chunk_id or not content:
                print(f"  [skip] chunk_id/content 누락: {fix}")
                continue
            cur.execute("SELECT doc_id, content_length, metadata FROM chunks WHERE chunk_id=%s", (chunk_id,))
            row = cur.fetchone()
            if row:
                cur.execute("SELECT 1 FROM chunk_embeddings WHERE chunk_id=%s AND model_name=%s", (chunk_id, _MODEL_NAME))
                has_emb = cur.fetchone() is not None
                valid.append({"mode": "update", "fix": fix, "has_emb": has_emb})
                print(f"  [update] {chunk_id} (doc={row['doc_id']}) old_len={row['content_length']} "
                      f"new_len={len(content)} emb_exists={has_emb}")
                continue
            # 신규 청크 INSERT: 같은 doc의 기존 청크에서 버전 메타 복사 (검색 latest 필터 정합)
            doc_id = fix.get("doc_id")
            if not doc_id:
                print(f"  [skip] 미존재 chunk_id이고 doc_id도 없음(INSERT 불가): {chunk_id}")
                continue
            cur.execute(
                """
                SELECT document_version_id, content_id, max(chunk_index) OVER () AS max_idx
                FROM chunks WHERE doc_id=%s ORDER BY chunk_index LIMIT 1
                """,
                (doc_id,),
            )
            meta_row = cur.fetchone()
            if not meta_row:
                print(f"  [skip] doc_id에 기존 청크 없음(버전 메타 복사 불가): {doc_id}")
                continue
            valid.append({
                "mode": "insert", "fix": fix,
                "document_version_id": meta_row["document_version_id"],
                "content_id": meta_row["content_id"],
                "next_index": (meta_row["max_idx"] or 0) + 1,
            })
            print(f"  [insert] {chunk_id} (doc={doc_id}) new_len={len(content)} "
                  f"ver={meta_row['document_version_id']} idx={(meta_row['max_idx'] or 0) + 1}")

    if not valid:
        print("[fix] 반영할 유효 청크 없음. 종료.")
        return

    if not args.execute:
        print("\n[dry-run] --execute 없이 실행됨. DB 변경 없음.")
        print("위 [ok] 청크들이 새 content로 교체되고 재임베딩됩니다.")
        return

    print("\n[fix] 임베더 초기화 중 (KoE5)...")
    from rag.embedding.koe5_embedder import KoE5Embedder
    embedder = KoE5Embedder()

    ts = datetime.now(timezone.utc).isoformat()
    n_update = n_insert = 0
    with conn.cursor(cursor_factory=DictCursor) as cur:
        for item in valid:
            fix = item["fix"]
            chunk_id = fix["chunk_id"]
            content = fix["content"]
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            override_meta = {
                "manual_override": True,
                "manual_override_at": ts,
                "manual_override_note": fix.get("note", ""),
            }
            vec = embedder.embed_text(content)
            pgvec = _to_pgvector(vec)

            if item["mode"] == "update":
                cur.execute(
                    """
                    UPDATE chunks
                    SET content=%s, content_length=%s, content_hash=%s,
                        metadata = coalesce(metadata, '{}'::jsonb) || %s::jsonb,
                        updated_at = now()
                    WHERE chunk_id=%s
                    """,
                    (content, len(content), content_hash, Json(override_meta), chunk_id),
                )
                if item["has_emb"]:
                    cur.execute(
                        "UPDATE chunk_embeddings SET embedding=%s::vector, updated_at=now() "
                        "WHERE chunk_id=%s AND model_name=%s",
                        (pgvec, chunk_id, _MODEL_NAME),
                    )
                else:
                    cur.execute(
                        "INSERT INTO chunk_embeddings (chunk_id, embedding, model_name) VALUES (%s, %s::vector, %s)",
                        (chunk_id, pgvec, _MODEL_NAME),
                    )
                n_update += 1
                print(f"  [updated] {chunk_id} (재임베딩 dim={len(vec)})")
            else:  # insert
                cur.execute(
                    """
                    INSERT INTO chunks
                        (chunk_id, doc_id, document_version_id, content_id, chunk_index,
                         section_type, content, content_length, content_hash, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 'attachment', %s, %s, %s, %s::jsonb, now(), now())
                    """,
                    (chunk_id, fix["doc_id"], item["document_version_id"], item["content_id"],
                     item["next_index"], content, len(content), content_hash, Json(override_meta)),
                )
                cur.execute(
                    "INSERT INTO chunk_embeddings (chunk_id, embedding, model_name) VALUES (%s, %s::vector, %s)",
                    (chunk_id, pgvec, _MODEL_NAME),
                )
                n_insert += 1
                print(f"  [inserted] {chunk_id} (재임베딩 dim={len(vec)})")

    conn.commit()
    print(f"\n[fix] 완료: 갱신 {n_update}개 + 신규 {n_insert}개. 재임베딩 + manual_override 기록됨.")


if __name__ == "__main__":
    main()
