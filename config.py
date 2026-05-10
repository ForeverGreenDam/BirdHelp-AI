from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── 服务 ──
    app_name: str = "BirdHelp-AI"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Java 后端 ──
    java_base_url: str = ""
    java_api_prefix: str = "/api"
    java_private_key_b64: str = ""
    java_sign_timeout_seconds: int = 300

    # ── 大模型 ──
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.7
    llm_max_retries: int = 3
    llm_timeout: int = 120

    # ── 嵌入模型 ──
    embedding_model: str = "text-embedding-3-small"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimension: int = 1536

    # ── 向量数据库 ──
    vector_store: str = "chromadb"
    chroma_persist_dir: str = "./chroma_data"
    milvus_host: str = ""
    milvus_port: int = 19530

    # ── RAG ──
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5
    retrieval_mode: str = "hybrid"

    # ── Redis ──
    redis_url: str = ""
    celery_broker_url: str = ""
    celery_result_backend: str = ""

    # ── 文件 ──
    temp_dir: str = "/tmp/birdhelp"
    max_upload_size_mb: int = 20

    # ── 语音 ──
    whisper_model: str = "whisper-1"
    whisper_api_key: str = ""

    # ── OCR ──
    paddleocr_lang: str = "ch"

    # ── LangSmith (可选) ──
    langsmith_api_key: str = ""
    langsmith_project: str = "BirdHelp-AI"

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.llm_base_url

    @property
    def effective_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.llm_api_key

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


settings = Settings()
