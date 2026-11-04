"""Chroma 向量库适配。

集合按“检索块”存储，metadata 同时保存空间、版本、类型与适用范围，
因此 Case 可以跨空间检索，并且在查询时用 document_version_id 白名单
限制到 Case 固定引用的版本。

每个索引配置版本（嵌入模型/维度/分块/分词器/融合策略指纹）使用一个独立
集合。这样切换 256 维本地向量与 1024 维云端向量时不会触发 Chroma 的
维度冲突，旧集合也不会再被查询。

嵌入向量由 services.embedding 计算后显式传入，Chroma 只负责持久化与
相似度查询，避免 Chroma 内部再调用外部模型。
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, List, Optional, Sequence

from core.config import get_settings


class VectorStoreError(RuntimeError):
    pass


_client = None
_collections: Dict[str, Any] = {}
_lock = threading.RLock()
_store_signature: Optional[tuple[str, str]] = None


def _import_chromadb():
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError as exc:  # pragma: no cover — 依赖缺失
        raise VectorStoreError(f"未安装 chromadb：{exc}") from exc
    return chromadb, ChromaSettings


def get_client():
    global _client, _store_signature
    settings = get_settings()
    signature = (str(settings.chroma_persist_dir), settings.chroma_collection)
    with _lock:
        if _client is not None and _store_signature == signature:
            return _client
        chromadb, ChromaSettings = _import_chromadb()
        try:
            _client = chromadb.PersistentClient(
                path=str(settings.chroma_persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"无法打开 Chroma 持久化目录：{exc}") from exc
        _collections.clear()
        _store_signature = signature
        return _client


def _current_index_version() -> str:
    from services.index_config import get_index_config

    return get_index_config().index_version


def collection_name(index_version: Optional[str] = None) -> str:
    base = get_settings().chroma_collection
    version = index_version or _current_index_version()
    suffix = version.replace("-", "_")
    return f"{base}_{suffix}"


def get_collection(index_version: Optional[str] = None):
    version = index_version or _current_index_version()
    name = collection_name(version)
    with _lock:
        cached = _collections.get(name)
        if cached is not None:
            return cached
        client = get_client()
        try:
            collection = client.get_or_create_collection(
                name=name,
                configuration={"hnsw": {"space": "cosine"}},
                metadata={
                    "description": "EvidenceDesk retrieval chunks",
                    "index_version": version,
                },
            )
        except Exception as exc:  # noqa: BLE001
            raise VectorStoreError(f"无法创建 Chroma 集合：{exc}") from exc
        _collections[name] = collection
        return collection


def reset_store() -> None:
    """测试或切换持久化目录时重置进程内句柄。"""
    global _client, _store_signature
    with _lock:
        _client = None
        _collections.clear()
        _store_signature = None


def upsert_chunks(
    *,
    index_version: str,
    entries: Sequence[Dict[str, Any]],
    embeddings: Sequence[Sequence[float]],
) -> None:
    if not entries:
        return
    collection = get_collection(index_version)
    ids = [entry["id"] for entry in entries]
    documents = [entry["text"] for entry in entries]
    metadatas = [entry["metadata"] for entry in entries]
    try:
        with _lock:
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=[list(vector) for vector in embeddings],
                metadatas=metadatas,
            )
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"写入向量索引失败：{exc}") from exc


def delete_version(
    document_version_id: str, *, index_version: Optional[str] = None
) -> None:
    collection = get_collection(index_version)
    try:
        with _lock:
            collection.delete(where={"document_version_id": document_version_id})
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"删除向量索引失败：{exc}") from exc


def query(
    *,
    index_version: str,
    document_version_ids: Iterable[str],
    embedding: Sequence[float],
    n_results: int,
) -> List[Dict[str, Any]]:
    version_ids = [value for value in document_version_ids if value]
    if not version_ids or n_results <= 0:
        return []
    collection = get_collection(index_version)
    where = {"document_version_id": {"$in": version_ids}}
    try:
        with _lock:
            result = collection.query(
                query_embeddings=[list(embedding)],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"向量检索失败：{exc}") from exc

    ids = (result.get("ids") or [[]])[0]
    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    hits: List[Dict[str, Any]] = []
    for position, chunk_id in enumerate(ids):
        metadata = metadatas[position] if position < len(metadatas) else {}
        distance = float(distances[position]) if position < len(distances) else 1.0
        hits.append(
            {
                "chunk_id": chunk_id,
                "text": documents[position] if position < len(documents) else None,
                "metadata": metadata or {},
                "distance": distance,
                # cosine 距离转相似度
                "similarity": max(-1.0, min(1.0, 1.0 - distance)),
            }
        )
    return hits


def count(index_version: Optional[str] = None) -> int:
    version = index_version or _current_index_version()
    collection = get_collection(version)
    try:
        return int(collection.count())
    except Exception as exc:  # noqa: BLE001
        raise VectorStoreError(f"读取索引统计失败：{exc}") from exc
