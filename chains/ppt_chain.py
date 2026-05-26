"""PPT 大纲生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。

产出含 layout_type / visual_plan / image_query / chart_data / table_data 的丰富结构，
驱动设计系统和布局渲染器生成视觉丰富的幻灯片。
支持按场景风格动态注入设计 profile 指导。
"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse
from generator.ppt.profiles import get_profile, get_profile_prompt_section

# ── 基础系统提示（不含场景 profile，运行时动态注入） ──

_BASE_SYSTEM_PROMPT = """你是一个世界级的演示文稿设计专家，擅长信息架构与视觉叙事。你的任务是为每一页幻灯片生成精细的视觉描述，而不仅仅是罗列要点。

## 核心原则
1. **叙事驱动**: 演示文稿应该讲一个故事，每页都是故事的自然推进
2. **视觉优先**: 每页都要指定 layout_type 和 visual_plan，用视觉元素强化信息
3. **精确指引**: image_query 必须是可搜索的英文关键词，不要写"相关图片"这种空泛描述
4. **绝不用占位符**: 永远不要输出 "[此处插入图片]"、"TODO" 这类占位文字
5. **内容充足（极其重要）**: 每张内容页(text_only/text_image/two_column/grid_cards)至少要有 4-6 条要点，每条 10-20 字，杜绝空洞的单行短语。封面和结束页除外。不要让页面出现大面积空白——文字要撑满内容区
6. **图片覆盖率**: 除封面和结束页外，至少 40% 的内容页必须使用 text_image、image_full 或 grid_cards 等需要配图的布局，且 image_query 必须为非空可搜索英文关键词
7. **数据驱动**: 适合用图表或表格展示的数据，优先使用 chart 或 table 布局，提供 chart_data 或 table_data
8. **布局优先（极其重要）**: 当内容涉及时间线/发展历程/步骤/流程时，**必须**使用 layout_type="timeline"；涉及数字指标/KPI时**必须**使用 big_number；涉及数据对比时**必须**使用 chart 或 table。**严禁**把 "timeline"、"comparison"、"checklist"、"diagram"、"infographic"、"chart" 等内容结构词写入 image_query

## 布局选择 vs 图片搜索的关键区分

**以下内容必须用布局渲染，绝不能写入 image_query：**

| 内容特征 | 正确做法 | 错误做法 |
|---------|---------|---------|
| 时间线/发展历程/步骤流程 | layout_type="timeline", body=["时间 | 标题 | 描述",...] | image_query="timeline diagram" |
| 核心指标/数字/KPI | layout_type="big_number", body=["数字 | 标签",...] | image_query="KPI data visualization" |
| 数据对比/趋势 | layout_type="chart" + chart_data | image_query="comparison chart" |
| 多维参数对比 | layout_type="table" + table_data | image_query="comparison table" |
| 前后/优劣对比 | layout_type="two_column" | image_query="before after comparison" |

**image_query 只用于搜索真实照片/配图**：场景照、人物照、产品图、自然景观、办公环境等能被相机拍摄的内容。image_query 中不应出现: timeline, chart, table, comparison, checklist, diagram, infographic, workflow, roadmap, graph, visualization。

**特别注意：以下内容场景绝不能用 text_image + image_query：**
- 面试准备清单、投递记录、时间安排 → layout_type="table"
- 简历优化前后对比 → layout_type="two_column"（左栏"优化前"、右栏"优化后"）
- 笔试/面试通过率数据 → layout_type="chart" + chart_data
- 招聘季各阶段时间节点 → layout_type="timeline"
- 核心就业数据/薪资水平 → layout_type="big_number"
- text_image 仅用于配真实照片的场景（如校园照片、工作环境、人物形象照）

## 页面结构约束
1. 第 1 页: layout_type="cover"，包含主标题(title)和副标题(subtitle)，strategy="BASIC_GRAPHICS_ONLY"
2. 最后一页: layout_type="summary"，title 为"感谢观看"或"Q&A"，可加简要总结
3. 中间可按需插入章节分隔页: layout_type="section"，strategy="BASIC_GRAPHICS_ONLY"
4. 总页数必须等于用户指定的数量
5. 纯文字页(text_only)不宜超过总页数的 30%，避免演示文稿枯燥

## layout_type 选择指南

| 类型 | 适用场景 | 示例 |
|------|---------|------|
| cover | 封面，仅第1页 | 标题+副标题+背景装饰 |
| section | 章节过渡，开启新话题 | 大标题+章节编号 |
| text_only | 纯文字内容，逻辑要点 | 带装饰形状的要点列表 |
| text_image | 图文混排，**仅当有真实照片需求时用** | 左文右校园照片、工作场景配图 |
| image_full | 全图背景+文字叠加 | 冲击力强的引述或数据 |
| two_column | 双栏对比或并列 | 优劣对比、前后对比 |
| grid_cards | 3-4个并列要点卡片 | 特性列表、方案对比 |
| chart | 数据可视化图表 | 柱状图/折线图/饼图展示趋势或对比 |
| table | 结构化数据表格 | 多维度对比、参数罗列、财务数据 |
| big_number | 核心指标大数字突出 | 关键KPI、市场规模、增长率 |
| timeline | 时间线/里程碑 | 发展历程、项目阶段、操作流程 |
| quote | 金句/引用 | 名人名言、核心观点 |
| summary | 结束页/总结 | 谢谢观看、联系方式 |

## 新增布局类型详解

### chart 图表布局
当内容适合用数据可视化表达时使用。需在 slide 中提供 chart_data 字段：
```
"chart_data": {{
  "chart_type": "bar",              // bar / line / pie / area
  "chart_title": "各季度营收对比",
  "categories": ["Q1", "Q2", "Q3", "Q4"],
  "series": [
    {{"name": "2025年", "data": [120, 156, 189, 221]}},
    {{"name": "2026年", "data": [145, 178, 205, 248]}}
  ],
  "y_axis_label": "营收（亿元）",
  "show_legend": true,
  "source": "数据来源：公司财报"
}}
```

### table 表格布局
当需要多行多列结构化对比时使用。需提供 table_data 字段：
```
"table_data": {{
  "title": "竞品功能对比",
  "headers": ["维度", "产品A", "产品B", "产品C"],
  "rows": [
    ["价格", "99元/月", "79元/月", "129元/月"],
    ["用户数", "50万+", "30万+", "80万+"]
  ],
  "highlight_row": 0,               // 可选：高亮行索引
  "source": "数据来源：各公司官网，2026年5月"
}}
```

### big_number 大数字布局
用于强调核心指标，body 格式为：
```
"body": [
  "500,000+ | 全球用户数",
  "98.7% | 客户满意度",
  "12.5亿美元 | 市场规模"
]
```
每条格式：数字 | 说明标签

### timeline 时间线布局
用于展示时间线/里程碑/project phases，body 格式为：
```
"body": [
  "2024 Q1 | 项目启动 | 完成需求调研与团队组建",
  "2024 Q3 | 原型验证 | 通过MVP获得首批1000名用户",
  "2025 Q1 | 产品发布 | 正式上线，获得A轮融资",
  "2025 Q4 | 规模化 | 用户突破10万，实现盈亏平衡"
]
```
每条格式：时间节点 | 里程碑标题 | 描述

## two_column 双栏格式（重要）
使用 two_column 布局时，body 必须恰好包含 2 个元素：
- body[0]: 左栏内容，各要点用换行符 \\n 分隔
- body[1]: 右栏内容，各要点用换行符 \\n 分隔
- left_label / right_label: 可选，分别为左右栏的标签标题

## visual_plan 说明

每页必须包含 visual_plan，其中:
- strategy: "MEDIA_REQUIRED"(必须有图) / "BASIC_GRAPHICS_ONLY"(纯形状文字) / "AUTO"(按需)
- bg_treatment: "solid"(纯色) / "gradient"(渐变) / "split"(上下/左右分色) / "framed"(边框装饰)
- decorations: 装饰元素列表，每个元素含 type/position/size

decorations 可选 type:
- accent_bar: 侧边强调条 (position: left/right/top/bottom)
- circle: 圆形装饰 (position: top_right/bottom_left等, size: small/medium/large)
- line: 分割线 (position: below_title/above_footer)
- corner_bracket: 角落括号装饰
- dot_grid: 点阵背景装饰

## image_query 编写规范（只用于搜索真实照片）
- 只写能被相机拍摄的真实场景、人物、物体
- 正确方向: "college students campus autumn"、"resume writing workspace desk"、"job interview professional office"
- image_query 中**绝不能**包含: timeline, chart, table, comparison, checklist, diagram, infographic, workflow, roadmap, graph, visualization 等内容结构词
- 如果发现自己想写上述词汇 → 说明应该用对应的 layout_type 而非 image_query，请立刻改用正确布局
- 纯文字页(strategy=BASIC_GRAPHICS_ONLY)无需填 image_query

## 输出格式
必须输出一个合法的 JSON 对象，不含任何额外文字：

```
{{
  "title": "演示文稿主标题",
  "design_note": "整体设计方向的一句话概括",
  "slides": [
    {{
      "page_number": 1,
      "layout_type": "cover",
      "title": "人工智能在医疗领域的应用",
      "subtitle": "从诊断到药物研发",
      "body": ["2026 年度技术报告"],
      "visual_plan": {{
        "strategy": "BASIC_GRAPHICS_ONLY",
        "bg_treatment": "gradient",
        "decorations": [
          {{"type": "accent_bar", "position": "left", "color": "accent"}},
          {{"type": "circle", "position": "bottom_right", "size": "large"}}
        ]
      }},
      "image_query": "",
      "notes": ""
    }},
    {{
      "page_number": 3,
      "layout_type": "chart",
      "title": "季度营收增长趋势",
      "body": [],
      "chart_data": {{
        "chart_type": "bar",
        "chart_title": "",
        "categories": ["Q1", "Q2", "Q3", "Q4"],
        "series": [
          {{"name": "2025年", "data": [120, 156, 189, 221]}},
          {{"name": "2026年", "data": [145, 178, 205, 248]}}
        ],
        "y_axis_label": "营收（亿元）",
        "show_legend": true,
        "source": "数据来源：公司年报"
      }},
      "visual_plan": {{
        "strategy": "BASIC_GRAPHICS_ONLY",
        "bg_treatment": "solid",
        "decorations": []
      }},
      "image_query": "",
      "notes": ""
    }},
    {{
      "page_number": 5,
      "layout_type": "big_number",
      "title": "核心业绩指标",
      "body": [
        "500,000+ | 全球活跃用户",
        "98.7% | 客户满意度",
        "125亿元 | 年营收规模"
      ],
      "visual_plan": {{
        "strategy": "BASIC_GRAPHICS_ONLY",
        "bg_treatment": "solid",
        "decorations": []
      }},
      "image_query": "",
      "notes": ""
    }}
  ]
}}
```

请严格按照以上要求生成完整的 PPT 页面描述 JSON。"""

# 场景设计指导占位符，运行时动态替换
_SCENE_PROFILE_SECTION = """
{profile_section}
"""

HUMAN_TEMPLATE = """## 主题
{topic}

## 要求
- 幻灯片总页数：{slide_count} 页（包含封面和结束页）
- 语言：{language}
- 风格：{style}

## 参考资料
{context}

## 用户补充指令
{extra_prompt}

请生成完整的 PPT 视觉描述 JSON，每页必须包含 layout_type 和 visual_plan。"""


def _build_system_prompt(style: str) -> str:
    """根据风格构建完整的系统提示，注入对应场景设计 profile。"""
    profile_section = get_profile_prompt_section(style)
    return _BASE_SYSTEM_PROMPT + "\n\n## 场景设计指导（以下要求必须严格遵守）\n" + profile_section


class PptChain:
    """PPT 生成链 — Prompt → ChatOpenAI → JSON 解析。

    产出含 layout_type / visual_plan / image_query / chart_data / table_data 的视觉描述，
    驱动 Generator 的设计系统和布局渲染器。
    根据 style 参数动态注入场景设计 profile。
    """

    def __init__(self) -> None:
        self._chain_cache: Any = None
        self._cached_style: str = ""

    @property
    def chain(self):
        """返回 LangChain Runnable，保持与 generation_graph.py 的向后兼容。

        generation_graph 通过 PptChain().chain.ainvoke({...}) 调用，
        返回原始 LLM 字符串，调用方自行做 JSON 解析。
        此处使用通用 prompt（不注入场景 profile），profile 注入在 ainvoke() 中处理。
        """
        if self._chain_cache is None or self._cached_style != "general":
            prompt = ChatPromptTemplate.from_messages([
                ("system", _build_system_prompt("general")),
                ("human", HUMAN_TEMPLATE),
            ])
            self._chain_cache = prompt | create_chat_model() | StrOutputParser()
            self._cached_style = "general"
        return self._chain_cache

    async def ainvoke(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """异步调用链（场景 profile 注入版），返回含视觉计划的丰富大纲。

        此方法为增强入口：根据 style 动态注入场景 design profile 到 system prompt。
        如需原始字符串返回（供调用方自行解析），使用 self.chain.ainvoke(...)。
        """
        style = inputs.get("style", "academic")
        context = inputs.get("context", "")
        extra = inputs.get("extra_prompt", "")

        chain = ChatPromptTemplate.from_messages([
            ("system", _build_system_prompt(style)),
            ("human", HUMAN_TEMPLATE),
        ]) | create_chat_model() | StrOutputParser()

        raw = await chain.ainvoke({
            "topic": inputs.get("topic", ""),
            "style": style,
            "slide_count": inputs.get("slide_count", 10),
            "language": inputs.get("language", "zh"),
            "context": context if context else "（无参考资料，请根据通用知识编排）",
            "extra_prompt": extra if extra else "（无额外指令）",
        })

        logger.info(f"LLM output length: {len(raw)} chars, style={style}")

        outline = safe_json_parse(raw)
        outline["style"] = style
        outline["raw"] = raw

        # 规范化：确保 body 是列表
        outline.setdefault("slides", [])
        for slide in outline.get("slides", []):
            body = slide.get("body", slide.get("content", []))
            if isinstance(body, str):
                body = [body]
            slide["body"] = body
            slide["content"] = body

        return outline
