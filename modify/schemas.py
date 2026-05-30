"""Pydantic 模型 — 对话修改 API 的请求/响应结构。

所有字段使用 Python snake_case，由 FastAPI + Pydantic 自动处理序列化。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── 文档类型枚举 ──

class DocType(str, Enum):
    ppt = "ppt"
    word = "word"
    pdf = "pdf"


# ── 大纲结构（用于 LLM 输出校验） ──

class SlideOutline(BaseModel):
    """PPT 单页大纲（与 chains/ppt_chain.py 输出格式兼容）。"""
    page_number: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    body: str = ""
    layout_type: str = Field(default="text_only")
    visual_plan: str = ""
    image_query: str = ""
    chart_data: dict[str, Any] | None = None
    table_data: dict[str, Any] | None = None
    style: str = ""


class SectionOutline(BaseModel):
    """Word/PDF 单节大纲。"""
    section_number: int = Field(..., ge=1)
    heading: str = Field(..., min_length=1)
    content: str = ""
    has_image: bool = False
    image_query: str = ""
    chart_data: dict[str, Any] | None = None
    table_data: dict[str, Any] | None = None


class DocumentOutline(BaseModel):
    """完整文档大纲（PPT 格式）。"""
    title: str = ""
    subtitle: str = ""
    doc_type: str = "ppt"
    style: str = "academic"
    slides: list[SlideOutline] = Field(default_factory=list)
    sections: list[SectionOutline] = Field(default_factory=list)


# ── 变更摘要 ──

class ChangeItem(BaseModel):
    """单条变更描述。"""
    page_number: int | None = None
    action: str  # "modified" | "added" | "deleted" | "unchanged"
    summary: str  # 一句话简述变更内容


# ── API 请求 ──

class ModifyRequest(BaseModel):
    """对话修改文档请求。"""
    user_id: str = Field(..., description="用户 ID")
    project_id: str = Field(..., description="项目 ID")
    session_id: str = Field(..., description="会话 ID（UUID v4）")
    file_id: str = Field(..., description="当前编辑的文档 ID")
    doc_type: str = Field(..., description="ppt / word / pdf")
    message: str = Field(..., description="用户修改指令")
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="历史消息列表，每项含 role(user/assistant) 和 content",
    )
    regenerate_file: bool = Field(
        default=True,
        description="是否重建文件（false 时仅返回文本回复，不生成文件）",
    )
    callback_id: str = Field(default="", description="关联 Java 后端请求 ID")


class ModifyResponse(BaseModel):
    """对话修改响应。"""
    session_id: str
    reply: str = Field(..., description="AI 文本回复")
    outline: dict[str, Any] | None = Field(
        default=None,
        description="修改后的完整大纲 JSON",
    )
    changes: list[ChangeItem] = Field(
        default_factory=list,
        description="变更摘要列表",
    )
    file_id: str | None = Field(
        default=None,
        description="新生成的文件 ID（regenerate_file=False 时为空）",
    )
    file_url: str | None = Field(
        default=None,
        description="新生成的文件 URL",
    )
    success: bool = True
