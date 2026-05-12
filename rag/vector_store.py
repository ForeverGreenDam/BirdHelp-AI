"""Redis Stack 向量存储管理 — 用户粒度索引隔离。

每个用户独立 Redis FT.INDEX: rag_user_{user_id}。
"""

from __future__ import annotations

from langchain_core.documents import Document
from redis import Redis as RedisClient

from config import settings
from core.embedding import create_embeddings


# ═══════════════════════════════════════════════════════════════════════════════
# 命名规则
# ═══════════════════════════════════════════════════════════════════════════════

def _index_name(user_id: str) -> str:
    return f"rag_user_{user_id}"


# ═══════════════════════════════════════════════════════════════════════════════
# Redis 连接（全局单例）
# ═══════════════════════════════════════════════════════════════════════════════

_redis_client: RedisClient | None = None


def _get_redis() -> RedisClient:
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            decode_responses=False,
        )
    return _redis_client


# ═══════════════════════════════════════════════════════════════════════════════
# 索引 schema（material_id 作为 TAG 字段以支持按素材删除）
# ═══════════════════════════════════════════════════════════════════════════════

_INDEX_SCHEMA = {
    "tag": [{"name": "material_id"}],
}


def get_vectorstore(user_id: str):
    """获取用户专属的 Redis 向量存储实例。"""
    from langchain_community.vectorstores.redis import Redis

    return Redis(
        redis_client=_get_redis(),
        index_name=_index_name(user_id),
        embedding=create_embeddings(),
        index_schema=_INDEX_SCHEMA,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CRUD 操作
# ═══════════════════════════════════════════════════════════════════════════════

def add_documents(user_id: str, docs: list) -> list[str]:
    """嵌入文档列表并写入向量库，返回 ID 列表。"""
    store = get_vectorstore(user_id)
    return store.add_documents(docs)


def delete_by_material(user_id: str, material_id: int) -> int:
    """按 material_id 删除该素材对应的所有 chunk。返回删除数量。"""
    from redis.commands.search.query import Query

    r = _get_redis()
    index_name = _index_name(user_id)
    try:
        results = r.ft(index_name).search(
            Query(f"@material_id:{{{material_id}}}")
        )
    except Exception:
        return 0
    doc_ids = [doc.id for doc in results.docs]
    if doc_ids:
        r.delete(*doc_ids)
    return len(doc_ids)


def get_all_documents(user_id: str) -> list[Document]:
    """获取用户全部已入库文档（用于构建 BM25 索引）。"""
    r = _get_redis()
    index_name = _index_name(user_id)
    docs: list[Document] = []
    for key in r.scan_iter(match=f"{index_name}:*", count=100):
        raw = r.hgetall(key)
        if not raw:
            continue
        data = {
            (k.decode("utf-8") if isinstance(k, bytes) else k): (
                v.decode("utf-8") if isinstance(v, bytes) else v
            )
            for k, v in raw.items()
        }
        content = data.pop("content", "")
        data.pop("content_vector", None)
        docs.append(Document(page_content=content, metadata=data))
    return docs
