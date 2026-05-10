from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── 通用 ──

class TaskStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any | None = None


# ── 文档生成请求 ──

class GenerateRequest(BaseModel):
    user_id: str = Field(..., description="用户 ID")
    topic: str = Field(..., description="文档主题")
    language: str = Field(default="zh", description="zh / en")
    extra_prompt: str | None = Field(default=None, description="用户补充指令")
    material_ids: list[str] | None = Field(default=None, description="RAG 素材 ID 列表")
    rag_enabled: bool = Field(default=False, description="是否启用 RAG")
    callback_id: str = Field(..., description="关联 Java 后端请求 ID")


class PptGenerateRequest(GenerateRequest):
    style: str = Field(default="academic", description="academic / business / creative")
    slide_count: int = Field(default=10, ge=1, le=50)


class WordGenerateRequest(GenerateRequest):
    doc_type: str = Field(default="essay", description="essay / report / letter / paper")
    word_count: int = Field(default=2000, ge=500, le=10000)


class PdfGenerateRequest(GenerateRequest):
    doc_type: str = Field(default="report", description="report / resume / form")


# ── 文档生成响应 ──

class GenerateResponse(BaseModel):
    task_id: str
    status: TaskStatus


# ── 对话修改 ──

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatModifyRequest(BaseModel):
    user_id: str
    session_id: str
    file_id: str = Field(..., description="当前编辑的文档 ID")
    message: str = Field(..., description="用户修改指令")
    history: list[ChatMessage] = Field(default_factory=list)
    rag_enabled: bool = False
    callback_id: str


class ChatModifyResponse(BaseModel):
    task_id: str
    reply: str
    status: TaskStatus


# ── 任务状态 ──

class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    file_url: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
