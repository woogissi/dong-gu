"""Cross-encoder 재랭킹 신호 (Tier 3).

규칙 기반 reranker(`rag/selection/reranker.py`)가 풀지 못하는 **의미 불일치** 케이스
(예: 본청 공지가 전과 규정 페이지를 누르는 G064)를 보정하기 위한 cross-encoder 점수를 제공한다.

- 기존 의존성(`sentence-transformers`)만 사용 — 신규 패키지 없음.
- 모델은 `rag_model_cache:/root/.cache` 볼륨에 KoE5와 동일하게 자동 캐싱된다.
- 환경변수 `RAG_CROSS_ENCODER_ENABLED`(기본 0)로 게이팅 — 비활성 시 reranker는 CE 경로를
  완전히 건너뛰어 기존 결정적 동작을 100% 보존한다.
- 모델 로드 실패 시 서비스를 중단하지 않고 graceful degrade(빈 점수 반환)한다.
"""

from __future__ import annotations

import math
import os
from functools import lru_cache
from typing import Any

_DEFAULT_MODEL = "Dongjin-kr/ko-reranker"
_DEFAULT_WEIGHT = 1.5
_DEFAULT_TOP_N = 20

_TRUTHY = {"1", "true", "yes", "on", "y", "t"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def cross_encoder_enabled() -> bool:
    """CE 재랭킹 신호 활성화 여부 (`RAG_CROSS_ENCODER_ENABLED`, 기본 off)."""
    return _env_flag("RAG_CROSS_ENCODER_ENABLED", False)


def cross_encoder_weight() -> float:
    """CE 점수를 규칙신호 합산에 더할 때의 가중치 (`RAG_CROSS_ENCODER_WEIGHT`)."""
    try:
        return float(os.getenv("RAG_CROSS_ENCODER_WEIGHT", str(_DEFAULT_WEIGHT)))
    except (TypeError, ValueError):
        return _DEFAULT_WEIGHT


def cross_encoder_top_n() -> int:
    """CE를 적용할 상위 후보 수 (`RAG_CROSS_ENCODER_TOP_N`)."""
    try:
        value = int(os.getenv("RAG_CROSS_ENCODER_TOP_N", str(_DEFAULT_TOP_N)))
    except (TypeError, ValueError):
        return _DEFAULT_TOP_N
    return value if value > 0 else _DEFAULT_TOP_N


@lru_cache(maxsize=1)
def get_cross_encoder() -> Any | None:
    """CE 모델 지연 싱글톤. 로드 실패 시 None을 반환한다(서비스 중단 금지).

    `CrossEncoder` import 자체를 함수 내부로 미뤄, CE 비활성 경로에서는 무거운
    sentence-transformers 로딩 비용을 전혀 치르지 않는다.
    """
    model_name = os.getenv("RAG_CROSS_ENCODER_MODEL", _DEFAULT_MODEL)
    try:
        from sentence_transformers import CrossEncoder

        print(f"[CrossEncoder] Loading reranker model={model_name} ...")
        model = CrossEncoder(model_name)
        print("[CrossEncoder] Reranker loaded successfully.")
        return model
    except Exception as exc:  # noqa: BLE001 - graceful degrade
        print(f"[CrossEncoder] Failed to load reranker model={model_name}: {exc}")
        return None


def _sigmoid(value: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-value))
    except OverflowError:
        return 0.0 if value < 0 else 1.0


def score_pairs(query: str, texts: list[str]) -> list[float]:
    """(query, text) 쌍을 배치로 1회 스코어링하고 sigmoid로 0~1 정규화해 반환한다.

    CE 비활성/모델 None/빈 입력이면 빈 리스트를 반환한다(호출부에서 no-op).
    `texts`와 동일 길이의 점수 리스트를 보장한다.
    """
    if not query or not query.strip() or not texts:
        return []
    model = get_cross_encoder()
    if model is None:
        return []
    try:
        raw_scores = model.predict([(query, text) for text in texts])
    except Exception as exc:  # noqa: BLE001 - graceful degrade
        print(f"[CrossEncoder] predict failed: {exc}")
        return []
    return [_sigmoid(float(score)) for score in raw_scores]
