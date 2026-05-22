"""LangGraph 生成状态图 — RAG 检索 → Chain 执行 → JSON 校验 → 失败重试。

支持 PPT / Word / PDF 三种文档类型，通过 state["doc_type"] 分发。
PPT 额外经过图片获取 + QA 评分流程。
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
from config import settings

MAX_RETRIES = 3

EXTENSION_MAP = {"ppt": ".pptx", "word": ".docx", "pdf": ".pdf"}


# ── 状态定义 ──

class GenerationState(TypedDict, total=False):
    """文档生成状态 — 所有字段由 LangGraph 按"后写入覆盖"语义合并。"""

    user_id: str
    project_id: str
    topic: str
    language: str
    extra_prompt: str
    rag_enabled: bool
    material_ids: list[str]
    doc_type: str
    doc_subtype: str
    style: str
    slide_count: int
    word_count: int

    # PPT 图片与 QA
    enable_images: bool

    context: str
    chain_output: str
    parsed_outline: dict[str, Any]

    # 图片获取产物
    images_map: dict[str, list[str]]

    # Q&A 产物
    qa_reports: list[dict]

    attempt: int
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
    builder.add_node("fetch_images", _fetch_images)
    builder.add_node("run_qa", _run_qa)
    builder.add_node("build_document", _build_document)
    builder.add_node("handle_error", _handle_error)

    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "generate_outline")
    builder.add_edge("generate_outline", "validate_outline")

    builder.add_conditional_edges("validate_outline", _route_after_validate, {
        "fetch_images": "fetch_images",
        "build": "build_document",
        "retry": "generate_outline",
        "error": "handle_error",
    })

    builder.add_edge("fetch_images", "run_qa")
    builder.add_edge("run_qa", "build_document")
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
    """RAG 检索节点。"""
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
    """调用对应 Chain 生成文档大纲。"""
    doc_type = state.get("doc_type", "ppt")
    context = state.get("context", "") or "（无参考资料，请根据通用知识编排）"
    extra = state.get("extra_prompt", "") or "（无额外指令）"
    language = state.get("language", "zh")
    style = state.get("style", "academic")

    if doc_type == "word":
        chain = WordChain()
        raw = await chain.chain.ainvoke({
            "topic": state.get("topic", ""),
            "doc_type": state.get("doc_subtype", "essay"),
            "word_count": state.get("word_count", 2000),
            "style": style,
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
            "style": style,
            "slide_count": state.get("slide_count", 10),
            "language": language,
            "context": context,
            "extra_prompt": extra,
        })

    outline = safe_json_parse(raw)
    outline["style"] = style

    slides_count = len(outline.get("sections", outline.get("slides", [])))
    logger.info(f"generate_outline ({doc_type}): {len(raw)} chars, slides={slides_count}")
    return {"chain_output": raw, "parsed_outline": outline}


async def _validate_outline(state: GenerationState) -> dict[str, Any]:
    """校验解析结果。"""
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


async def _fetch_images(state: GenerationState) -> dict[str, Any]:
    """为需要图片的页面搜索并下载配图。PPT 文档专用。"""
    if state.get("doc_type") != "ppt" or not state.get("enable_images", False):
        logger.info("Image fetching skipped")
        return {"images_map": {}}

    from generator.ppt.image_provider import fetch_images_for_slides

    slides = state.get("parsed_outline", {}).get("slides", [])
    if not slides:
        return {"images_map": {}}

    logger.info(f"Fetching images for {len(slides)} slides...")
    images_map = await fetch_images_for_slides(slides)
    logger.info(f"Image fetch complete: {len(images_map)} slides got images")
    return {"images_map": images_map}


async def _run_qa(state: GenerationState) -> dict[str, Any]:
    """逐页质量评估 + 修复循环。PPT 文档专用。"""
    if state.get("doc_type") != "ppt":
        logger.info("QA skipped (non-PPT document)")
        return {"qa_reports": []}

    from chains.qa_chain import PptQAChain

    outline = state.get("parsed_outline", {})
    slides = outline.get("slides", [])
    style = state.get("style", "academic")

    if not slides:
        return {"qa_reports": []}

    logger.info(f"Running QA on {len(slides)} slides (threshold={settings.ppt_qa_score_threshold})...")
    qa_chain = PptQAChain()
    repaired_slides, reports = await qa_chain.evaluate_all(
        slides,
        style=style,
        threshold=settings.ppt_qa_score_threshold,
        max_rounds=settings.ppt_max_repair_rounds,
    )

    outline["slides"] = repaired_slides
    return {
        "parsed_outline": outline,
        "qa_reports": [{"slide_index": r.slide_index, "score": r.score,
                        "passed": r.passed,
                        "issues": [c.detail for c in r.all_issues]}
                       for r in reports],
    }


async def _build_document(state: GenerationState) -> dict[str, Any]:
    """将校验通过的大纲构建为文档文件。"""
    doc_type = state.get("doc_type", "ppt")
    outline = state.get("parsed_outline", {})

    ensure_temp_dir()
    extension = EXTENSION_MAP.get(doc_type, ".pptx")
    file_path = temp_file_path(extension)

    if doc_type == "word":
        generator = WordGenerator()
        actual_path = generator.generate(outline, file_path)
    elif doc_type == "pdf":
        generator = PdfGenerator()
        actual_path = generator.generate(outline, file_path)
    else:
        generator = PptGenerator()
        images_map = state.get("images_map", {})
        actual_path = generator.generate(outline, file_path, images_map=images_map)

    return {"file_path": str(actual_path)}


async def _handle_error(state: GenerationState) -> dict[str, Any]:
    """记录最终失败信息。"""
    err = state.get("error", "未知错误")
    max_attempts = state.get("attempt", MAX_RETRIES)
    logger.error(f"Generation failed after {max_attempts} attempts: {err}")
    return {"error": err or "大纲生成失败，已达最大重试次数"}


# ── 条件路由 ──

def _route_after_validate(state: GenerationState) -> str:
    """根据校验结果和模式决定下一步。"""
    error = state.get("error", "")
    attempt = state.get("attempt", 0)

    if error:
        if attempt < MAX_RETRIES:
            return "retry"
        return "error"

    # 校验通过：PPT 走 fetch_images → QA → build，Word/PDF 直接 build
    if state.get("doc_type") == "ppt":
        return "fetch_images"

    return "build"
