"""LangGraph 对话修改/讨论双模状态图。

模式（mode）:
  - "modify": 用户意图修改文档 → LLM 输出新大纲 JSON → 校验 → 重建 → 上传
  - "discuss": 用户提问/讨论文档 → LLM 输出自然语言建议 → 跳过校验/重建

结构:
  modify: START → chat_analyze → validate_output → rebuild → upload → END
  discuss: START → chat_analyze → validate_output(skip) → END
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END, START
from loguru import logger

from utils.format import safe_json_parse
from config import settings

MAX_RETRIES = 3

EXTENSION_MAP = {"ppt": ".pptx", "word": ".docx", "pdf": ".pdf"}


# ── 状态定义 ──

class ModifyState(TypedDict, total=False):
    """对话修改/讨论状态。"""

    mode: str  # "modify" 或 "discuss"
    user_id: str
    project_id: str
    session_id: str
    file_id: str  # 原始文件 ID
    doc_type: str
    message: str  # 用户当前修改指令
    history: list[dict[str, str]]  # 历史消息

    # 当前大纲（从 Java 获取或 parser 降级）
    current_outline: dict[str, Any]

    # LLM 输出
    chain_output: str  # LLM 原始文本
    new_outline: dict[str, Any]  # 解析后的新大纲
    changes: list[dict]  # 变更摘要

    # 文件生成
    should_rebuild: bool  # 是否重建文件
    file_path: str
    new_file_id: str
    new_file_url: str
    file_name: str

    # 流程控制
    attempts: int
    error: str
    ai_reply: str  # AI 文本回复


# ── 图单例 ──

_modify_graph: Any = None


def _build_modify_graph() -> StateGraph:
    builder = StateGraph(ModifyState)

    builder.add_node("chat_analyze", _chat_analyze)
    builder.add_node("validate_output", _validate_output)
    builder.add_node("rebuild_file", _rebuild_file)
    builder.add_node("upload_file", _upload_file)
    builder.add_node("handle_error", _handle_error)

    builder.add_edge(START, "chat_analyze")
    builder.add_edge("chat_analyze", "validate_output")

    builder.add_conditional_edges("validate_output", _route_after_validate, {
        "rebuild": "rebuild_file",
        "retry": "chat_analyze",
        "done": END,
        "error": "handle_error",
    })

    builder.add_edge("rebuild_file", "upload_file")
    builder.add_edge("upload_file", END)
    builder.add_edge("handle_error", END)

    return builder.compile()


def get_modify_graph() -> StateGraph:
    """获取对话修改图的全局单例（懒加载）。"""
    global _modify_graph
    if _modify_graph is None:
        _modify_graph = _build_modify_graph()
    return _modify_graph


# ── 节点函数 ──

async def _chat_analyze(state: ModifyState) -> ModifyState:
    """LLM 分析用户意图：modify 输出新大纲 JSON，discuss 输出自然语言建议。"""
    from modify.chain import invoke_modify_llm, invoke_discuss_llm

    mode = state.get("mode", "modify")
    attempts = state.get("attempts", 0) + 1
    logger.info(f"[{mode.capitalize()}::{state.get('session_id', '?')}] Chat analyze attempt {attempts}")

    try:
        if mode == "discuss":
            llm_output = await invoke_discuss_llm(
                outline=state["current_outline"],
                history=state.get("history", []),
                user_message=state["message"],
                doc_type=state.get("doc_type", "ppt"),
            )
        else:
            llm_output = await invoke_modify_llm(
                outline=state["current_outline"],
                history=state.get("history", []),
                user_message=state["message"],
                doc_type=state.get("doc_type", "ppt"),
            )

        state["chain_output"] = llm_output
        state["attempts"] = attempts

    except Exception as exc:
        logger.error(f"[{mode.capitalize()}] LLM call failed (attempt {attempts}): {exc}")
        state["error"] = f"LLM 调用失败: {exc}"
        state["attempts"] = attempts

    return state


def _validate_output(state: ModifyState) -> ModifyState:
    """modify 模式：解析 LLM 输出为结构化大纲，校验结构合法性。
    discuss 模式：直接将 LLM 文本回复作为 ai_reply 透传，跳过 JSON 解析。"""
    mode = state.get("mode", "modify")
    chain_output = state.get("chain_output", "")

    if mode == "discuss":
        state["ai_reply"] = chain_output or "抱歉，我没有生成有效的回复。"
        state["error"] = ""
        state["changes"] = []
        logger.info(f"[Discuss] Reply length: {len(state['ai_reply'])}")
        return state

    try:
        # 使用项目的 safe_json_parse 工具（支持 markdown 代码块中的 JSON）
        parsed = safe_json_parse(chain_output)

        if not isinstance(parsed, dict):
            raise ValueError("解析结果不是 JSON 对象")

        # 校验 PPT 结构
        if state.get("doc_type") == "ppt":
            slides = parsed.get("slides", [])
            if not slides or not isinstance(slides, list):
                raise ValueError("缺少 slides 数组")
            if len(slides) < 2:
                # PPT 最少 2 页（封面 + 正文）
                logger.warning("[Modify] slides < 2，但允许通过（可能删页导致）")

            for i, slide in enumerate(slides):
                if not isinstance(slide, dict):
                    raise ValueError(f"slides[{i}] 不是对象")
                if "page_number" not in slide:
                    slide["page_number"] = i + 1
                if "title" not in slide:
                    raise ValueError(f"slides[{i}] 缺少 title")

        # 校验 Word/PDF 结构
        else:
            sections = parsed.get("sections", [])
            if sections and not isinstance(sections, list):
                raise ValueError("sections 不是数组")

        state["new_outline"] = parsed
        state["error"] = ""

        # 提取变更摘要（对比 old_outline 和 new_outline）
        state["changes"] = _diff_outlines(state.get("current_outline", {}), parsed)

        # 简单的 AI 回复文本
        change_count = len(state["changes"])
        state["ai_reply"] = f"已根据您的指令修改文档大纲（{change_count} 处变更）。"

        logger.info(f"[Modify] Outline validated: {len(parsed.get('slides', parsed.get('sections', [])))} items")

    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        state["error"] = str(exc)
        logger.warning(f"[Modify] Validation failed: {exc}")

    return state


def _route_after_validate(state: ModifyState) -> str:
    """根据校验结果路由。discuss 模式校验通过后直接结束。"""
    mode = state.get("mode", "modify")
    error = state.get("error", "")
    if not error:
        if mode == "discuss":
            return "done"
        if state.get("should_rebuild", True):
            return "rebuild"
        return "done"

    # 校验失败 → 重试（最多 3 次）
    attempts = state.get("attempts", 0)
    if attempts < MAX_RETRIES:
        logger.info(f"[Modify] Retry {attempts}/{MAX_RETRIES}: {error}")
        return "retry"

    # 超过重试次数
    logger.error(f"[Modify] Max retries reached, giving up: {error}")
    state["ai_reply"] = f"抱歉，大纲修改失败（已重试 {MAX_RETRIES} 次）。请尝试更具体的修改指令。"
    return "error"


async def _rebuild_file(state: ModifyState) -> ModifyState:
    """根据新大纲重建文档文件。PPT 会先搜索下载配图再生成，确保图片不丢失。"""
    from generator.ppt import PptGenerator
    from generator.ppt.image_provider import fetch_images_for_slides
    from generator.word import WordGenerator
    from generator.pdf import PdfGenerator
    from utils.file import temp_file_path, ensure_temp_dir

    ensure_temp_dir()

    doc_type = state.get("doc_type", "ppt")
    ext = EXTENSION_MAP.get(doc_type, ".pptx")
    file_path = temp_file_path(ext)

    new_outline = state.get("new_outline", {})
    file_name = new_outline.get("title", "modified_document") + ext

    images_map: dict[str, list[str]] = {}

    try:
        if doc_type == "ppt":
            # 从修改后的大纲中提取 slides，搜索下载配图
            slides = new_outline.get("slides", [])
            if slides:
                logger.info(f"[Modify] Fetching images for {len(slides)} slides...")
                images_map = await fetch_images_for_slides(slides)
                logger.info(f"[Modify] Images fetched: {len(images_map)} slides have images")

            generator = PptGenerator()
            generator.generate(
                content=new_outline,
                output_path=file_path,
                images_map=images_map,
            )
        elif doc_type == "word":
            generator = WordGenerator()
            generator.generate(
                content=new_outline,
                output_path=file_path,
            )
        elif doc_type == "pdf":
            generator = PdfGenerator()
            generator.generate(
                content=new_outline,
                output_path=file_path,
            )

        state["file_path"] = file_path
        state["file_name"] = file_name
        logger.info(f"[Modify] File rebuilt: {file_path}")

    except Exception as exc:
        logger.error(f"[Modify] File rebuild failed: {exc}")
        state["error"] = f"文件重建失败: {exc}"

    return state


async def _upload_file(state: ModifyState) -> ModifyState:
    """上传新文件到 Java（携带 versionOf 建立版本链）。"""
    from client.file import upload

    file_path = state.get("file_path", "")
    if not file_path:
        state["error"] = "文件路径为空，无法上传"
        return state

    user_id = int(state["user_id"])
    project_id = int(state["project_id"])
    file_name = state.get("file_name", "modified.pptx")

    # 上传时携带 versionOf（原始文件 ID），Java 据此建立版本链
    original_fid = int(state.get("file_id", "0")) if state.get("file_id") else None

    try:
        result = await upload(file_path, user_id, project_id, file_name, version_of=original_fid)
        data = result.get("data", {}) if isinstance(result, dict) else {}

        state["new_file_id"] = str(data.get("id", ""))
        state["new_file_url"] = data.get("file_url") or data.get("fileUrl") or ""

        logger.info(f"[Modify] File uploaded: fileId={state['new_file_id']}")

    except Exception as exc:
        logger.error(f"[Modify] Upload failed: {exc}")
        state["error"] = f"文件上传失败: {exc}"

    return state


async def _handle_error(state: ModifyState) -> ModifyState:
    """错误处理节点。"""
    if not state.get("ai_reply"):
        state["ai_reply"] = f"修改失败: {state.get('error', '未知错误')}"
    logger.error(f"[Modify] Error handler: {state.get('error')}")
    return state


# ── 大纲差异对比 ──

def _diff_outlines(old: dict, new: dict) -> list[dict]:
    """对比新旧大纲，生成变更摘要列表。"""
    changes = []

    doc_type = new.get("doc_type", "ppt")
    key = "slides" if (doc_type == "ppt" or doc_type == "pdf") else "sections"
    old_items = old.get(key, [])
    new_items = new.get(key, [])

    old_map = {item.get("page_number", item.get("section_number", 0)): item for item in old_items}
    new_map = {item.get("page_number", item.get("section_number", 0)): item for item in new_items}

    old_pages = set(old_map.keys())
    new_pages = set(new_map.keys())

    # 新增
    for p in new_pages - old_pages:
        n = new_map[p]
        changes.append({
            "page_number": p,
            "action": "added",
            "summary": f"新增: {n.get('title', n.get('heading', f'第{p}项'))}",
        })

    # 删除
    for p in old_pages - new_pages:
        changes.append({
            "page_number": p,
            "action": "deleted",
            "summary": f"删除第{p}项",
        })

    # 修改
    for p in old_pages & new_pages:
        o = old_map[p]
        n = new_map[p]
        diffs = []
        o_title = o.get("title", o.get("heading", ""))
        n_title = n.get("title", n.get("heading", ""))
        if o_title != n_title:
            diffs.append(f"标题: \"{o_title}\" → \"{n_title}\"")
        o_body = o.get("body", o.get("content", ""))[:50]
        n_body = n.get("body", n.get("content", ""))[:50]
        if o_body != n_body:
            diffs.append(f"内容已修改")
        if diffs:
            changes.append({
                "page_number": p,
                "action": "modified",
                "summary": "; ".join(diffs),
            })

    return changes
