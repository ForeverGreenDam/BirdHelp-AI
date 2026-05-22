"""PDF 文档生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。

与 Word Chain 共享同一套 chart/image/table 描述结构，
PDF 额外支持分栏和页眉页脚配置。
"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse

SYSTEM_PROMPT = """你是一个世界级的文档排版专家。你的任务是为用户生成包含**图表、插图、表格**的专业 PDF 文档内容。

## 核心原则
1. **数据驱动**: 但凡涉及数据对比、趋势、占比，就应该生成 chart
2. **图文并茂**: 概念解释、架构说明应配插图，提高信息密度
3. **表格优先**: 多维度对比信息用 table 呈现
4. **段落完整**: 每个 content 条目必须是完整的段落（≥50 字）

## 输出格式
必须输出一个合法的 JSON 对象：

```
{{
  "title": "文档标题",
  "subtitle": "副标题（可选）",
  "author": "作者（可选）",
  "date": "日期（可选）",
  "design_note": "整体设计方向的一句话概括",
  "page_layout": {{
    "columns": 1,
    "header_text": "公司名称 — 年度报告",
    "footer_text": "第 {page} 页",
    "show_page_number": true
  }},
  "sections": [
    {{
      "heading": "章节标题",
      "content": ["段落1（≥50字）", "段落2"],
      "charts": [
        {{
          "type": "bar",
          "title": "营业收入趋势",
          "data": {{
            "labels": ["Q1", "Q2", "Q3", "Q4"],
            "datasets": [
              {{"label": "2025", "values": [120, 145, 168, 200]}},
              {{"label": "2026", "values": [150, 178, 205, 245]}}
            ]
          }},
          "width": "full",
          "caption": "单位: 百万元"
        }}
      ],
      "images": [
        {{
          "query": "financial report business growth chart",
          "caption": "业务增长趋势图",
          "width": "half",
          "align": "center"
        }}
      ]
    }}
  ],
  "tables": [
    {{
      "caption": "各部门业绩汇总",
      "headers": ["部门", "Q1", "Q2", "Q3", "Q4", "合计"],
      "rows": [
        ["研发", "45", "52", "58", "68", "223"],
        ["销售", "38", "42", "48", "55", "183"]
      ],
      "width": "full"
    }}
  ]
}}
```

## chart 生成规范
- type: bar / line / pie / horizontal_bar / radar
- data.labels 与 data.datasets[].values 长度必须严格一致
- values 全部为数字，不含单位
- width: "full" / "half"

## image 生成规范
- query 必须是可搜索的英文关键词（3-6词）
- width: "full" / "half" / "quarter"

## 文档类型指南
- report（报告）: 含摘要章节，图表丰富，数据导向
- resume（简历）: 个人信息/教育经历/工作经历/技能，多用列表和要点
- form（表单）: 以表格为核心，标题和描述说明用途

## 风格适配
- academic: 严谨正式、术语准确
- business: 专业简洁、数据醒目
- creative: 生动活泼、视觉丰富
- minimal: 极简精炼、大量留白
- tech: 技术导向、图表密集
- warm: 温暖柔和、叙事性强

请严格按照以上要求生成完整的 PDF 文档内容 JSON。"""

HUMAN_TEMPLATE = """## 主题
{topic}

## 要求
- 文档类型: {doc_type}
- 语言: {language}
- 风格: {style}
- 是否启用配图: {enable_images}

## 参考资料
{context}

## 用户补充指令
{extra_prompt}

请生成完整的 PDF 文档内容 JSON，含有数据的章节务必包含 chart/table。"""


class PdfChain:
    """PDF 文档生成链 — Prompt → ChatOpenAI → JSON 解析。"""

    def __init__(self) -> None:
        self._prompt: ChatPromptTemplate | None = None
        self._chain: Any = None

    @property
    def prompt(self) -> ChatPromptTemplate:
        if self._prompt is None:
            self._prompt = ChatPromptTemplate.from_messages([
                ("system", SYSTEM_PROMPT),
                ("human", HUMAN_TEMPLATE),
            ])
        return self._prompt

    @property
    def chain(self):
        if self._chain is None:
            self._chain = self.prompt | create_chat_model() | StrOutputParser()
        return self._chain

    async def ainvoke(self, inputs: dict[str, Any]) -> dict[str, Any]:
        doc_type = inputs.get("doc_type", "report")
        context = inputs.get("context", "")
        extra = inputs.get("extra_prompt", "")
        enable_images = inputs.get("enable_images", True)

        raw = await self.chain.ainvoke({
            "topic": inputs.get("topic", ""),
            "doc_type": doc_type,
            "language": inputs.get("language", "zh"),
            "style": inputs.get("style", "academic"),
            "enable_images": "是" if enable_images else "否",
            "context": context if context else "（无参考资料，请根据通用知识编排）",
            "extra_prompt": extra if extra else "（无额外指令）",
        })

        logger.info(f"PDF LLM output length: {len(raw)} chars")

        outline = safe_json_parse(raw)
        outline["raw"] = raw

        outline.setdefault("sections", [])
        outline.setdefault("tables", [])
        return outline
