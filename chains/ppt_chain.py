"""PPT 大纲生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。

产出含 layout_type / visual_plan / image_query 的丰富结构，
驱动设计系统和布局渲染器生成视觉丰富的幻灯片。
"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse

SYSTEM_PROMPT = """你是一个世界级的演示文稿设计专家，擅长信息架构与视觉叙事。你的任务是为每一页幻灯片生成精细的视觉描述，而不仅仅是罗列要点。

## 核心原则
1. **叙事驱动**: 演示文稿应该讲一个故事，每页都是故事的自然推进
2. **视觉优先**: 每页都要指定 layout_type 和 visual_plan，用视觉元素强化信息
3. **精确指引**: image_query 必须是可搜索的英文关键词，不要写"相关图片"这种空泛描述
4. **绝不用占位符**: 永远不要输出 "[此处插入图片]"、"TODO" 这类占位文字
5. **图片覆盖率**: 除封面和结束页外，至少 40% 的内容页必须使用 text_image、image_full 或 grid_cards 等需要配图的布局，且 image_query 必须为非空可搜索英文关键词

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
| text_image | 图文混排，需配图说明 | 左文右图或上图下文 |
| image_full | 全图背景+文字叠加 | 冲击力强的引述或数据 |
| two_column | 双栏对比或并列 | 优劣对比、前后对比 |
| grid_cards | 3-4个并列要点卡片 | 特性列表、方案对比 |
| timeline | 时间线/步骤 | 发展历程、操作流程 |
| quote | 金句/引用 | 名人名言、核心观点 |
| summary | 结束页/总结 | 谢谢观看、联系方式 |

## two_column 双栏格式（重要）
使用 two_column 布局时，body 必须恰好包含 2 个元素：
- body[0]: 左栏内容，各要点用换行符 \n 分隔
- body[1]: 右栏内容，各要点用换行符 \n 分隔
- left_label / right_label: 可选，分别为左右栏的标签标题
示例：
```
"body": [
  "固定功能管线\n- 渲染步骤由硅片固化电路决定\n- 灵活性低，难以实现动态光影",
  "统一着色器架构\n- 顶点/像素/几何计算单元统一调度\n- 高度并行化，奠定现代通用计算基础"
],
"left_label": "传统架构",
"right_label": "现代架构"
```

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

## image_query 编写规范
- 使用英文关键词，3-6个词
- 描述具体场景或抽象概念，而非泛泛描述
- 好: "medical AI diagnosis deep learning visualization"
- 差: "相关图片"
- 纯文字页(strategy=BASIC_GRAPHICS_ONLY)无需填 image_query

## 风格适配
- academic: 克制装饰，清晰层级，深蓝/深灰为主
- business: 精确对齐，数据醒目，专业配色
- creative: 大胆用色，动态构图，曲面/圆形装饰
- minimal: 大量留白，极少装饰，字体层级清晰
- tech: 科技感线条，渐变背景，霓虹强调色
- warm: 暖色调，手绘感装饰，圆角形状

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
      "image_position": "",
      "notes": ""
    }},
    {{
      "page_number": 3,
      "layout_type": "text_image",
      "title": "机器学习诊断流程",
      "body": [
        "数据采集：多模态数据输入",
        "特征提取：深度学习自动提取",
        "模型推理：集成多专家模型"
      ],
      "visual_plan": {{
        "strategy": "MEDIA_REQUIRED",
        "layout_hint": "text_left_image_right",
        "bg_treatment": "solid",
        "decorations": [
          {{"type": "line", "position": "below_title", "color": "accent"}}
        ]
      }},
      "image_query": "machine learning medical diagnosis workflow",
      "image_position": "right",
      "notes": "重点强调特征提取环节"
    }}
  ]
}}
```

请严格按照以上要求生成完整的 PPT 页面描述 JSON。"""

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


class PptChain:
    """PPT 生成链 — Prompt → ChatOpenAI → JSON 解析。

    产出含 layout_type / visual_plan / image_query 的视觉描述，
    驱动 Generator 的设计系统和布局渲染器。
    """

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
        """异步调用链，返回含视觉计划的丰富大纲。"""
        style = inputs.get("style", "academic")
        context = inputs.get("context", "")
        extra = inputs.get("extra_prompt", "")

        raw = await self.chain.ainvoke({
            "topic": inputs.get("topic", ""),
            "style": style,
            "slide_count": inputs.get("slide_count", 10),
            "language": inputs.get("language", "zh"),
            "context": context if context else "（无参考资料，请根据通用知识编排）",
            "extra_prompt": extra if extra else "（无额外指令）",
        })

        logger.info(f"LLM output length: {len(raw)} chars")

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
