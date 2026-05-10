from langchain_openai import ChatOpenAI

from config import settings


def create_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout,
    )
