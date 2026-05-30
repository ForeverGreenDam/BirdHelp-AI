"""FastAPI Router — 对话修改文档的 HTTP 接口。

两个接口（§三.3.2）:
  POST /ai/chat/modify  — 对话修改文档（LLM + 重建文件）
  POST /ai/chat/discuss — 仅讨论/问答（LLM + 文本回复，不建文件）
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, Request
from loguru import logger
from pydantic import ValidationError

from core.schemas import ApiResponse
from modify.schemas import ModifyRequest, ModifyResponse, ChangeItem
from modify.service import execute_modify, execute_discuss

router = APIRouter(prefix="/ai/chat", tags=["chat_modify"])


@router.post("/modify", response_model=ApiResponse)
async def chat_modify(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """对话修改文档。

    完整流程：获取大纲 → LLM 修改 → 校验 → 重建文件 → 上传 → 同步 Java。

    Request Body:
        {
            "userId": "...",
            "projectId": "...",
            "sessionId": "...",
            "fileId": "...",
            "docType": "ppt",
            "message": "把第二页标题改得激进一些",
            "history": [],
            "regenerateFile": true,
            "callbackId": ""
        }

    Response:
        {
            "code": 0,
            "message": "success",
            "data": {
                "sessionId": "...",
                "reply": "已根据您的指令修改...",
                "outline": {...},
                "changes": [...],
                "fileId": "101",
                "fileUrl": "...",
                "success": true
            }
        }
    """
    try:
        # 字段映射 camelCase → snake_case
        req = ModifyRequest(
            user_id=str(body.get("userId", "")),
            project_id=str(body.get("projectId", "")),
            session_id=str(body.get("sessionId", "")),
            file_id=str(body.get("fileId", "")),
            doc_type=str(body.get("docType", "ppt")),
            message=str(body.get("message", "")),
            history=body.get("history", []),
            regenerate_file=body.get("regenerateFile", True),
            callback_id=str(body.get("callbackId", "")),
        )

        if not req.user_id or not req.session_id or not req.file_id or not req.message:
            return {
                "code": 40000,
                "message": "缺少必填参数: userId/sessionId/fileId/message",
                "data": None,
            }

        result = await execute_modify(
            user_id=req.user_id,
            project_id=req.project_id,
            session_id=req.session_id,
            file_id=req.file_id,
            doc_type=req.doc_type,
            message=req.message,
            history=req.history,
            regenerate_file=req.regenerate_file,
            callback_id=req.callback_id,
        )

        changes = [
            {"page_number": c.get("page_number"), "action": c.get("action", ""), "summary": c.get("summary", "")}
            for c in result.get("changes", [])
        ]

        response_data: dict[str, Any] = {
            "sessionId": result["session_id"],
            "reply": result["reply"],
            "outline": result.get("outline"),
            "changes": changes,
            "fileId": result.get("file_id"),
            "fileUrl": result.get("file_url"),
            "success": result["success"],
        }

        logger.info(f"[Modify API] Success: sessionId={result['session_id']}, "
                    f"newFileId={result.get('file_id')}, changes={len(changes)}")

        return {"code": 0, "message": "success", "data": response_data}

    except ValidationError as exc:
        logger.warning(f"[Modify API] Validation error: {exc}")
        return {"code": 40000, "message": f"参数校验失败: {exc}", "data": None}

    except Exception as exc:
        logger.error(f"[Modify API] Unexpected error: {exc}\n{traceback.format_exc()}")
        return {"code": 50000, "message": f"修改失败: {str(exc)}", "data": None}


@router.post("/discuss", response_model=ApiResponse)
async def chat_discuss(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """仅讨论/问答（不重建文件）。

    与 /modify 区别：LLM 会修改大纲但不会生成文件，只返回文本回复。

    Request Body:
        {
            "userId": "...",
            "projectId": "...",
            "sessionId": "...",
            "fileId": "...",
            "docType": "ppt",
            "message": "这个文档的第一页标题有什么问题？",
            "history": [],
            "callbackId": ""
        }
    """
    try:
        req = ModifyRequest(
            user_id=str(body.get("userId", "")),
            project_id=str(body.get("projectId", "")),
            session_id=str(body.get("sessionId", "")),
            file_id=str(body.get("fileId", "")),
            doc_type=str(body.get("docType", "ppt")),
            message=str(body.get("message", "")),
            history=body.get("history", []),
            regenerate_file=False,  # 讨论不生成文件
            callback_id=str(body.get("callbackId", "")),
        )

        if not req.user_id or not req.session_id or not req.file_id or not req.message:
            return {
                "code": 40000,
                "message": "缺少必填参数: userId/sessionId/fileId/message",
                "data": None,
            }

        result = await execute_discuss(
            user_id=req.user_id,
            project_id=req.project_id,
            session_id=req.session_id,
            file_id=req.file_id,
            doc_type=req.doc_type,
            message=req.message,
            history=req.history,
            callback_id=req.callback_id,
        )

        response_data: dict[str, Any] = {
            "sessionId": result["session_id"],
            "reply": result["reply"],
            "outline": result.get("outline"),
            "changes": [],
            "fileId": None,
            "fileUrl": None,
            "success": result["success"],
        }

        return {"code": 0, "message": "success", "data": response_data}

    except ValidationError as exc:
        logger.warning(f"[Discuss API] Validation error: {exc}")
        return {"code": 40000, "message": f"参数校验失败: {exc}", "data": None}

    except Exception as exc:
        logger.error(f"[Discuss API] Unexpected error: {exc}\n{traceback.format_exc()}")
        return {"code": 50000, "message": f"讨论请求失败: {str(exc)}", "data": None}
