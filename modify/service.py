"""对话修改业务编排 — 协调 client / parser / graph 完成完整修改流程。

流程（§二.2.3）:
  ① 调 Java API 获取大纲（100% 保真）
  ② 调 Java API 获取/创建会话 + 历史消息
  ③ 执行 LangGraph 状态图（LLM 修改大纲 → 校验 → 重建文件 → 上传）
  ④ 调 Java API 更新大纲 + 追加消息
  ⑤ 返回 AI 回复 + 新大纲 + 新 file_id
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from config import settings


async def execute_modify(
    user_id: str,
    project_id: str,
    session_id: str,
    file_id: str,
    doc_type: str,
    message: str,
    history: list[dict[str, str]],
    regenerate_file: bool = True,
    callback_id: str = "",
) -> dict[str, Any]:
    """执行完整的对话修改流程。

    Args:
        user_id: 用户 ID
        project_id: 项目 ID
        session_id: 会话 ID
        file_id: 被修改的源文件 ID
        doc_type: 文档类型 (ppt/word/pdf)
        message: 用户当前的修改指令
        history: 对话历史消息列表
        regenerate_file: 是否重建文件
        callback_id: 关联 Java 后端请求 ID

    Returns:
        {
            "session_id": "...",
            "reply": "AI 文本回复",
            "outline": {...} or None,
            "changes": [{...}],
            "file_id": "..." or None,
            "file_url": "..." or None,
            "success": bool
        }
    """
    from modify.client import (
        get_outline,
        get_or_create_session,
        append_messages,
        update_outline,
        ModifyClientError,
    )
    from modify.parser import parse_outline_from_file
    from modify.graph import get_modify_graph

    uid = int(user_id)
    pid = int(project_id)
    fid = int(file_id)

    # ── 步骤 1: 获取大纲 ──
    outline: dict[str, Any] = {}
    outline_source = "unknown"

    try:
        outline_data = await get_outline(fid)
        outline_str = outline_data.get("outline", "")
        if outline_str and isinstance(outline_str, str) and outline_str.strip():
            try:
                outline = json.loads(outline_str)
                outline_source = "mysql"
                logger.info(f"[Modify] Outline loaded from Java: fileId={fid}, "
                           f"slides={len(outline.get('slides', outline.get('sections', [])))}")
            except json.JSONDecodeError:
                logger.warning(f"[Modify] Outline JSON 解析失败，回退到 parser")
        else:
            logger.info(f"[Modify] Outline 为空，触发 parser 降级: fileId={fid}")
    except ModifyClientError as exc:
        logger.warning(f"[Modify] 获取大纲失败 (API: {exc.endpoint}): {exc.detail}")

    # 降级：从文件内容逆向解析
    if not outline:
        outline_source = "parser"
        outline = await _parse_outline_fallback(fid, doc_type)

    # ── 步骤 2: 获取/创建会话 ──
    try:
        session_data = await get_or_create_session(session_id, uid, pid, fid, doc_type)
        # 如果 Java 有更完整的历史，优先使用
        java_messages = session_data.get("messages", [])
        if java_messages and not history:
            history = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in java_messages
            ]
        logger.info(f"[Modify] Session ready: sessionId={session_id}, historySize={len(history)}")
    except ModifyClientError as exc:
        logger.warning(f"[Modify] 会话 API 异常（非致命）: {exc.detail}")

    # ── 步骤 3: 执行 LangGraph ──
    state = {
        "user_id": user_id,
        "project_id": project_id,
        "session_id": session_id,
        "file_id": file_id,
        "doc_type": doc_type,
        "message": message,
        "history": history,
        "current_outline": outline,
        "rebuild_file": regenerate_file,
        "chain_output": "",
        "new_outline": {},
        "changes": [],
        "file_path": "",
        "new_file_id": "",
        "new_file_url": "",
        "file_name": "",
        "attempts": 0,
        "error": "",
        "ai_reply": "",
    }

    graph = get_modify_graph()
    result = await graph.ainvoke(state)

    reply = result.get("ai_reply", "已完成修改。")
    new_outline = result.get("new_outline", {})
    changes = result.get("changes", [])
    new_file_id = result.get("new_file_id", "")
    new_file_url = result.get("new_file_url", "")
    error = result.get("error", "")
    success = not bool(error)

    # ── 步骤 4: 回调 Java — 更新大纲 + 追加消息 ──
    if success and new_outline and new_file_id:
        try:
            new_fid = int(new_file_id)
            await update_outline(new_fid, json.dumps(new_outline, ensure_ascii=False))
            logger.info(f"[Modify] New outline saved: fileId={new_fid}")
        except ModifyClientError as exc:
            logger.warning(f"[Modify] 更新大纲失败（非致命）: {exc.detail}")

    # 追加消息到会话
    try:
        msg_list = [
            {"role": "user", "content": message},
            {"role": "assistant", "content": reply, "fileId": int(new_file_id) if new_file_id else None},
        ]
        await append_messages(session_id, msg_list, int(new_file_id) if new_file_id else None)
        logger.info(f"[Modify] Messages appended: sessionId={session_id}")
    except ModifyClientError as exc:
        logger.warning(f"[Modify] 追加消息失败（非致命）: {exc.detail}")

    # ── 首轮对话生成标题（仿 ChatGPT/DeepSeek） ──
    title = ""
    if success and not history:
        try:
            from modify.chain import generate_title
            title = await generate_title(outline, message, doc_type)
        except Exception as exc:
            logger.warning(f"[Modify] Title generation failed (non-critical): {exc}")

    return {
        "session_id": session_id,
        "reply": reply,
        "outline": new_outline if success else None,
        "changes": changes,
        "file_id": new_file_id or None,
        "file_url": new_file_url or None,
        "title": title,
        "success": success,
        "_meta": {
            "outline_source": outline_source,
            "error": error if not success else "",
        },
    }


async def execute_discuss(
    user_id: str,
    project_id: str,
    session_id: str,
    file_id: str,
    doc_type: str,
    message: str,
    history: list[dict[str, str]],
    callback_id: str = "",
) -> dict[str, Any]:
    """执行仅讨论/问答（不重建文件）。

    复用 modify graph 但设置 regenerate_file=False，LLM 只改大纲层面
    但不触发文件重建和上传。
    """
    return await execute_modify(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        file_id=file_id,
        doc_type=doc_type,
        message=message,
        history=history,
        regenerate_file=False,
        callback_id=callback_id,
    )


# ── 辅助 ──

async def _parse_outline_fallback(file_id: int, doc_type: str) -> dict[str, Any]:
    """从 Java 下载文件，用 parser 逆向提取大纲（降级兜底）。"""
    from modify.client import ModifyClientError
    from modify.parser import parse_outline_from_file

    # 下载文件
    from client.file import download

    try:
        file_bytes = await download(file_id)
        if file_bytes:
            return await parse_outline_from_file(file_bytes, doc_type, f"file_{file_id}")
    except (ModifyClientError, Exception) as exc:
        logger.error(f"[Modify] Parser fallback 完全失败: {exc}")

    # 返回空大纲
    return {
        "title": f"Document {file_id}",
        "doc_type": doc_type,
        "style": "academic",
        "slides": [],
        "sections": [],
        "_meta": {"source": "fallback_empty", "error": str(exc) if 'exc' in dir() else "unknown"},
    }
