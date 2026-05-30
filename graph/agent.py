"""文档生成智能体 — 基于 ReAct 模式的自主文档创建引擎。

使用 LLM 驱动的 Agent 取代传统的固定流程编排，Agent 自主决定：
- 调用哪些工具
- 以什么顺序调用
- 是否需要重试或跳过某些步骤

架构：
  Agent (LLM) ←→ 工具集 (检索、生成、图表、配图、质检、构建)
  共享状态通过 _agent_state 字典在工具间传递。

用法：
  orchestrator = AgentOrchestrator()
  result = await orchestrator.run(task_state)
  # result: {"file_path": "...", "parsed_outline": {...}, "qa_reports": [...], ...}
"""

from __future__ import annotations

import asyncio
import time as _time
from typing import Any

from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.callbacks import AsyncCallbackHandler
from loguru import logger

from config import settings
from core.llm import create_chat_model

# ── 共享状态 ──
# 模块级字典，在异步单线程消费者上下文中是安全的。
# 各工具通过读写此字典在步骤间传递数据。

_agent_state: dict[str, Any] = {}


def _reset_agent_state(task_state: dict[str, Any]) -> None:
    """用任务消息字段初始化共享状态。"""
    _agent_state.clear()
    _agent_state.update(task_state)
    _agent_state.setdefault("context", "")
    _agent_state.setdefault("chain_output", "")
    _agent_state.setdefault("parsed_outline", {})
    _agent_state.setdefault("images_map", {})
    _agent_state.setdefault("qa_reports", [])
    _agent_state.setdefault("file_path", "")
    _agent_state.setdefault("error", "")


# ── 系统提示词 ──

AGENT_SYSTEM_PROMPT = """你是一个文档生成专家 AI。你的任务是自主编排一系列专业工具，产出高质量的 Office 文档。

## 你的角色
你负责生成 PPT 演示文稿、Word 文档和 PDF 报告。你掌控整个创作流程 —— 从资料检索到最终文件输出。

## 可用工具
1. **retrieve_knowledge** — 从知识库检索与主题相关的参考资料。启用 RAG 时应首先调用。
2. **generate_outline** — 使用大模型生成结构化文档大纲。这是内容创作的核心步骤。
3. **render_charts** — 为文档渲染数据图表图片（仅 Word/PDF 需要；PPT 的图表由布局渲染器处理，跳过此步）。
4. **fetch_images** — 根据大纲中的图片查询从 Unsplash/Pexels 搜索并下载配图。
5. **evaluate_quality** — 对大纲进行多维度质量评估，识别问题并自动修复。
6. **build_document** — 构建最终的 Office 文件（.pptx / .docx / .pdf）。必须作为最后一步调用。

## 推荐流程
1. retrieve_knowledge（如果启用了 RAG）
2. generate_outline
3. render_charts（仅 Word/PDF）
4. fetch_images（如果启用了图片）
5. evaluate_quality
6. build_document

## 自主决策准则
- 当某步骤不适用时可以跳过（例如 PPT 跳过 render_charts、纯文本文档跳过 fetch_images）。
- 当质量不达标时可以重复执行某步骤（例如首次生成的大纲质量差，则再次调用 generate_outline 重新生成，然后再调用 evaluate_quality）。
- 可以根据文档类型和具体需求灵活调整步骤顺序。
- 必须始终以 build_document 作为最后一步。build_document 只能调用一次。
- 不要向用户请求确认 —— 直接执行流程并交付最终文档。

## 质量标准
- 大纲结构必须完整，标题明确，内容充实。
- PPT 大纲每页的 layout_type 必须为以下有效值之一：cover、section、text_only、text_image、image_full、two_column、grid_crids、timeline、big_number、chart、table、quote、summary。
- Word/PDF 大纲必须包含完整的章节结构，每段不少于 50 字。
- 所有大纲必须是合法的 JSON 格式。

现在请自主开始生成文档。"""

# ── 工具定义 ──


@tool
async def retrieve_knowledge() -> str:
    """从 RAG 知识库检索与文档主题相关的参考资料。
    启用了 RAG 时应当首先调用此工具。返回检索到的资料数量。"""
    state = _agent_state
    if not state.get("rag_enabled", False):
        return "当前任务未启用 RAG，跳过知识检索。"

    from rag.retrieval import retrieve_formatted

    user_id = str(state.get("user_id", ""))
    project_id = str(state.get("project_id", ""))
    topic = state.get("topic", "")

    try:
        context = await retrieve_formatted(user_id, project_id, topic)
        state["context"] = context
        chars = len(context) if context else 0
        logger.info(f"[Agent] 知识检索完成: {chars} 字")
        if chars > 0:
            return f"成功从知识库检索到 {chars} 字的参考资料。"
        else:
            return "知识库中未找到相关参考资料。"
    except Exception as exc:
        logger.warning(f"[Agent] 知识检索失败: {exc}")
        state["context"] = ""
        return f"知识检索失败: {exc}。将在没有参考资料的情况下继续。"


@tool
async def generate_outline() -> str:
    """使用大模型生成结构化文档大纲。这是核心的内容创作步骤。
    首次调用会生成初始大纲；如果大纲存在质量问题，可以再次调用来重新生成。"""

    t0 = _time.monotonic()
    state = _agent_state

    # 从任务消息设置大模型配置
    llm_config = state.get("llm_config", {})
    if llm_config:
        from core.llm import set_llm_config
        set_llm_config(llm_config)

    doc_type = state.get("doc_type", "ppt")
    context = state.get("context", "") or "（无参考资料，请根据通用知识编排）"
    extra = state.get("extra_prompt", "") or "（无额外指令）"
    language = state.get("language", "zh")
    style = state.get("style", "academic")

    from utils.format import safe_json_parse

    try:
        if doc_type == "word":
            from chains.word_chain import WordChain
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
            outline = safe_json_parse(raw)
            outline["style"] = style
            outline.setdefault("sections", [])
            outline.setdefault("tables", [])
            outline.setdefault("references", [])
            items_count = len(outline.get("sections", []))

        elif doc_type == "pdf":
            from chains.pdf_chain import PdfChain
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
            outline = safe_json_parse(raw)
            outline.setdefault("sections", [])
            outline.setdefault("tables", [])
            items_count = len(outline.get("sections", []))

        else:  # ppt
            from chains.ppt_chain import PptChain
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
            outline.setdefault("slides", [])
            for slide in outline.get("slides", []):
                body = slide.get("body", slide.get("content", []))
                if isinstance(body, str):
                    body = [body]
                slide["body"] = body
                slide["content"] = body
            items_count = len(outline.get("slides", []))

    except Exception as exc:
        logger.error(f"[Agent] 大纲生成失败: {exc}")
        return f"大纲生成失败: {exc}。请重试。"

    state["chain_output"] = raw
    state["parsed_outline"] = outline

    elapsed = _time.monotonic() - t0
    logger.info(f"[Agent] 大纲生成完成 ({doc_type}): 条目数={items_count}, 耗时={elapsed:.1f}s")

    # 基本结构校验
    errors = []
    if not outline.get("title"):
        errors.append("缺少主标题")
    if doc_type == "ppt":
        slides = outline.get("slides", [])
        if not slides or len(slides) < 2:
            errors.append(f"幻灯片数量不足 ({len(slides)}，至少需要 2 页)")
    else:
        sections = outline.get("sections", [])
        if not sections:
            errors.append("未找到内容章节")

    if errors:
        return (
            f"大纲已生成，共 {items_count} 个条目，但存在结构问题: {'；'.join(errors)}。"
            f"建议重新生成大纲以修复这些问题。"
        )

    title = outline.get("title", "未命名")
    return f"大纲生成成功: {items_count} 个内容条目，标题='{title[:80]}'。可以继续下一步。"


@tool
async def render_charts() -> str:
    """为 Word/PDF 文档渲染数据图表图片。PPT 文档请跳过此步骤——PPT 的图表由布局渲染器内部处理。"""
    state = _agent_state
    doc_type = state.get("doc_type", "ppt")

    if doc_type == "ppt":
        return "PPT 的图表由布局渲染器内部处理，已跳过图表渲染。继续下一步。"

    from generator._chart_engine import render_chart, _HAS_MPL
    from generator._design import get_palette
    from utils.file import ensure_temp_dir

    if not _HAS_MPL:
        logger.info("[Agent] matplotlib 未安装，跳过图表渲染")
        return "matplotlib 未安装，跳过图表渲染。继续后续步骤。"

    outline = state.get("parsed_outline", {})
    sections = outline.get("sections", [])

    chart_specs = []
    for section in sections:
        chart_specs.extend(section.get("charts", []))

    if not chart_specs:
        return "大纲中未发现图表规格定义。跳过图表渲染。"

    palette = get_palette(state.get("style", "academic"))
    chart_dir = ensure_temp_dir() / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    chart_count = 0
    for chart_spec in chart_specs:
        try:
            chart_name = f"chart_{abs(hash(str(chart_spec))):x}.png"
            chart_path = chart_dir / chart_name
            result = render_chart(chart_spec, chart_path, palette)
            if result and result.exists():
                chart_count += 1
        except Exception as exc:
            logger.warning(f"[Agent] 图表渲染失败: {exc}")

    logger.info(f"[Agent] 图表渲染: {chart_count}/{len(chart_specs)} 张")
    return f"成功渲染 {chart_count}/{len(chart_specs)} 张图表。"


@tool
async def fetch_images() -> str:
    """根据大纲中的图片查询搜索并下载配图。
    依次尝试 Unsplash → Pexels，最终降级为纯色占位图。"""
    state = _agent_state
    doc_type = state.get("doc_type", "ppt")

    if not state.get("enable_images", False):
        return "当前任务未启用图片搜索。跳过。"

    from generator.ppt.image_provider import (
        _search_unsplash, _search_pexels,
        _download_image, _generate_placeholder,
        _images_dir, _query_hash,
    )

    outline = state.get("parsed_outline", {})

    # 从大纲中收集所有图片查询
    tasks: list[tuple[int, str]] = []
    if doc_type == "ppt":
        for slide in outline.get("slides", []):
            q = slide.get("image_query", "").strip()
            if q:
                page_num = slide.get("page_number", len(tasks))
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
        return "大纲中未发现图片查询。跳过图片搜索。"

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
            # 优先 Unsplash
            unsplash_results = await _search_unsplash(query)
            if unsplash_results:
                url = unsplash_results[0].get("urls", {}).get("regular", "")
                if url and await _download_image(url, dest):
                    results[key] = [str(dest)]
                    return
            # 降级 Pexels
            pexels_results = await _search_pexels(query)
            if pexels_results:
                url = pexels_results[0].get("src", {}).get("large", "")
                if url and await _download_image(url, dest):
                    results[key] = [str(dest)]
                    return
            # 最终降级：纯色占位图
            placeholder_path = _images_dir() / f"{key_prefix}_{page_num:02d}-placeholder.png"
            if _generate_placeholder(query, placeholder_path):
                results[key] = [str(placeholder_path)]

    await asyncio.gather(*[_process_one(pn, q) for pn, q in tasks])
    state["images_map"] = results

    logger.info(f"[Agent] 图片获取: {len(results)}/{len(tasks)} 张")
    return f"为 {len(results)}/{len(tasks)} 个查询获取了图片。"


@tool
async def evaluate_quality() -> str:
    """对已生成的大纲进行质量评估并自动修复发现的问题。
    在 generate_outline 之后、build_document 之前调用。
    如果质量仍不理想，可以多次调用以持续改进。"""

    t0 = _time.monotonic()
    state = _agent_state

    # 确保大模型配置对质检链生效
    llm_config = state.get("llm_config", {})
    if llm_config:
        from core.llm import set_llm_config
        set_llm_config(llm_config)

    doc_type = state.get("doc_type", "ppt")
    outline = state.get("parsed_outline", {})
    style = state.get("style", "academic")

    if not outline:
        return "没有可评估的大纲。请先调用 generate_outline。"

    if not settings.ppt_qa_enabled:
        logger.info("[Agent] 质检已通过配置关闭，跳过")
        return "质检功能已在服务器配置中关闭。可以直接调用 build_document。"

    try:
        if doc_type == "ppt":
            from chains.qa_chain import PptQAChain
            slides = outline.get("slides", [])
            if not slides:
                return "大纲中没有幻灯片可供评估。"

            qa_chain = PptQAChain()
            repaired_slides, reports = await qa_chain.evaluate_all(
                slides, style=style,
                threshold=settings.ppt_qa_score_threshold,
                max_rounds=settings.ppt_max_repair_rounds,
            )
            outline["slides"] = repaired_slides
            state["parsed_outline"] = outline

            scores = [r.score for r in reports]
            avg_score = sum(scores) / len(scores) if scores else 0
            passed_count = sum(1 for r in reports if r.passed)
            state["qa_reports"] = [
                {
                    "slide_index": r.slide_index, "score": r.score,
                    "passed": r.passed,
                    "issues": [c.detail for c in r.all_issues],
                }
                for r in reports
            ]

            elapsed = _time.monotonic() - t0
            logger.info(
                f"[Agent] 质检完成 (PPT): 均分={avg_score:.0f}, "
                f"通过={passed_count}/{len(slides)}, 耗时={elapsed:.1f}s"
            )
            return (
                f"质量评估完成: 共 {len(slides)} 页幻灯片，平均分 {avg_score:.0f}/100，"
                f"{passed_count}/{len(slides)} 页通过。已自动修复发现的问题。"
            )

        else:
            from chains.word_qa_chain import DocQAChain
            qa_chain = DocQAChain()
            fixed_outline, report = await qa_chain.evaluate_with_repair(
                outline,
                doc_type=state.get("doc_subtype", "essay"),
                word_count=state.get("word_count", 2000),
                style=style,
                threshold=settings.ppt_qa_score_threshold,
                max_rounds=settings.ppt_max_repair_rounds,
            )
            state["parsed_outline"] = fixed_outline
            state["qa_reports"] = [
                {
                    "score": report.score, "passed": report.passed,
                    "issues": [c.detail for c in report.all_issues],
                }
            ]

            elapsed = _time.monotonic() - t0
            logger.info(
                f"[Agent] 质检完成 ({doc_type}): 评分={report.score}, "
                f"通过={report.passed}, 耗时={elapsed:.1f}s"
            )
            return (
                f"质量评估完成: 评分 {report.score}/100。"
                f"通过: {report.passed}。已自动修复发现的问题。"
            )

    except Exception as exc:
        logger.error(f"[Agent] 质检失败: {exc}")
        return f"质量评估遇到错误: {exc}。可以跳过质检直接调用 build_document，也可以重试。"


@tool
async def build_document() -> str:
    """构建最终 Office 文件（.pptx / .docx / .pdf）。
    必须作为最后一步调用。仅在前面所有步骤都完成、大纲已生成、配图已就绪后调用。"""
    state = _agent_state
    doc_type = state.get("doc_type", "ppt")
    outline = state.get("parsed_outline", {})
    images_map = state.get("images_map", {})

    if not outline:
        return "错误: 没有可构建的大纲。请先调用 generate_outline。"

    from utils.file import temp_file_path, ensure_temp_dir

    ensure_temp_dir()
    extension_map = {"ppt": ".pptx", "word": ".docx", "pdf": ".pdf"}
    extension = extension_map.get(doc_type, ".pptx")
    file_path = temp_file_path(extension)

    try:
        if doc_type == "word":
            from generator.word import WordGenerator
            generator = WordGenerator()
            actual_path = generator.generate(outline, file_path, images_map=images_map)
        elif doc_type == "pdf":
            from generator.pdf import PdfGenerator
            generator = PdfGenerator()
            actual_path = generator.generate(outline, file_path, images_map=images_map)
        else:
            from generator.ppt import PptGenerator
            generator = PptGenerator()
            actual_path = generator.generate(outline, file_path, images_map=images_map)

        state["file_path"] = str(actual_path)
        items = (
            len(outline.get("slides", []))
            if doc_type == "ppt"
            else len(outline.get("sections", []))
        )
        logger.info(f"[Agent] 文档构建完成: {actual_path} ({items} 个条目)")
        return f"文档构建成功: {actual_path}。共 {items} 个内容条目。任务完成。"

    except Exception as exc:
        logger.error(f"[Agent] 文档构建失败: {exc}")
        return f"错误: 文档构建失败: {exc}。"


# ── 工具注册表 ──

AGENT_TOOLS = [
    retrieve_knowledge,
    generate_outline,
    render_charts,
    fetch_images,
    evaluate_quality,
    build_document,
]


# ── 进度回调 ──

class AgentAuditCallback(AsyncCallbackHandler):
    """Agent LLM 调用审计日志 — 使用 print 输出，确保生产环境可见。

    记录每次 ReAct 循环中的：
    - LLM 收到的消息（系统提示词 + 历史消息摘要）
    - LLM 返回的内容（工具调用选择 或 最终回复）
    - 工具调用的输入和输出
    """

    def __init__(self) -> None:
        self._step: int = 0

    def _p(self, *args, **kwargs) -> None:
        """统一的 print 输出，带 Agent 前缀便于 grep。"""
        print("[AGENT-AUDIT]", *args, **kwargs)

    # ── LLM 层 ──

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        **kwargs: Any,
    ) -> None:
        """LLM 推理开始 — 打印发送的消息摘要。"""
        self._step += 1
        self._p(f"{'='*60}")
        self._p(f"Step #{self._step} — LLM 推理开始")
        self._p(f"{'='*60}")

        for batch_idx, batch in enumerate(messages):
            for msg_idx, msg in enumerate(batch):
                role = getattr(msg, "type", "unknown")
                content = getattr(msg, "content", "")
                tool_calls = getattr(msg, "tool_calls", None)

                if role == "system":
                    # 系统提示词：打印全文（通常较短）
                    self._p(f"[系统提示词] (batch={batch_idx}, msg={msg_idx})")
                    self._p(content[:2000] if len(content) > 2000 else content)

                elif role == "human":
                    # 用户消息：通常是任务描述
                    self._p(f"[用户输入] (batch={batch_idx}, msg={msg_idx})")
                    self._p(content[:1000] if len(content) > 1000 else content)

                elif role == "ai":
                    # AI 消息：可能是之前的工具调用决策
                    if tool_calls:
                        for tc in tool_calls:
                            tc_name = tc.get("name", "?")
                            tc_args = tc.get("args", {})
                            args_str = str(tc_args)[:500]
                            self._p(f"[LLM决策] 调用工具: {tc_name}")
                            self._p(f"  输入参数: {args_str}")
                    else:
                        text = str(content)[:500]
                        self._p(f"[LLM回复] {text}")

                elif role == "tool":
                    # 工具返回结果（前一轮的 observation）
                    tool_name = getattr(msg, "name", "?")
                    text = str(content)[:800]
                    self._p(f"[工具返回] {tool_name}: {text}")

                else:
                    self._p(f"[{role}] content长度={len(str(content))}")

    async def on_chat_model_end(self, response: Any, **kwargs: Any) -> None:
        """LLM 推理完成 — 打印返回内容。"""
        self._p(f"--- Step #{self._step} 完成 ---")
        try:
            message = response.generations[0][0].message
            # 检查是否是工具调用
            tool_calls = getattr(message, "tool_calls", None) or []
            if tool_calls:
                for tc in tool_calls:
                    self._p(f"[LLM输出] → 调用工具: {tc.get('name', '?')}")
                    args_str = str(tc.get('args', {}))[:500]
                    self._p(f"  参数: {args_str}")
                # 检查是否同时有文字内容（比如推理过程）
                content = getattr(message, "content", "")
                if content:
                    self._p(f"[LLM推理] {str(content)[:800]}")
            else:
                content = str(getattr(message, "content", ""))[:1000]
                self._p(f"[LLM输出] 最终回复: {content}")

            # Token 用量
            llm_output = getattr(response, "llm_output", None) or {}
            usage = llm_output.get("token_usage", {})
            if usage:
                self._p(
                    f"[Token] prompt={usage.get('prompt_tokens','?')}, "
                    f"completion={usage.get('completion_tokens','?')}, "
                    f"total={usage.get('total_tokens','?')}"
                )
        except Exception:
            self._p(f"[LLM原始输出] {str(response)[:1000]}")
        self._p(f"{'='*60}\n")

    # ── 工具层 ──

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any,
    ) -> None:
        """工具开始执行。"""
        tool_name = serialized.get("name", "") if isinstance(serialized, dict) else ""
        input_preview = str(input_str)[:500]
        self._p(f"[工具调用] {tool_name} 开始执行")
        if input_preview and input_preview != "{}":
            self._p(f"  输入: {input_preview}")

    async def on_tool_end(
        self, output: Any, **kwargs: Any,
    ) -> None:
        """工具执行完成 — 打印返回结果。"""
        output_str = str(output)[:1000] if output else "(空)"
        self._p(f"[工具调用] 完成 → 返回: {output_str}")

    async def on_tool_error(
        self, error: Exception, **kwargs: Any,
    ) -> None:
        """工具执行出错。"""
        self._p(f"[工具调用] ❌ 错误: {error}")


# ── 进度回调（Java 推送） ──

# 工具名 → (进度阶段, 百分比, 提示消息)
_TOOL_PROGRESS_MAP = {
    "retrieve_knowledge": ("retrieving_context", 5, "正在检索参考资料..."),
    "generate_outline": ("generating_outline", 25, "正在生成文档大纲..."),
    "render_charts": ("rendering_charts", 55, "正在渲染图表..."),
    "fetch_images": ("fetching_images", 70, "正在搜索配图..."),
    "evaluate_quality": ("running_qa", 85, "正在质量评审..."),
    "build_document": ("building_document", 95, "正在构建文档文件..."),
}


class AgentProgressCallback(AsyncCallbackHandler):
    """Agent 工具调用进度回调：在每次工具开始执行时向前端推送进度。"""

    def __init__(self, sender):
        self._sender = sender
        self._task_msg = None

    def set_task_msg(self, task_msg):
        """绑定当前任务消息，供回调时使用。"""
        self._task_msg = task_msg

    async def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, **kwargs: Any,
    ) -> None:
        """工具开始执行时推送进度。"""
        if self._task_msg is None:
            return
        tool_name = serialized.get("name", "") if isinstance(serialized, dict) else ""
        if tool_name in _TOOL_PROGRESS_MAP:
            stage, pct, msg = _TOOL_PROGRESS_MAP[tool_name]
            await self._sender(self._task_msg, stage, pct, msg)


# ── Agent 编排器 ──


class AgentOrchestrator:
    """使用 ReAct Agent 编排文档生成的编排器。

    以 LLM 驱动的 Agent 取代固定的状态图，Agent 自主决定
    调用哪些工具、以什么顺序调用、何时重试。
    """

    def __init__(self, progress_sender=None) -> None:
        """初始化编排器。

        Args:
            progress_sender: 可选的异步回调 callable(task_msg, stage, pct, msg)，
                             用于向 Java 后端推送进度更新。
        """
        self._progress_sender = progress_sender
        self._agent = None
        self._model = None

    def _get_model(self):
        """获取或创建聊天模型，从 Agent 状态加载大模型配置。"""
        if self._model is None:
            self._model = create_chat_model()
        return self._model

    def _get_agent(self):
        """构建或获取已编译的 ReAct Agent。"""
        if self._agent is None:
            self._agent = create_react_agent(
                model=self._get_model(),
                tools=AGENT_TOOLS,
            )
        return self._agent

    async def run(
        self,
        task_state: dict[str, Any],
        task_msg: Any = None,
    ) -> dict[str, Any]:
        """执行 Agent 生成文档。

        Args:
            task_state: 任务参数（user_id、topic、doc_type、style 等）
            task_msg: 可选的 TaskMessage，用于进度回调

        Returns:
            包含以下键的字典: file_path、parsed_outline、qa_reports、
                              images_map、error、context、chain_output
        """
        _reset_agent_state(task_state)

        # 构建给 Agent 的任务描述
        doc_type = task_state.get("doc_type", "ppt")
        topic = task_state.get("topic", "")
        language = task_state.get("language", "zh")
        style = task_state.get("style", "academic")
        rag_enabled = task_state.get("rag_enabled", False)
        enable_images = task_state.get("enable_images", False)

        task_description = (
            f"请生成一份 {doc_type.upper()} 文档。\n"
            f"主题: {topic}\n"
            f"语言: {language}\n"
            f"风格: {style}\n"
            f"RAG 知识库已启用: {rag_enabled}\n"
            f"图片搜索已启用: {enable_images}\n"
        )
        if doc_type == "ppt":
            task_description += f"幻灯片页数: {task_state.get('slide_count', 10)}\n"
        elif doc_type == "word":
            task_description += f"目标字数: {task_state.get('word_count', 2000)}\n"
            task_description += f"文档子类型: {task_state.get('doc_subtype', 'essay')}\n"
        elif doc_type == "pdf":
            task_description += f"文档子类型: {task_state.get('doc_subtype', 'report')}\n"

        task_description += (
            "\n请自主生成这份文档。"
            "首先检索知识库（如已启用 RAG），然后生成大纲，"
            "根据需要添加图表和配图，进行质量评估，最后构建文档。"
            "必须以 build_document 作为最后一步。"
        )

        logger.info(f"[Agent] 开始: doc_type={doc_type}, topic={topic[:60]}")
        start_ms = int(_time.monotonic() * 1000)

        # 审计日志：打印系统提示词和任务描述
        print(f"[AGENT-AUDIT] {'='*60}")
        print(f"[AGENT-AUDIT] 任务开始: doc_type={doc_type}, topic={topic}")
        print(f"[AGENT-AUDIT] 系统提示词长度: {len(AGENT_SYSTEM_PROMPT)} 字符")
        print(f"[AGENT-AUDIT] 系统提示词全文:\n{AGENT_SYSTEM_PROMPT}")
        print(f"[AGENT-AUDIT] --- 用户任务描述 ---")
        print(f"[AGENT-AUDIT] {task_description}")
        print(f"[AGENT-AUDIT] {'='*60}\n")

        # 配置回调：审计日志 + 进度推送
        audit_cb = AgentAuditCallback()
        config: dict[str, Any] = {"callbacks": [audit_cb]}
        if self._progress_sender and task_msg is not None:
            progress_cb = AgentProgressCallback(self._progress_sender)
            progress_cb.set_task_msg(task_msg)
            config["callbacks"].append(progress_cb)

        # 运行 Agent
        try:
            result = await self._get_agent().ainvoke(
                {
                    "messages": [
                        SystemMessage(content=AGENT_SYSTEM_PROMPT),
                        HumanMessage(content=task_description),
                    ]
                },
                config=config,
            )
        except Exception as exc:
            logger.error(f"[Agent] 执行失败: {exc}")
            raise

        elapsed_ms = int(_time.monotonic() * 1000) - start_ms

        # 记录 Agent 的消息历史，便于调试
        messages = result.get("messages", [])
        tool_calls_count = sum(1 for m in messages if hasattr(m, "tool_calls") and m.tool_calls)
        logger.info(
            f"[Agent] 完成: 耗时={elapsed_ms}ms, "
            f"消息数={len(messages)}, 工具调用次数={tool_calls_count}"
        )

        # 从共享状态提取结果
        file_path = _agent_state.get("file_path", "")
        if not file_path:
            logger.warning("[Agent] 状态中未找到 file_path —— build_document 可能未被调用")
            # 尝试从最后一条工具消息中提取文件路径
            for m in reversed(messages):
                if hasattr(m, "content") and "文档构建成功:" in str(m.content):
                    import re
                    match = re.search(r"文档构建成功: (.+)$", str(m.content), re.MULTILINE)
                    if match:
                        file_path = match.group(1).strip()
                        _agent_state["file_path"] = file_path
                        break

        return {
            "file_path": file_path,
            "parsed_outline": _agent_state.get("parsed_outline", {}),
            "qa_reports": _agent_state.get("qa_reports", []),
            "images_map": _agent_state.get("images_map", {}),
            "error": _agent_state.get("error", ""),
            "context": _agent_state.get("context", ""),
            "chain_output": _agent_state.get("chain_output", ""),
        }


def get_agent_orchestrator(progress_sender=None) -> AgentOrchestrator:
    """AgentOrchestrator 工厂函数。每次调用返回全新实例。

    Args:
        progress_sender: 可选的异步进度回调函数。

    Returns:
        新的 AgentOrchestrator 实例。
    """
    return AgentOrchestrator(progress_sender=progress_sender)
