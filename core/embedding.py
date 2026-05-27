"""Embedding 工厂，统一创建嵌入模型客户端实例。

嵌入模型必须固定——同一 RAG 系统的向量必须由同一模型产出。
所有配置从 .env 读取（embedding_model / embedding_api_key / embedding_base_url），
embedding_api_key / embedding_base_url 为空时自动回退到大模型对应字段。
"""

from langchain_openai import OpenAIEmbeddings

from config import settings


def create_embeddings() -> OpenAIEmbeddings:
    """基于 .env 配置创建 OpenAIEmbeddings 实例。

    embedding_api_key / embedding_base_url 为空时
    自动回退到 llm_api_key / llm_base_url。
    """
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.effective_embedding_api_key,
        base_url=settings.effective_embedding_base_url,
        dimensions=settings.embedding_dimension,
        check_embedding_ctx_length=False,
    )
