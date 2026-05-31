"""LLM 对话修改 Chain — 基于现有大纲 + 对话历史 + 用户消息，输出修改后的大纲。

核心 Prompt 设计：
  1. 理解用户的修改意图（改文字/增删页/调顺序/换布局/改数据）
  2. 精准修改目标页面，未提及的页面保持原样
  3. 结构化输出（与 chains 输出格式完全兼容）
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model

# ── System Prompt ──

SYSTEM_PROMPT = """你是一个专业的文档编辑助手。用户会给你一份现有文档的结构化大纲（JSON 格式），以及一条修改指令。你需要根据修改指令调整大纲，然后输出完整的新大纲。

## 你的任务
1. 仔细阅读现有大纲的结构和内容
2. 理解用户的修改意图
3. 精准修改目标页面/节的内容
4. 未提及的页面保持原样（不做任何改动）
5. 输出完整的新大纲 JSON

## 修改能力
- 修改任意页面的标题（title）和正文（body）
- 增删页面/章节（增加/删除 slides 或 sections 数组中的条目，重新编号 page_number/section_number）
- 调整页面顺序（重新排列 slides/sections 数组）
- 切换布局类型（PPT 的 layout_type，可选: cover, section_header, text_only, text_image, two_column, grid_cards, big_number, chart, table, timeline, summary）
- 修改图表数据（chart_data）和表格数据（table_data）
- 改变整体风格（style: academic/business/creative/minimal/tech/warm）

## 输出格式
你必须输出一个合法的 JSON 对象，包含以下字段：

### PPT 格式:
```json
{
  "title": "文档标题",
  "subtitle": "副标题（可选）",
  "doc_type": "ppt",
  "style": "academic",
  "slides": [
    {
      "page_number": 1,
      "title": "页面标题",
      "body": "正文内容",
      "layout_type": "text_only",
      "visual_plan": "视觉描述",
      "image_query": "配图搜索关键词（英文）",
      "chart_data": null,
      "table_data": null,
      "style": ""
    }
  ]
}
```

### Word 格式:
```json
{
  "title": "文档标题",
  "subtitle": "副标题（可选）",
  "doc_type": "word",
  "style": "academic",
  "sections": [
    {
      "section_number": 1,
      "heading": "节标题",
      "content": "正文内容",
      "has_image": false,
      "image_query": "",
      "chart_data": null,
      "table_data": null
    }
  ]
}
```

### PDF 格式:
```json
{
  "title": "文档标题",
  "doc_type": "pdf",
  "style": "academic",
  "slides": [
    {
      "page_number": 1,
      "title": "页面标题",
      "body": "正文内容",
      "layout_type": "text_only",
      "visual_plan": "",
      "image_query": "",
      "chart_data": null,
      "table_data": null
    }
  ]
}
```

## 关键规则
1. **保留元信息**: 每个页面的 layout_type, visual_plan, image_query, chart_data, table_data, style 等字段必须保留（除非用户明确要求修改它们）
2. **页码连续性**: 如果有增删操作，所有受影响页面的 page_number/section_number 必须重新编号，从 1 开始连续递增
3. **只改用户说的**: 用户没提到的页面和字段，必须保持原样，严禁擅自修改
4. **body 字段**: PPT 的 body 包含该页的要点文本，用换行符分隔多个要点
5. **content 字段**: Word 的 content 是正文段落，用换行符分隔段落
6. **输出纯 JSON**: 不要包含 markdown 代码块标记，不要包含任何解释文字，只输出 JSON 对象

## 对话格式
对话历史会以 role: user/assistant 的格式提供。你的回复将作为 assistant 回复展示给用户。
"""


# ── Chain 构建 ──

def build_modify_prompt(
    current_outline: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
) -> list:
    """构建对话修改的 Prompt 消息列表。

    Args:
        current_outline: 当前文档的完整大纲 JSON
        history: 最近 N 条历史消息
        user_message: 用户当前的修改指令

    Returns:
        [SystemMessage, HumanMessage] 消息列表
    """
    # 截断大纲中的 body/content 字段以避免 context 溢出
    truncated = _truncate_outline(current_outline)

    # 构建用户消息
    user_parts = [
        "=== 当前文档大纲 ===",
        json.dumps(truncated, ensure_ascii=False, indent=2),
    ]

    if history:
        user_parts.append("\n=== 对话历史 ===")
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            user_parts.append(f"[{role}]: {content}")

    user_parts.append(f"\n=== 用户修改指令 ===\n{user_message}")
    user_parts.append("\n请直接输出修改后的完整大纲 JSON：")

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content="\n".join(user_parts)),
    ]


def _truncate_outline(outline: dict[str, Any], max_body: int = 500) -> dict[str, Any]:
    """截断大纲中的 body/content 字段，避免 context 溢出。

    保留标题和结构信息，截断详细正文（LLM 修改时主要依赖标题定位页面）。
    """
    import copy
    result = copy.deepcopy(outline)

    # 截断 PPT slides 的 body
    for slide in result.get("slides", []):
        if "body" in slide and len(slide.get("body", "")) > max_body:
            slide["body"] = slide["body"][:max_body] + "..."

    # 截断 Word/PDF sections 的 content
    for section in result.get("sections", []):
        if "content" in section and len(section.get("content", "")) > max_body:
            section["content"] = section["content"][:max_body] + "..."

    return result


async def invoke_llm(
    outline: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    doc_type: str,
) -> str:
    """调用 LLM 进行大纲修改，返回 LLM 原始输出文本。

    Args:
        outline: 当前文档大纲
        history: 历史消息
        user_message: 用户当前消息
        doc_type: ppt / word / pdf

    Returns:
        LLM 输出的字符串（可能是 JSON 或包含 JSON 的 markdown）
    """
    llm = create_chat_model()
    messages = build_modify_prompt(outline, history, user_message)

    try:
        chain = messages | llm | StrOutputParser()
        result = await chain.ainvoke({})
        logger.info(f"LLM modify output length: {len(result)}")
        return result
    except Exception as exc:
        logger.error(f"LLM modify call failed: {exc}")
        raise


async def generate_title(
    outline: dict[str, Any],
    user_message: str,
    doc_type: str,
) -> str:
    """根据首次对话生成会话标题（仿 DeepSeek / ChatGPT 行为）。

    Args:
        outline: 当前文档大纲
        user_message: 用户首条消息
        doc_type: ppt / word / pdf

    Returns:
        生成的标题（≤20 字），失败时返回空字符串
    """
    # 提取大纲摘要：标题 + 前几页标题
    outline_summary = outline.get("title", "")
    pages = outline.get("slides", outline.get("sections", []))
    page_titles = [
        p.get("title", p.get("heading", ""))
        for p in pages[:5] if p.get("title") or p.get("heading")
    ]
    if page_titles:
        outline_summary += " | " + " → ".join(page_titles)

    prompt = f"""根据以下信息，生成一个简短的会话标题（不超过 20 字），用于左侧栏标签展示。

文档主题：{outline_summary[:300]}
用户首条消息：{user_message[:200]}
文档类型：{doc_type}

只输出标题本身，不要引号、不要解释。"""

    try:
        llm = create_chat_model()
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        title = result.content.strip() if hasattr(result, 'content') else str(result).strip()
        # 清理：去掉可能的引号、截断过长
        title = title.replace('"', '').replace('「', '').replace('」', '').strip()
        if len(title) > 20:
            title = title[:20]
        logger.info(f"Title generated: '{title}'")
        return title
    except Exception as exc:
        logger.warning(f"Title generation failed (non-critical): {exc}")
        return ""
