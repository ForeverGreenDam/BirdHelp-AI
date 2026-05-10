"""Pydantic 数据模型 — 定义 API 请求/响应结构与枚举常量。

覆盖文档生成、对话修改、任务状态查询等全部接口。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── 通用 ──

class TaskStatus(str, Enum):
    """异步任务状态枚举。"""
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ApiResponse(BaseModel):
    """统一响应体，code=0 表示成功。"""
    code: int = 0
    message: str = "success"
    data: Any | None = None


# ── 文档生成请求 ──

class GenerateRequest(BaseModel):
    """文档生成基类请求，包含 RAG 相关可选字段。"""
    user_id: str = Field(..., description="用户 ID")
    topic: str = Field(..., description="文档主题")
    language: str = Field(default="zh", description="zh / en")
    extra_prompt: str | None = Field(default=None, description="用户补充指令")
    material_ids: list[str] | None = Field(default=None, description="RAG 素材 ID 列表")
    rag_enabled: bool = Field(default=False, description="是否启用 RAG")
    callback_id: str = Field(..., description="关联 Java 后端请求 ID")


class PptGenerateRequest(GenerateRequest):
    """PPT 生成请求，扩展风格与页数。"""
    style: str = Field(default="academic", description="academic / business / creative")
    slide_count: int = Field(default=10, ge=1, le=50)


class WordGenerateRequest(GenerateRequest):
    """Word 生成请求，扩展文档类型与字数。"""
    doc_type: str = Field(default="essay", description="essay / report / letter / paper")
    word_count: int = Field(default=2000, ge=500, le=10000)


class PdfGenerateRequest(GenerateRequest):
    """PDF 生成请求，扩展文档类型。"""
    doc_type: str = Field(default="report", description="report / resume / form")


# ── 文档生成响应 ──

class GenerateResponse(BaseModel):
    """生成任务提交后立即返回，包含 task_id 用于后续轮询。"""
    task_id: str
    status: TaskStatus


# ── 对话修改 ──

class ChatMessage(BaseModel):
    """对话历史中的单条消息。"""
    role: str
    content: str


class ChatModifyRequest(BaseModel):
    """对话式修改文档的请求体。"""
    user_id: str
    session_id: str
    file_id: str = Field(..., description="当前编辑的文档 ID")
    message: str = Field(..., description="用户修改指令")
    history: list[ChatMessage] = Field(default_factory=list)
    rag_enabled: bool = False
    callback_id: str


class ChatModifyResponse(BaseModel):
    """对话修改响应，包含任务 ID 与 AI 回复文本。"""
    task_id: str
    reply: str
    status: TaskStatus


# ── 任务状态 ──

class TaskStatusResponse(BaseModel):
    """异步任务状态查询响应，完成时返回文件 URL，失败时返回错误信息。"""
    task_id: str
    status: TaskStatus
    file_url: str | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
