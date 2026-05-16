"""LangGraph 生成状态图 — RAG 检索 → Chain 执行 → JSON 校验 → 失败重试。

同步模式下，图的 ainvoke() 会阻塞直到生成完成或所有重试耗尽。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import StateGraph, END, START
from loguru import logger

from chains.ppt_chain import PptChain
from generator.ppt import PptGenerator
from rag.retrieval import retrieve_formatted
from utils.file import temp_file_path, ensure_temp_dir
from utils.format import safe_json_parse

MAX_RETRIES = 3


# ── 状态定义 ──

class GenerationState(TypedDict, total=False):
    """文档生成状态 — 所有字段由 LangGraph 按"后写入覆盖"语义合并。

    各节点只需返回自己关心的部分，未返回的字段保留旧值。
    """

    # ── 输入参数（调用方注入，之后不变） ──
    user_id: str
    project_id: str
    topic: str
    style: str
    slide_count: int
    language: str
    extra_prompt: str
    rag_enabled: bool
    material_ids: list[str]

    # ── RAG 结果 ──
    context: str

    # ── Chain 执行中间产物 ──
    chain_output: str         # LLM 原始输出文本
    parsed_outline: dict[str, Any]  # 解析后的结构化大纲

    # ── 重试控制 ──
    attempt: int              # 当前重试次数（0-based）

    # ── 最终产物 ──
    file_path: str            # 生成的 .pptx 临时路径
    error: str                # 失败信息（空 = 无错误）


# ── 图单例 ──

_graph: Any = None


def _build_graph() -> StateGraph:
    """构建并编译生成状态图，全局复用。"""
    builder = StateGraph(GenerationState)

    builder.add_node("retrieve_context", _retrieve_context)
    builder.add_node("generate_outline", _generate_outline)
    builder.add_node("validate_outline", _validate_outline)
    builder.add_node("build_pptx", _build_pptx)
    builder.add_node("handle_error", _handle_error)

    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "generate_outline")
    builder.add_edge("generate_outline", "validate_outline")

    builder.add_conditional_edges("validate_outline", _route_after_validate, {
        "build": "build_pptx",
        "retry": "generate_outline",
        "error": "handle_error",
    })

    builder.add_edge("build_pptx", END)
    builder.add_edge("handle_error", END)

    return builder.compile()


def get_generation_graph():
    """获取编译后的生成状态图单例。"""
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── 节点实现 ──

async def _retrieve_context(state: GenerationState) -> dict[str, Any]:
    """RAG 检索节点：若启用 RAG，获取参考资料的格式化文本。"""
    if not state.get("rag_enabled", False):
        logger.info("RAG disabled, skip retrieval")
        return {"context": ""}

    user_id = state.get("user_id", "")
    project_id = state.get("project_id", "")
    query = state.get("topic", "")
    logger.info(f"RAG retrieval for user={user_id} project={project_id} query={query[:50]}...")

    context = await retrieve_formatted(str(user_id), str(project_id), query)
    if context:
        logger.info(f"RAG retrieved context: {len(context)} chars")
    else:
        logger.warning("RAG returned empty context")
    return {"context": context}


async def _generate_outline(state: GenerationState) -> dict[str, Any]:
    """调用 PptChain 生成 PPT 大纲 JSON 字符串。"""
    chain = PptChain()
    raw = await chain.chain.ainvoke({
        "topic": state.get("topic", ""),
        "style": state.get("style", "academic"),
        "slide_count": state.get("slide_count", 10),
        "language": state.get("language", "zh"),
        "context": state.get("context", "") or "（无参考资料，请根据通用知识编排）",
        "extra_prompt": state.get("extra_prompt", "") or "（无额外指令）",
    })

    outline = safe_json_parse(raw)
    outline["style"] = state.get("style", "academic")
    outline["raw"] = raw

    logger.info(f"generate_outline: {len(raw)} chars, {len(outline.get('slides', []))} slides")
    return {"chain_output": raw, "parsed_outline": outline}


async def _validate_outline(state: GenerationState) -> dict[str, Any]:
    """校验解析结果，成功则清除错误，失败则递增 attempt 并记录错误。"""
    attempt = state.get("attempt", 0)
    outline = state.get("parsed_outline", {})
    slides = outline.get("slides", [])
    errors = []

    if not outline.get("title"):
        errors.append("缺少主标题字段 'title'")
    if not slides or len(slides) < 2:
        errors.append(f"幻灯片数量不足: {len(slides)} (需要 >= 2)")

    if errors:
        err_msg = "; ".join(errors)
        logger.warning(f"Validation attempt {attempt + 1}/{MAX_RETRIES} failed: {err_msg}")
        return {
            "attempt": attempt + 1,
            "error": err_msg,
            "parsed_outline": {},
        }

    logger.info(f"Validation passed: {len(slides)} slides")
    return {"attempt": attempt, "error": ""}


async def _build_pptx(state: GenerationState) -> dict[str, Any]:
    """将校验通过的大纲构建为 .pptx 文件。"""
    outline = state.get("parsed_outline", {})
    ensure_temp_dir()
    file_path = temp_file_path(".pptx")
    generator = PptGenerator()
    generator.generate(outline, file_path)
    return {"file_path": str(file_path)}


async def _handle_error(state: GenerationState) -> dict[str, Any]:
    """记录最终失败信息。"""
    err = state.get("error", "未知错误")
    max_attempts = state.get("attempt", MAX_RETRIES)
    logger.error(f"Generation failed after {max_attempts} attempts: {err}")
    return {"error": err or "大纲生成失败，已达最大重试次数"}


# ── 条件路由 ──

def _route_after_validate(state: GenerationState) -> str:
    """根据校验结果决定下一步。"""
    error = state.get("error", "")
    attempt = state.get("attempt", 0)

    if not error:
        return "build"
    if attempt < MAX_RETRIES:
        return "retry"
    return "error"
