from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DATA_DIR = PACKAGE_DIR / "data"
HF_CACHE_DIR = PACKAGE_DIR / ".hf_cache"

RAW_DIR = DATA_DIR / "raw"
RAW_HTML_DIR = RAW_DIR / "html"
RAW_DOC_DIR = RAW_DIR / "documents"
RAW_ATTACH_DIR = RAW_DIR / "attachments"
RAW_FILE_DIR = RAW_DIR / "files"

CURATED_DOC_DIR = DATA_DIR / "curated" / "documents"
CHUNK_DIR = DATA_DIR / "rag_ready" / "chunks"
LOG_DIR = DATA_DIR / "logs"
MANIFEST_DIR = DATA_DIR / "manifest"


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
