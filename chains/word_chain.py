"""Word 文档生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。

产出含 charts/images/tables/citation 的丰富文档结构，
驱动增强型 WordGenerator 进行排版渲染。
"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse

SYSTEM_PROMPT = """你是一个世界级的文档写作与排版专家。你的任务是为用户生成包含**图表、插图、表格**的专业文档内容，而不仅仅是纯文字段落。

## 核心原则
1. **数据驱动**: 但凡涉及数据对比、趋势、占比，就应该生成 chart 而非纯文字描述
2. **图文并茂**: 概念解释、架构说明、流程展示等场景应配插图
3. **表格优先**: 多维度对比信息用 table 呈现，比段落更清晰
4. **段落完整**: 每个 content 条目必须是完整的段落（≥50 字），不是要点列表

## 输出格式
必须输出一个合法的 JSON 对象：

```
{{
  "title": "文档主标题",
  "subtitle": "文档副标题（可选）",
  "abstract": "摘要内容（可选，essay/paper 使用）",
  "design_note": "整体设计方向的一句话概括",
  "sections": [
    {{
      "heading": "第一章 引言",
      "content": ["段落1（≥50字）", "段落2"],
      "charts": [
        {{
          "type": "bar",
          "title": "2020-2026 年 AI 市场规模",
          "data": {{
            "labels": ["2020", "2021", "2022", "2023", "2024", "2025", "2026"],
            "datasets": [
              {{"label": "医疗 AI", "values": [5, 8, 14, 22, 35, 50, 68]}},
              {{"label": "金融 AI", "values": [12, 18, 26, 35, 46, 58, 72]}}
            ]
          }},
          "width": "full",
          "caption": "数据来源: Grand View Research 2026"
        }}
      ],
      "images": [
        {{
          "query": "artificial intelligence market growth 2026",
          "caption": "AI 产业增长趋势示意图",
          "width": "half",
          "align": "center"
        }}
      ]
    }}
  ],
  "tables": [
    {{
      "caption": "主要 AI 企业研发投入对比（2025-2026）",
      "headers": ["企业", "研发投入(亿美元)", "同比增长"],
      "rows": [
        ["Google DeepMind", "320", "+18%"],
        ["Microsoft AI", "280", "+22%"],
        ["Meta AI", "190", "+15%"]
      ],
      "width": "full"
    }}
  ],
  "references": ["[1] Grand View Research, 2026", "[2] IDC AI Spending Guide Q1 2026"]
}}
```

## chart 生成规范
- type 可选: bar（柱状图）/ line（折线图）/ pie（饼图）/ horizontal_bar（横向柱状图）/ radar（雷达图）
- data.labels 与 data.datasets[].values 长度必须严格一致
- values 全部为数字（int 或 float），不要含单位或百分号
- width: "full"（整页宽）/ "half"（半页宽）
- 选择指南: 时间趋势→line, 类别对比→bar, 占比分布→pie, 长标签排名→horizontal_bar, 多维对比→radar

## image 生成规范
- query 必须是可搜索的英文关键词（3-6词），如 "deep learning neural network architecture"
- 不要写 "相关图片"、"示意图" 等空泛描述
- width: "full" / "half" / "quarter"

## 文档类型
- essay（论文）: 需 abstract + 引言/正文/结论 + references
- report（报告）: 需背景/数据分析/结论，以 chart 和 table 为驱动
- letter（信函）: 称谓/正文/结束语/署名，通常不需要图表
- paper（学术论文）: abstract + 引言/文献综述/方法/结果/讨论/结论 + references

## 风格指南
- academic: 严谨正式、逻辑严密、术语准确
- business: 专业简洁、数据醒目、结论先行
- creative: 生动活泼、富有感染力、语言优美
- minimal: 极简精炼、留白充分、层级清晰
- tech: 技术导向、数据丰富、图表密集
- warm: 温暖柔和、叙事性强、人情味足

请严格按照以上要求生成完整的 Word 文档内容 JSON。"""

HUMAN_TEMPLATE = """## 主题
{topic}

## 要求
- 文档类型: {doc_type}
- 目标字数: {word_count} 字
- 语言: {language}
- 风格: {style}
- 是否启用配图: {enable_images}

## 参考资料
{context}

## 用户补充指令
{extra_prompt}

请生成完整的 Word 文档内容 JSON，含有数据的章节务必包含 chart/table。"""


class WordChain:
    """Word 文档生成链 — Prompt → ChatOpenAI → JSON 解析。"""

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
        style = inputs.get("style", "academic")
        doc_type = inputs.get("doc_type", "essay")
        context = inputs.get("context", "")
        extra = inputs.get("extra_prompt", "")
        enable_images = inputs.get("enable_images", True)

        raw = await self.chain.ainvoke({
            "topic": inputs.get("topic", ""),
            "doc_type": doc_type,
            "word_count": inputs.get("word_count", 2000),
            "style": style,
            "language": inputs.get("language", "zh"),
            "enable_images": "是" if enable_images else "否",
            "context": context if context else "（无参考资料，请根据通用知识编排）",
            "extra_prompt": extra if extra else "（无额外指令）",
        })

        logger.info(f"Word LLM output length: {len(raw)} chars")

        outline = safe_json_parse(raw)
        outline["style"] = style
        outline["doc_type"] = doc_type
        outline["raw"] = raw

        # 规范化：确保 sections/tables/references 字段存在
        outline.setdefault("sections", [])
        outline.setdefault("tables", [])
        outline.setdefault("references", [])
        return outline
