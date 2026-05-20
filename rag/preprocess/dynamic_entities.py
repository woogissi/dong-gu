"""DB-backed entity alias extraction for university RAG queries.

The static dictionary remains the source of truth. This module adds a small,
cached layer from the current corpus so newly crawled departments, buildings,
boards, and site paths can participate in query preprocessing without code
changes.
"""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict
from urllib.parse import urlparse

try:  # pragma: no cover - covered through fallback behavior in unit tests
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:  # pragma: no cover
    psycopg2 = None
    RealDictCursor = None

from rag.preprocess.domain_knowledge import DOMAIN_BLACKLIST

_DB_URL_ENV_VAR = "DATABASE_URL"
_ENABLE_ENV_VAR = "RAG_DYNAMIC_ENTITY_ALIASES"
_TTL_ENV_VAR = "RAG_DYNAMIC_ENTITY_ALIAS_TTL_SECONDS"
_LIMIT_ENV_VAR = "RAG_DYNAMIC_ENTITY_ALIAS_LIMIT"
_DEFAULT_TTL_SECONDS = 1800
_DEFAULT_LIMIT = 800

_ENTITY_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9]+(?:학과|학부|전공|대학|대학원|처|팀|센터|관|전|원|실|부|게시판)"
)
_BUILDING_PATTERN = re.compile(r"(?:제?\d+효민생활관|[가-힣A-Za-z0-9]{2,12}(?:관|전|센터|라운지))")
_BOARD_PATH_PATTERN = re.compile(r"([a-z0-9-]*(?:notice|board|bbs|qna|faq|archive|reference|scholarship|job)[a-z0-9-]*)")

_BLACKLIST = {
    *DOMAIN_BLACKLIST,
    "본문",
    "내용",
    "첨부",
    "파일",
    "관리자",
    "대학교",
    "동의대학교",
    "동의대",
    "게시판",
    "공지사항",
    "공지",
    "상세보기",
}

_BLACKLIST.update({"board", "boardlist", "boardlistcategory", "bbs", "notice", "main", "sub", "view"})

_CACHE: tuple[float, dict[str, list[str]]] | None = None


def get_dynamic_entity_aliases() -> dict[str, list[str]]:
    """Return cached aliases extracted from the corpus DB.

    Fail closed: if DB access is unavailable, return an empty dict. This keeps
    local unit tests and non-DB deployments deterministic.
    """

    global _CACHE
    if os.getenv(_ENABLE_ENV_VAR, "1").strip().lower() in {"0", "false", "no", "off"}:
        return {}
    now = time.time()
    ttl = _int_env(_TTL_ENV_VAR, _DEFAULT_TTL_SECONDS)
    if _CACHE is not None and now - _CACHE[0] < ttl:
        return _CACHE[1]
    aliases = _load_aliases_from_db()
    _CACHE = (now, aliases)
    return aliases


def clear_dynamic_entity_alias_cache() -> None:
    global _CACHE
    _CACHE = None


def build_aliases_from_rows(rows: list[dict]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        title = str(row.get("title") or "")
        department = str(row.get("department") or "")
        source_type = str(row.get("source_type") or "")
        source_url = str(row.get("source_url") or "")

        for value in _title_entities(title):
            grouped[value].update(_aliases_for_entity(value))
        for value in _department_entities(department):
            grouped[value].update(_aliases_for_entity(value))
        for value in _building_entities(f"{title} {department}"):
            grouped[value].update(_aliases_for_entity(value))
        for value in _url_path_entities(source_url):
            grouped[value].add(value.replace("-", " "))
        if source_type and _is_safe_entity(source_type):
            grouped[source_type].add(source_type.replace("_", " "))

    return {
        canonical: sorted(alias for alias in aliases if alias and alias != canonical)
        for canonical, aliases in sorted(grouped.items())
        if _is_safe_entity(canonical)
    }


def _load_aliases_from_db() -> dict[str, list[str]]:
    if psycopg2 is None or RealDictCursor is None:
        return {}
    try:
        with _open_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SET statement_timeout = '2500ms';"
                )
                cur.execute(
                    """
                    SELECT title, department, source_type, source_url
                    FROM documents
                    WHERE title IS NOT NULL
                    ORDER BY db_updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    (_int_env(_LIMIT_ENV_VAR, _DEFAULT_LIMIT),),
                )
                return build_aliases_from_rows([dict(row) for row in cur.fetchall()])
    except Exception:
        return {}


def _open_connection():
    database_url = os.getenv(_DB_URL_ENV_VAR, "").strip()
    if database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql://", 1)
    if database_url:
        return psycopg2.connect(database_url, connect_timeout=3)
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "chatbot"),
        user=os.getenv("POSTGRES_USER", "chatbot"),
        password=os.getenv("POSTGRES_PASSWORD", "chatbot"),
        connect_timeout=3,
    )


def _title_entities(title: str) -> list[str]:
    parts = re.split(r"\s*[|>]\s*|\s+-\s+", title)
    candidates = []
    for part in parts:
        text = _clean_entity(part)
        if _is_safe_title_entity(text):
            candidates.append(text)
        candidates.extend(_ENTITY_PATTERN.findall(part))
    return _ordered_unique(candidates)


def _department_entities(department: str) -> list[str]:
    return [value for value in [_clean_entity(department), *_ENTITY_PATTERN.findall(department)] if _is_safe_entity(value)]


def _building_entities(text: str) -> list[str]:
    return [value for value in _BUILDING_PATTERN.findall(text) if _is_safe_entity(value)]


def _url_path_entities(source_url: str) -> list[str]:
    if not source_url:
        return []
    parsed = urlparse(source_url)
    path = parsed.path or ""
    values = []
    for segment in path.split("/"):
        segment = segment.strip().lower()
        if not segment:
            continue
        match = _BOARD_PATH_PATTERN.search(segment)
        if match:
            values.append(match.group(1))
    host = (parsed.hostname or "").split(".")[0]
    if host and _is_safe_entity(host):
        values.append(host)
    return _ordered_unique(values)


def _aliases_for_entity(value: str) -> set[str]:
    aliases: set[str] = set()
    if value.endswith("학과"):
        aliases.add(value.removesuffix("학과"))
        aliases.add(value.removesuffix("과"))
    if value.endswith("학부"):
        aliases.add(value.removesuffix("학부"))
    if value.endswith("전공"):
        aliases.add(value.removesuffix("전공"))
    if value.endswith("관"):
        aliases.add(value.removesuffix("관"))
    if value.endswith("센터"):
        aliases.add(value.removesuffix("센터"))
    if value == "컴퓨터공학과":
        aliases.update({"컴공", "computer", "computer engineering"})
    return {alias for alias in aliases if _is_safe_entity(alias)}


def _clean_entity(value: str) -> str:
    text = re.sub(r"\[[^\]]+\]|\([^)]+\)", " ", value or "")
    text = re.sub(r"[^0-9A-Za-z가-힣\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_safe_entity(value: str) -> bool:
    text = (value or "").strip()
    if len(text) < 2:
        return False
    if text in _BLACKLIST:
        return False
    if text.casefold() in _BLACKLIST:
        return False
    if re.fullmatch(r"[A-Za-z]+", text) and len(text) < 3:
        return False
    if text.isdigit():
        return False
    return True


def _is_safe_title_entity(value: str) -> bool:
    if not _is_safe_entity(value):
        return False
    if len(value) > 24:
        return False
    if re.search(r"\d{4}년|\d+월|\d+일|개최|모집|안내|신청|공고|콘테스트|패치", value):
        return False
    return bool(_ENTITY_PATTERN.fullmatch(value) or _BUILDING_PATTERN.fullmatch(value))


def _ordered_unique(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default
