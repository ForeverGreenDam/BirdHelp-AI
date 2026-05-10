from langchain_openai import OpenAIEmbeddings

from config import settings


def create_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.effective_embedding_api_key,
        base_url=settings.effective_embedding_base_url,
        dimensions=settings.embedding_dimension,
    )
