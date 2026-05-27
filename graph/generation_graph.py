"""LangGraph 生成状态图 — RAG 检索 → Chain 执行 → JSON 校验 → 失败重试。

支持 PPT / Word / PDF 三种文档类型，通过 state["doc_type"] 分发。
PPT: 额外经过 图片获取 + QA 评分
Word: 额外经过 图表渲染 + 图片获取 + 文档 QA
PDF: 额外经过 图表渲染 + 图片获取（QA 复用 Word QA 链）
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
    """文档生成状态。"""

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

    enable_images: bool

    # LLM 配置由 Java 端通过 RabbitMQ 消息注入，透传到 create_chat_model()
    llm_config: dict[str, str]

    context: str
    chain_output: str
    parsed_outline: dict[str, Any]

    images_map: dict[str, list[str]]
    qa_reports: list[dict]

    attempt: int
    file_path: str
    error: str


# ── 图单例 ──

_graph: Any = None


def _build_graph() -> StateGraph:
    builder = StateGraph(GenerationState)

    builder.add_node("retrieve_context", _retrieve_context)
    builder.add_node("generate_outline", _generate_outline)
    builder.add_node("validate_outline", _validate_outline)
    builder.add_node("render_charts", _render_charts)
    builder.add_node("fetch_images", _fetch_images)
    builder.add_node("run_qa", _run_qa)
    builder.add_node("build_document", _build_document)
    builder.add_node("handle_error", _handle_error)

    builder.add_edge(START, "retrieve_context")
    builder.add_edge("retrieve_context", "generate_outline")
    builder.add_edge("generate_outline", "validate_outline")

    builder.add_conditional_edges("validate_outline", _route_after_validate, {
        "render_charts": "render_charts",
        "run_qa": "run_qa",
        "retry": "generate_outline",
        "error": "handle_error",
    })

    builder.add_edge("render_charts", "run_qa")
    builder.add_edge("run_qa", "fetch_images")
    builder.add_edge("fetch_images", "build_document")
    builder.add_edge("build_document", END)
    builder.add_edge("handle_error", END)

    return builder.compile()


def get_generation_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ── 节点实现 ──

async def _retrieve_context(state: GenerationState) -> dict[str, Any]:
    if not state.get("rag_enabled", False):
        logger.info("RAG disabled, skip retrieval")
        return {"context": ""}
    user_id = state.get("user_id", "")
    project_id = state.get("project_id", "")
    query = state.get("topic", "")
    context = await retrieve_formatted(str(user_id), str(project_id), query)
    if context:
        logger.info(f"RAG retrieved context: {len(context)} chars")
    return {"context": context}


async def _generate_outline(state: GenerationState) -> dict[str, Any]:
    import time as _time
    _t0 = _time.monotonic()

    # 将 Java 端注入的 LLM 配置设置到当前异步上下文，后续 create_chat_model() 自动读取
    llm_config = state.get("llm_config", {})
    if llm_config:
        from core.llm import set_llm_config
        set_llm_config(llm_config)

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
            "enable_images": state.get("enable_images", True),
            "context": context,
            "extra_prompt": extra,
        })
    elif doc_type == "pdf":
        chain = PdfChain()
        raw = await chain.chain.ainvoke({
            "topic": state.get("topic", ""),
            "doc_type": state.get("doc_subtype", "report"),
            "language": language,
            "style": style,
            "enable_images": state.get("enable_images", True),
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

    items_count = len(outline.get("sections", outline.get("slides", [])))
    _elapsed = _time.monotonic() - _t0
    logger.info(f"generate_outline ({doc_type}): {len(raw)} chars, items={items_count}, "
                f"elapsed={_elapsed:.1f}s")
    return {"chain_output": raw, "parsed_outline": outline}


async def _validate_outline(state: GenerationState) -> dict[str, Any]:
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
        return {"attempt": attempt + 1, "error": err_msg, "parsed_outline": {}}

    logger.info(f"Validation passed ({doc_type})")
    return {"attempt": attempt, "error": ""}


async def _render_charts(state: GenerationState) -> dict[str, Any]:
    """为 Word/PDF 文档渲染图表。PPT 的图表通过布局渲染器处理，不在此处。"""
    doc_type = state.get("doc_type", "ppt")
    if doc_type == "ppt":
        return {}

    outline = state.get("parsed_outline", {})
    sections = outline.get("sections", [])

    from generator._chart_engine import render_chart, _HAS_MPL
    from generator._design import get_palette
    from utils.file import ensure_temp_dir

    if not _HAS_MPL:
        logger.info("Chart rendering skipped (matplotlib not installed)")
        return {}

    palette = get_palette(state.get("style", "academic"))
    chart_dir = ensure_temp_dir() / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    chart_count = 0
    for section in sections:
        for chart_spec in section.get("charts", []):
            chart_name = f"chart_{abs(hash(str(chart_spec))):x}.png"
            chart_path = chart_dir / chart_name
            result = render_chart(chart_spec, chart_path, palette)
            if result and result.exists():
                chart_count += 1

    logger.info(f"Charts rendered: {chart_count}")
    return {}


async def _fetch_images(state: GenerationState) -> dict[str, Any]:
    """为需要图片的文档搜索并下载配图。PPT 从 slides 取，Word/PDF 从 sections 取。"""
    doc_type = state.get("doc_type", "ppt")
    if not state.get("enable_images", False):
        logger.info("Image fetching disabled")
        return {"images_map": {}}

    from generator.ppt.image_provider import _search_unsplash, _search_pexels, \
        _download_image, _generate_placeholder, _images_dir, _query_hash

    outline = state.get("parsed_outline", {})

    # 收集所有 image_query，携带页面索引用于 key 匹配
    tasks: list[tuple[int, str]] = []
    if doc_type == "ppt":
        for slide in outline.get("slides", []):
            q = slide.get("image_query", "").strip()
            if q:
                page_num = slide.get("page_number", 0)
                tasks.append((page_num, q))
    else:
        img_idx = 0
        for section in outline.get("sections", []):
            for img in section.get("images", []):
                q = img.get("query", "").strip()
                if q:
                    tasks.append((img_idx, q))
                    img_idx += 1

    if not tasks:
        logger.info("No image queries found")
        return {"images_map": {}}

    import asyncio
    semaphore = asyncio.Semaphore(settings.ppt_max_concurrent_slides)
    results: dict[str, list[str]] = {}
    key_prefix = "slide" if doc_type == "ppt" else "img"

    async def _process_one(page_num: int, query: str) -> None:
        async with semaphore:
            key = f"{key_prefix}_{page_num:02d}"
            dest = _images_dir() / f"{key_prefix}_{page_num:02d}-{_query_hash(query)}.jpg"
            if dest.exists():
                results[key] = [str(dest)]
                return
            # Unsplash
            unsplash_results = await _search_unsplash(query)
            if unsplash_results:
                url = unsplash_results[0].get("urls", {}).get("regular", "")
                if url and await _download_image(url, dest):
                    results[key] = [str(dest)]
                    return
            # Pexels
            pexels_results = await _search_pexels(query)
            if pexels_results:
                url = pexels_results[0].get("src", {}).get("large", "")
                if url and await _download_image(url, dest):
                    results[key] = [str(dest)]
                    return
            # 占位图
            placeholder_path = _images_dir() / f"{key_prefix}_{page_num:02d}-placeholder.png"
            if _generate_placeholder(query, placeholder_path):
                results[key] = [str(placeholder_path)]

    await asyncio.gather(*[_process_one(pn, q) for pn, q in tasks])
    logger.info(f"Doc image fetch complete: {len(results)}/{len(tasks)} images")
    return {"images_map": results}


async def _run_qa(state: GenerationState) -> dict[str, Any]:
    """质量评估。PPT 用 PptQAChain，Word/PDF 用 DocQAChain。"""
    import time as _time
    _t0 = _time.monotonic()

    # QA chain 也使用 create_chat_model()，需要确保上下文中有 LLM 配置
    llm_config = state.get("llm_config", {})
    if llm_config:
        from core.llm import set_llm_config
        set_llm_config(llm_config)

    doc_type = state.get("doc_type", "ppt")
    outline = state.get("parsed_outline", {})
    style = state.get("style", "academic")

    if not settings.ppt_qa_enabled:
        logger.info(f"QA disabled by config, skipping ({doc_type})")
        return {"qa_reports": []}

    if doc_type == "ppt":
        from chains.qa_chain import PptQAChain
        slides = outline.get("slides", [])
        if not slides:
            return {"qa_reports": []}
        logger.info(f"Running PPT QA on {len(slides)} slides...")
        qa_chain = PptQAChain()
        repaired_slides, reports = await qa_chain.evaluate_all(
            slides, style=style,
            threshold=settings.ppt_qa_score_threshold,
            max_rounds=settings.ppt_max_repair_rounds,
        )
        outline["slides"] = repaired_slides
        _elapsed = _time.monotonic() - _t0
        logger.info(f"QA complete ({doc_type}): {len(slides)} slides, "
                    f"elapsed={_elapsed:.1f}s")
        return {
            "parsed_outline": outline,
            "qa_reports": [{"slide_index": r.slide_index, "score": r.score,
                            "passed": r.passed,
                            "issues": [c.detail for c in r.all_issues]}
                           for r in reports],
        }
    else:
        from chains.word_qa_chain import DocQAChain
        logger.info(f"Running doc QA for {doc_type}...")
        qa_chain = DocQAChain()
        fixed_outline, report = await qa_chain.evaluate_with_repair(
            outline,
            doc_type=state.get("doc_subtype", "essay"),
            word_count=state.get("word_count", 2000),
            style=style,
            threshold=settings.ppt_qa_score_threshold,
            max_rounds=settings.ppt_max_repair_rounds,
        )
        _elapsed = _time.monotonic() - _t0
        logger.info(f"QA complete ({doc_type}): score={report.score}, "
                    f"elapsed={_elapsed:.1f}s")
        return {
            "parsed_outline": fixed_outline,
            "qa_reports": [{"score": report.score, "passed": report.passed,
                            "issues": [c.detail for c in report.all_issues]}],
        }


async def _build_document(state: GenerationState) -> dict[str, Any]:
    doc_type = state.get("doc_type", "ppt")
    outline = state.get("parsed_outline", {})
    images_map = state.get("images_map", {})

    ensure_temp_dir()
    extension = EXTENSION_MAP.get(doc_type, ".pptx")
    file_path = temp_file_path(extension)

    if doc_type == "word":
        generator = WordGenerator()
        actual_path = generator.generate(outline, file_path, images_map=images_map)
    elif doc_type == "pdf":
        generator = PdfGenerator()
        actual_path = generator.generate(outline, file_path, images_map=images_map)
    else:
        generator = PptGenerator()
        actual_path = generator.generate(outline, file_path, images_map=images_map)

    return {"file_path": str(actual_path)}


async def _handle_error(state: GenerationState) -> dict[str, Any]:
    err = state.get("error", "未知错误")
    max_attempts = state.get("attempt", MAX_RETRIES)
    logger.error(f"Generation failed after {max_attempts} attempts: {err}")
    return {"error": err or "大纲生成失败，已达最大重试次数"}


# ── 条件路由 ──

def _route_after_validate(state: GenerationState) -> str:
    error = state.get("error", "")
    attempt = state.get("attempt", 0)

    if error:
        if attempt < MAX_RETRIES:
            return "retry"
        return "error"

    doc_type = state.get("doc_type", "ppt")
    if doc_type in ("word", "pdf"):
        return "render_charts"
    return "run_qa"
