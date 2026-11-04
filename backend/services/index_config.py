"""检索索引配置与版本指纹。

嵌入模型、向量维度、分块策略、分词器或融合策略任一变化，都会产生新的
index_version。旧索引不会被新检索使用，避免“换了模型却混用旧向量”。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict

from core.config import get_settings
from services.tokenizer import TOKENIZER_VERSION

INDEX_SCHEMA_VERSION = "retrieval-index-v1"
CHUNK_STRATEGY = "evidence_span_window_section_v2"
FUSION_STRATEGY = "rrf_v1"


@dataclass(frozen=True)
class IndexConfig:
    index_version: str
    embedding_provider: str
    embedding_model: str
    embedding_dimension: int
    chunk_strategy: str
    chunk_max_chars: int
    chunk_overlap_chars: int
    tokenizer_version: str
    fusion_strategy: str
    schema_version: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_index_config() -> IndexConfig:
    settings = get_settings()
    payload = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "embedding_dimension": settings.embedding_dimension,
        "chunk_strategy": CHUNK_STRATEGY,
        "chunk_max_chars": settings.chunk_max_chars,
        "chunk_overlap_chars": settings.chunk_overlap_chars,
        "tokenizer_version": TOKENIZER_VERSION,
        "fusion_strategy": FUSION_STRATEGY,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return IndexConfig(
        index_version=f"v1-{digest[:12]}",
        **payload,
    )


def get_index_config() -> IndexConfig:
    return build_index_config()
