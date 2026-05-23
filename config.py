"""全局配置，基于 pydantic-settings 从 .env 文件与环境变量加载。"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置聚合类，所有字段可从 .env 或环境变量读取。

    嵌入模型 base_url / api_key 为空时自动回退到 LLM 对应配置。
    """

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
    java_caller_public_key_b64: str = ""

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

    # ── Redis Stack 向量数据库 ──
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""

    # ── RAG ──
    chunk_size: int = 1000
    chunk_overlap: int = 200
    retrieval_top_k: int = 5
    retrieval_mode: str = "hybrid"

    # ── 文件 ──
    temp_dir: str = "/tmp/birdhelp"
    max_upload_size_mb: int = 20

    # ── OCR ──
    paddleocr_lang: str = "ch"

    # ── PPT / Word / PDF 增强生成 ──
    ppt_qa_enabled: bool = True
    ppt_qa_score_threshold: int = 70
    ppt_max_repair_rounds: int = 3
    ppt_image_enabled: bool = True
    ppt_image_source: str = "unsplash"
    ppt_unsplash_access_key: str = ""
    ppt_pexels_api_key: str = ""
    ppt_max_concurrent_slides: int = 4
    # Word/PDF QA 复用 ppt_qa_score_threshold 和 ppt_max_repair_rounds

    # ── RabbitMQ ──
    rabbitmq_host: str = "127.0.0.1"
    rabbitmq_port: int = 5672
    rabbitmq_vhost: str = "/"
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_exchange: str = "birdhelp.doc.generation"
    rabbitmq_queue: str = "birdhelp.doc.generation.tasks"
    rabbitmq_prefetch: int = 1

    # ── LangSmith (可选) ──
    langsmith_api_key: str = ""
    langsmith_project: str = "BirdHelp-AI"

    @property
    def effective_embedding_base_url(self) -> str:
        """嵌入模型 base_url，为空时回退到 llm_base_url。"""
        return self.embedding_base_url or self.llm_base_url

    @property
    def effective_embedding_api_key(self) -> str:
        """嵌入模型 api_key，为空时回退到 llm_api_key。"""
        return self.embedding_api_key or self.llm_api_key


settings = Settings()
