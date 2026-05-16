"""PDF 内容生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse

SYSTEM_PROMPT = """你是一个专业的文档排版专家，擅长根据用户需求生成结构清晰的 PDF 文档内容。

## 支持的文档类型
- report（报告）：包含标题、摘要、多个章节段落，适合研究报告、工作总结
- resume（简历）：包含个人信息、教育经历、工作经历、技能列表，适合个人简历
- form（表单）：包含标题、描述、表格数据，适合数据报表、登记表

## 输出格式
必须输出一个合法的 JSON 对象，不要包含任何额外的解释文字：

```
{{
  "title": "文档标题",
  "subtitle": "副标题（可选）",
  "author": "作者（可选）",
  "date": "日期（可选）",
  "sections": [
    {{
      "heading": "章节标题",
      "content": ["段落1", "段落2"]
    }}
  ],
  "tables": [
    {{
      "caption": "表格标题（可选）",
      "headers": ["列1", "列2"],
      "rows": [
        ["值1", "值2"]
      ]
    }}
  ]
}}
```

## 文档类型指南
- report（报告）：需包含一个 abstract 摘要章节，各章节内容逻辑连贯，语言正式
- resume（简历）：个人信息章节包含姓名、联系方式，教育经历按时间倒序，技能使用要点列表
- form（表单）：以表格为核心展示数据，标题和描述说明用途，表格行列清晰

请严格按照以上要求生成文档内容。"""

HUMAN_TEMPLATE = """## 主题
{topic}

## 要求
- 文档类型：{doc_type}
- 语言：{language}

## 参考资料
{context}

## 用户补充指令
{extra_prompt}

请生成完整的 PDF 文档内容 JSON。"""


class PdfChain:
    """PDF 内容生成链：Prompt → ChatOpenAI → JSON 解析。"""

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
        """异步调用链，返回解析后的结构化文档内容。

        Args:
            inputs: 包含 topic, doc_type, language, context, extra_prompt 的 dict

        Returns:
            {"title": str, "sections": [...], "raw": str}
        """
        doc_type = inputs.get("doc_type", "report")
        context = inputs.get("context", "")
        extra = inputs.get("extra_prompt", "")

        raw = await self.chain.ainvoke({
            "topic": inputs.get("topic", ""),
            "doc_type": doc_type,
            "language": inputs.get("language", "zh"),
            "context": context if context else "（无参考资料，请根据通用知识编排）",
            "extra_prompt": extra if extra else "（无额外指令）",
        })

        logger.info(f"LLM output length: {len(raw)} chars")

        outline = safe_json_parse(raw)
        outline["raw"] = raw
        return outline
