"""LangGraph 生成状态图 — RAG 检索 → Chain 执行 → JSON 校验 → 失败重试。

支持 PPT / Word / PDF 三种文档类型，通过 state["doc_type"] 分发。
同步模式下，图的 ainvoke() 会阻塞直到生成完成或所有重试耗尽。
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import StateGraph, END, START
from loguru import logger

from chains.ppt_chain import PptChain
from chains.word_chain import WordChain
from chains.pdf_chain import PdfChain
from generator.ppt import PptGenerator
from generator.word import WordGenerator
from generator.pdf import PdfGenerator
from rag.retrieval import retrieve_formatted
from utils.file import temp_file_path, ensure_temp_dir
from utils.format import safe_json_parse

MAX_RETRIES = 3

EXTENSION_MAP = {"ppt": ".pptx", "word": ".docx", "pdf": ".pdf"}


# ── 状态定义 ──

class GenerationState(TypedDict, total=False):
    """文档生成状态 — 所有字段由 LangGraph 按"后写入覆盖"语义合并。"""

    # ── 输入参数（调用方注入，之后不变） ──
    user_id: str
    project_id: str
    topic: str
    language: str
    extra_prompt: str
    rag_enabled: bool
    material_ids: list[str]
    doc_type: str              # "ppt" | "word" | "pdf"
    doc_subtype: str           # word: essay/report/letter/paper; pdf: report/resume/form
    style: str                 # PPT 风格: academic/business/creative
    slide_count: int           # PPT 页数
    word_count: int            # Word 字数

    # ── RAG 结果 ──
    context: str

    # ── Chain 执行中间产物 ──
    chain_output: str
    parsed_outline: dict[str, Any]

    # ── 重试控制 ──
    attempt: int

    # ── 最终产物 ──
    file_path: str
    error: str


# ── 图单例 ──

_graph: Any = None


def _build_graph() -> StateGraph:
    """构建并编译生成状态图，全局复用。"""
    builder = StateGraph(GenerationState)

    builder.add_node("retrieve_context", _retrieve_context)
    builder.add_node("generate_outline", _generate_outline)
    builder.add_node("validate_outline", _validate_outline)
    builder.add_node("build_document", _build_document)
    builder.add_node("handle_error", _handle_error)

    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "generate_outline")
    builder.add_edge("generate_outline", "validate_outline")

    builder.add_conditional_edges("validate_outline", _route_after_validate, {
        "build": "build_document",
        "retry": "generate_outline",
        "error": "handle_error",
    })

    builder.add_edge("build_document", END)
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
    """调用对应 Chain 生成文档大纲 JSON 字符串。"""
    doc_type = state.get("doc_type", "ppt")
    context = state.get("context", "") or "（无参考资料，请根据通用知识编排）"
    extra = state.get("extra_prompt", "") or "（无额外指令）"
    language = state.get("language", "zh")

    if doc_type == "word":
        chain = WordChain()
        raw = await chain.chain.ainvoke({
            "topic": state.get("topic", ""),
            "doc_type": state.get("doc_subtype", "essay"),
            "word_count": state.get("word_count", 2000),
            "style": state.get("style", "academic"),
            "language": language,
            "context": context,
            "extra_prompt": extra,
        })
    elif doc_type == "pdf":
        chain = PdfChain()
        raw = await chain.chain.ainvoke({
            "topic": state.get("topic", ""),
            "doc_type": state.get("doc_subtype", "report"),
            "language": language,
            "context": context,
            "extra_prompt": extra,
        })
    else:
        chain = PptChain()
        raw = await chain.chain.ainvoke({
            "topic": state.get("topic", ""),
            "style": state.get("style", "academic"),
            "slide_count": state.get("slide_count", 10),
            "language": language,
            "context": context,
            "extra_prompt": extra,
        })

    outline = safe_json_parse(raw)
    outline["style"] = state.get("style", "academic")

    logger.info(f"generate_outline ({doc_type}): {len(raw)} chars, "
                f"sections={len(outline.get('sections', outline.get('slides', [])))}")
    return {"chain_output": raw, "parsed_outline": outline}


async def _validate_outline(state: GenerationState) -> dict[str, Any]:
    """校验解析结果，成功则清除错误，失败则递增 attempt 并记录错误。"""
    doc_type = state.get("doc_type", "ppt")
    attempt = state.get("attempt", 0)
    outline = state.get("parsed_outline", {})
    errors = []

    if not outline.get("title"):
        errors.append("缺少主标题字段 'title'")

    if doc_type == "ppt":
        slides = outline.get("slides", [])
        if not slides or len(slides) < 2:
            errors.append(f"幻灯片数量不足: {len(slides)} (需要 >= 2)")
    else:
        sections = outline.get("sections", [])
        if not sections:
            errors.append("缺少内容章节 'sections'")

    if errors:
        err_msg = "; ".join(errors)
        logger.warning(f"Validation attempt {attempt + 1}/{MAX_RETRIES} failed: {err_msg}")
        return {
            "attempt": attempt + 1,
            "error": err_msg,
            "parsed_outline": {},
        }

    logger.info(f"Validation passed ({doc_type})")
    return {"attempt": attempt, "error": ""}


async def _build_document(state: GenerationState) -> dict[str, Any]:
    """将校验通过的大纲构建为文档文件。"""
    doc_type = state.get("doc_type", "ppt")
    outline = state.get("parsed_outline", {})
    ensure_temp_dir()
    extension = EXTENSION_MAP.get(doc_type, ".pptx")
    file_path = temp_file_path(extension)

    if doc_type == "word":
        generator = WordGenerator()
    elif doc_type == "pdf":
        generator = PdfGenerator()
    else:
        generator = PptGenerator()

    actual_path = generator.generate(outline, file_path)
    return {"file_path": str(actual_path)}


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
