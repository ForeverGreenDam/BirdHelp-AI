"""ChromaDB 向量存储管理 — 用户粒度的集合隔离、增删、检索。

每个用户一个独立 collection，命名规则: rag_user_{user_id}。
"""

from langchain_community.vectorstores import Chroma

from config import settings
from core.embedding import create_embeddings


def _collection_name(user_id: str) -> str:
    return f"rag_user_{user_id}"


def get_vectorstore(user_id: str) -> Chroma:
    """获取用户专属的 Chroma 向量存储实例（懒加载）。"""
    return Chroma(
        collection_name=_collection_name(user_id),
        embedding_function=create_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )


def add_documents(user_id: str, docs: list) -> list[str]:
    """将 LangChain Document 列表嵌入并写入向量库，返回 ID 列表。"""
    store = get_vectorstore(user_id)
    return store.add_documents(docs)


def delete_by_material(user_id: str, material_id: int) -> int:
    """按 material_id 删除该素材对应的所有 chunk。返回删除数量。"""
    store = get_vectorstore(user_id)
    results = store.get(where={"material_id": material_id})
    if results and results["ids"]:
        store.delete(ids=results["ids"])
        return len(results["ids"])
    return 0


def get_all_documents(user_id: str) -> list:
    """获取用户全部已入库文档（用于构建 BM25 索引等场景）。"""
    from langchain_core.documents import Document

    store = get_vectorstore(user_id)
    raw = store.get(include=["documents", "metadatas"])
    docs = []
    for content, meta in zip(raw.get("documents", []), raw.get("metadatas", [])):
        docs.append(Document(page_content=content, metadata=meta))
    return docs
