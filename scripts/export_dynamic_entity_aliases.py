from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env()
    from rag.preprocess.dynamic_entities import clear_dynamic_entity_alias_cache, get_dynamic_entity_aliases

    clear_dynamic_entity_alias_cache()
    aliases = get_dynamic_entity_aliases()
    print(json.dumps(aliases, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"\ncount={len(aliases)}")


if __name__ == "__main__":
    main()
