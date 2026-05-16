"""Word 文档大纲生成 Chain — Prompt 模板 + LLM 调用 + JSON 结构化输出。"""

from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse

SYSTEM_PROMPT = """你是一个专业的文档写作专家。根据用户提供的主题和参考资料，生成结构化的 Word 文档内容。

## 约束条件
1. 文档结构必须包含标题（title）和多个章节（sections）
2. 每个章节包含 heading（章节标题）和 content（段落文本数组）
3. content 中的每一条应为完整的段落文本（不少于 50 字），而非要点列表
4. 总字数必须控制在用户指定的范围内
5. 如果用户提供了参考资料，优先基于资料内容编排，确保信息准确
6. 语言表达流畅、逻辑清晰，符合正式文档写作规范

## 输出格式
必须输出一个合法的 JSON 对象，不要包含任何额外的解释文字：

```
{{
  "title": "文档主标题",
  "subtitle": "文档副标题（可选）",
  "abstract": "摘要内容（可选，仅 essay/paper 类型使用）",
  "sections": [
    {{
      "heading": "第一章 引言",
      "content": ["段落文本1", "段落文本2"]
    }}
  ],
  "references": ["参考文献1", "参考文献2（可选）"]
}}
```

## 文档类型说明
- essay（论文）：需要包含摘要（abstract）、引言、正文、结论等结构，引用参考文献
- report（报告）：需要包含背景、数据分析、结论与建议等结构，以数据和分析为导向
- letter（信函）：包含称谓、正文、结束语、署名等，语言得体庄重
- paper（学术论文）：需要包含摘要（abstract）、关键词、引言、文献综述、方法、结果、讨论、结论、参考文献等完整学术结构

## 风格指南
- academic（学术风格）：严谨正式、逻辑严密、术语准确，适合学术写作
- business（商务风格）：专业简洁、条理清晰、结论先行，适合商业文档
- creative（创意风格）：生动活泼、富有感染力、语言优美，适合创意文案

请严格按照以上要求生成文档内容。"""

HUMAN_TEMPLATE = """## 主题
{topic}

## 要求
- 文档类型：{doc_type}
- 目标字数：{word_count} 字
- 语言：{language}
- 风格：{style}

## 参考资料
{context}

## 用户补充指令
{extra_prompt}

请生成完整的 Word 文档内容 JSON。"""


class WordChain:
    """Word 文档大纲生成链：Prompt → ChatOpenAI → JSON 解析。"""

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
            inputs: 包含 topic, doc_type, word_count, style, language, context, extra_prompt 的 dict

        Returns:
            {"title": str, "subtitle": str, "abstract": str, "sections": [...], "references": [...], "style": str, "raw": str}
        """
        style = inputs.get("style", "academic")
        doc_type = inputs.get("doc_type", "essay")
        context = inputs.get("context", "")
        extra = inputs.get("extra_prompt", "")

        raw = await self.chain.ainvoke({
            "topic": inputs.get("topic", ""),
            "doc_type": doc_type,
            "word_count": inputs.get("word_count", 2000),
            "style": style,
            "language": inputs.get("language", "zh"),
            "context": context if context else "（无参考资料，请根据通用知识编排）",
            "extra_prompt": extra if extra else "（无额外指令）",
        })

        logger.info(f"LLM output length: {len(raw)} chars")

        outline = safe_json_parse(raw)
        outline["style"] = style
        outline["doc_type"] = doc_type
        outline["raw"] = raw
        return outline
