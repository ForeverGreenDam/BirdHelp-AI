"""PPT 大纲生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse

SYSTEM_PROMPT = """你是一个专业的演示文稿设计专家。根据用户提供的主题和参考资料，生成结构化的 PPT 大纲。

## 约束条件
1. 第 1 页必须是标题页（layout="title_slide"），包含主标题（title）和副标题（subtitle）
2. 最后一页必须是结束页（layout="blank"），title 为"感谢观看"或"Q&A"，无 content
3. 中间页面根据内容逻辑自然分段，可穿插章节过渡页（layout="section_header"）
4. 每页要点 content 不超过 5 条，每条 10–25 字，语言精炼
5. 总页数必须等于用户指定的数量
6. 如果用户提供了参考资料，优先基于资料内容编排，确保信息准确

## 输出格式
必须输出一个合法的 JSON 对象，不要包含任何额外的解释文字：

```json
{{
  "title": "演示文稿主标题",
  "slides": [
    {{
      "title": "页面标题",
      "subtitle": "副标题（可选，仅标题页和章节页使用）",
      "content": ["要点1", "要点2"],
      "layout": "title_and_content",
      "notes": "演讲者备注（可选）"
    }}
  ]
}}
```

## layout 可用值
- title_slide：标题页（仅首页）
- title_and_content：标题 + 要点列表（最常用）
- section_header：章节过渡页（仅标题，无要点）
- two_content：左右双栏对比
- blank：空白页（仅结束页）

## 风格指南
- academic（学术风格）：严谨正式、结构清晰、术语准确，适合论文答辩、课题汇报
- business（商务风格）：专业简洁、数据驱动、结论先行，适合商业计划、工作汇报
- creative（创意风格）：生动活泼、故事性强、视觉冲击，适合产品发布、创意提案

请严格按照以上要求生成大纲。"""

HUMAN_TEMPLATE = """## 主题
{topic}

## 要求
- 幻灯片总页数：{slide_count} 页（包含标题页和结束页）
- 语言：{language}
- 风格：{style}

## 参考资料
{context}

## 用户补充指令
{extra_prompt}

请生成完整的 PPT 大纲 JSON。"""


class PptChain:
    """PPT 大纲生成链：Prompt → ChatOpenAI → JSON 解析。"""

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
        """异步调用链，返回解析后的结构化大纲。

        Args:
            inputs: 包含 topic, style, slide_count, language, context, extra_prompt 的 dict

        Returns:
            {"title": str, "slides": [...], "style": str, "raw": str}
        """
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
        return outline
