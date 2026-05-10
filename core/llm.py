"""ChatModel 工厂，统一创建 LLM 客户端实例。"""

from langchain_openai import ChatOpenAI

from config import settings


def create_chat_model() -> ChatOpenAI:
    """基于全局配置创建 ChatOpenAI 实例。

    兼容 DeepSeek/通义千问/GPT-4o 等 OpenAI 兼容 API。
    """
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout,
    )
