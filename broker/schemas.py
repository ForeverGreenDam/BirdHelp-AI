"""RabbitMQ 消息体 Pydantic 模型，负责解析与校验 Java 端发出的生成任务消息。

字段名使用 camelCase（与 Java 端约定一致），通过 alias 映射到 Python snake_case。

协议版本 v1.0: java 端在消息中直接携带 LLM 配置（apiKey/baseUrl/modelName），
Python 端消费后注入 create_chat_model()，无需自行管理密钥。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


SUPPORTED_VERSIONS = {"1.0"}
VALID_DOC_TYPES = {"ppt", "word", "pdf"}
VALID_STYLES = {"academic", "business", "creative", "minimal", "tech", "warm"}
VALID_LANGUAGES = {"zh", "en"}
VALID_WORD_SUBTYPES = {"essay", "report", "letter", "paper"}
VALID_PDF_SUBTYPES = {"report", "resume", "form"}


class TaskMessage(BaseModel):
    """RabbitMQ 任务消息体，字段名保持与 Java 端一致的 camelCase。

    使用 populate_by_name=True 允许同时通过 alias (camelCase) 和
    Python 字段名 (snake_case) 访问。
    """

    model_config = {"populate_by_name": True}

    # ── 通用必填 ──
    version: str = Field(alias="version")
    task_id: str = Field(alias="taskId")
    callback_id: str = Field(alias="callbackId")
    doc_type: str = Field(alias="docType")
    user_id: str = Field(alias="userId")
    project_id: str = Field(alias="projectId")
    topic: str = Field(alias="topic")
    language: str = Field(alias="language")
    rag_enabled: bool = Field(alias="ragEnabled")
    timestamp: int = Field(alias="timestamp")

    # ── LLM 配置（由 Java 端注入，为空时自动降级到 .env） ──
    api_key: str = Field(default="", alias="apiKey")
    base_url: str = Field(default="", alias="baseUrl")
    model_name: str = Field(default="", alias="modelName")

    # ── 通用选填 ──
    extra_prompt: str | None = Field(default=None, alias="extraPrompt")
    material_ids: list[str] | None = Field(default=None, alias="materialIds")
    style: str = Field(default="academic", alias="style")
    enable_images: bool = Field(default=True, alias="enableImages")

    # ── PPT 专属 ──
    slide_count: int = Field(default=10, alias="slideCount", ge=1, le=50)

    # ── Word 专属 ──
    doc_subtype: str = Field(default="essay", alias="docSubtype")
    word_count: int = Field(default=2000, alias="wordCount", ge=500, le=10000)


class TaskCallback(BaseModel):
    """任务完成/失败回调体，发送到 Java POST /api/internal/task/callback。"""

    task_id: str
    callback_id: str
    user_id: int
    project_id: int
    status: str  # "completed" | "failed"
    file_id: int | None = None
    file_url: str | None = None
    file_name: str | None = None
    qa_lowest_score: int | None = None
    qa_passed_count: int | None = None
    qa_total_count: int | None = None
    generation_time_ms: int = 0
    error_code: int = 0
    error_message: str = ""

    def to_camel_dict(self) -> dict:
        """转为 camelCase JSON 字典，用于 HTTP 回调。"""
        return {
            "taskId": self.task_id,
            "callbackId": self.callback_id,
            "userId": self.user_id,
            "projectId": self.project_id,
            "status": self.status,
            "fileId": self.file_id,
            "fileUrl": self.file_url,
            "fileName": self.file_name,
            "qaLowestScore": self.qa_lowest_score,
            "qaPassedCount": self.qa_passed_count,
            "qaTotalCount": self.qa_total_count,
            "generationTimeMs": self.generation_time_ms,
            "errorCode": self.error_code,
            "errorMessage": self.error_message,
        }


class TaskProgress(BaseModel):
    """任务进度通知体，发送到 Java POST /api/internal/task/progress。"""

    task_id: str
    callback_id: str
    status: str = "processing"
    stage: str
    progress: int = 0
    message: str = ""

    def to_camel_dict(self) -> dict:
        return {
            "taskId": self.task_id,
            "callbackId": self.callback_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "message": self.message,
        }
