"""Java 内部 API 客户端 — HTTP 调用 Java ChatInternalController 的 4 个端点。

使用 client/http.py 的 RSA-SHA256 签名 HTTP 客户端。
所有调用失败均抛出 ModifyClientError（上层 service 负责重试与降级）。
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger
from client.http import get, post, put


class ModifyClientError(Exception):
    """调用 Java 内部 API 失败。"""
    def __init__(self, endpoint: str, status: int, detail: str):
        self.endpoint = endpoint
        self.status = status
        self.detail = detail
        super().__init__(f"[{status}] {endpoint}: {detail}")


# ── 大纲读写 ──

async def get_outline(file_id: int) -> dict[str, Any]:
    """GET /internal/file/{id}/outline — 获取文档大纲。

    Returns:
        {
            "fileId": 100,
            "outline": "{...}" or null,
            "fileName": "xxx.pptx",
            "fileType": 1
        }
    """
    path = f"/api/internal/file/{file_id}/outline"
    try:
        result = await get(path)
        if isinstance(result, dict) and result.get("code") == 0:
            return result.get("data", {})
        raise ModifyClientError(path, result.get("code", -1), str(result))
    except ModifyClientError:
        raise
    except Exception as exc:
        raise ModifyClientError(path, 0, str(exc)) from exc


async def update_outline(file_id: int, outline_json: str) -> None:
    """PUT /internal/file/{id}/outline — 更新文档大纲。

    Args:
        file_id: 文件记录 ID
        outline_json: 修改后的完整大纲 JSON 字符串
    """
    path = f"/api/internal/file/{file_id}/outline"
    try:
        result = await put(path, {"outline": outline_json})
        if isinstance(result, dict) and result.get("code") == 0:
            return
        raise ModifyClientError(path, result.get("code", -1), str(result))
    except ModifyClientError:
        raise
    except Exception as exc:
        raise ModifyClientError(path, 0, str(exc)) from exc


# ── 会话管理 ──

async def get_or_create_session(
    session_id: str,
    user_id: int,
    project_id: int,
    original_file_id: int,
    doc_type: str,
) -> dict[str, Any]:
    """POST /internal/chat/session — 获取或创建会话（幂等）。

    Returns:
        {
            "sessionId": "...",
            "originalFileId": 100,
            "currentFileId": 100,
            "docType": "ppt",
            "messages": [{...}, ...]
        }
    """
    path = "/api/internal/chat/session"
    body = {
        "sessionId": session_id,
        "userId": user_id,
        "projectId": project_id,
        "originalFileId": original_file_id,
        "docType": doc_type,
    }
    try:
        result = await post(path, body)
        if isinstance(result, dict) and result.get("code") == 0:
            return result.get("data", {})
        raise ModifyClientError(path, result.get("code", -1), str(result))
    except ModifyClientError:
        raise
    except Exception as exc:
        raise ModifyClientError(path, 0, str(exc)) from exc


async def append_messages(
    session_id: str,
    messages: list[dict[str, Any]],
    current_file_id: int | None = None,
) -> dict[str, Any]:
    """POST /internal/chat/session/{id}/messages — 追加消息。

    Args:
        session_id: 会话 ID
        messages: [{role, content, fileId?}, ...]
        current_file_id: 当前最新版本文件 ID（可选）
    """
    path = f"/api/internal/chat/session/{session_id}/messages"
    body: dict[str, Any] = {"messages": messages}
    if current_file_id is not None:
        body["currentFileId"] = current_file_id
    try:
        result = await post(path, body)
        if isinstance(result, dict) and result.get("code") == 0:
            return result.get("data", {})
        raise ModifyClientError(path, result.get("code", -1), str(result))
    except ModifyClientError:
        raise
    except Exception as exc:
        raise ModifyClientError(path, 0, str(exc)) from exc
