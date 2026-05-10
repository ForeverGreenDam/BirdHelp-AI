"""RAG 混合检索器 — 向量检索 + BM25 关键词检索 → RRF 融合。

结合 MultiQueryRetriever 自动改写用户查询，提升召回率。
"""

from typing import Any

from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers.multi_query import MultiQueryRetriever
from langchain_core.documents import Document
from loguru import logger

from config import settings
from core.llm import create_chat_model
from rag.vector_store import get_vectorstore, get_all_documents


def _build_ensemble(user_id: str, k: int | None = None) -> EnsembleRetriever:
    """构建向量 + BM25 混合检索器（RRF 融合）。

    每次调用都会用 ChromaDB 中的最新文档重建 BM25 索引。
    """
    top_k = k or settings.retrieval_top_k

    # 向量检索器
    vectorstore = get_vectorstore(user_id)
    vector_retriever = vectorstore.as_retriever(search_kwargs={"k": top_k * 2})

    # BM25 关键词检索器（从 ChromaDB 加载全部文档构建索引）
    all_docs = get_all_documents(user_id)
    if not all_docs:
        logger.warning(f"User {user_id} has no indexed documents, fallback to vector only")
        return EnsembleRetriever(
            retrievers=[vector_retriever],
            weights=[1.0],
        )

    bm25_retriever = BM25Retriever.from_documents(all_docs)
    bm25_retriever.k = top_k * 2

    return EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[0.5, 0.5],
    )


async def retrieve(
    user_id: str,
    query: str,
    top_k: int | None = None,
    use_multiquery: bool = True,
) -> list[Document]:
    """执行混合检索，返回去重排序后的文档列表。

    Args:
        user_id: 用户 ID，用于隔离向量库
        query: 用户原始查询
        top_k: 返回文档数量，默认取配置值
        use_multiquery: 是否启用 MultiQuery 改写（默认开启）
    """
    k = top_k or settings.retrieval_top_k
    ensemble = _build_ensemble(user_id, k)

    if use_multiquery:
        llm = create_chat_model()
        retriever = MultiQueryRetriever.from_llm(
            retriever=ensemble,
            llm=llm,
        )
    else:
        retriever = ensemble

    docs: list[Document] = await retriever.ainvoke(query)
    # 去重（按 page_content 内容）
    seen = set()
    unique: list[Document] = []
    for d in docs:
        key = d.page_content[:120]
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique[:k]


async def retrieve_formatted(
    user_id: str,
    query: str,
    top_k: int | None = None,
) -> str:
    """检索并格式化为 Prompt 可注入的 context 文本。"""
    docs = await retrieve(user_id, query, top_k)
    if not docs:
        return ""

    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        src = doc.metadata.get("file_name", "未知来源")
        parts.append(f"[参考片段 {i} | 来源: {src}]\n{doc.page_content}")
    return "\n\n".join(parts)
