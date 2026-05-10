"""Embedding 工厂，统一创建嵌入模型客户端实例。"""

from langchain_openai import OpenAIEmbeddings

from config import settings


def create_embeddings() -> OpenAIEmbeddings:
    """基于全局配置创建 OpenAIEmbeddings 实例。

    API key 和 base_url 会自动回退到大模型配置。
    """
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.effective_embedding_api_key,
        base_url=settings.effective_embedding_base_url,
        dimensions=settings.embedding_dimension,
    )
