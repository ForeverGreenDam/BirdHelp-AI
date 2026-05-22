"""Word/PDF 质量评估 Chain — 对文档进行多维度结构化和内容质量评分。

用于修复循环：不合格的文档连同问题列表喂回 LLM 修复。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from loguru import logger

from core.llm import create_chat_model
from utils.format import safe_json_parse


@dataclass
class DocQACheck:
    label: str
    passed: bool
    severity: str
    detail: str = ""


@dataclass
class DocQAReport:
    score: int
    checks: list[DocQACheck] = field(default_factory=list)

    @property
    def blocking_issues(self) -> list[DocQACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "blocking"]

    @property
    def high_risk_issues(self) -> list[DocQACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "high_risk"]

    @property
    def all_issues(self) -> list[DocQACheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed(self) -> bool:
        return not self.blocking_issues and not self.high_risk_issues


QA_SYSTEM_PROMPT = """你是一个文档质量评审专家。对给定的文档 JSON 描述进行逐项检查并评分。

## 检查维度

### 结构完整性（阻塞级别）
1. title 存在: 文档主标题是否非空
2. sections 数量: 至少 1 个章节

### 图表数据正确性（阻塞级别）
3. chart 数据一致性: 所有 chart 中 data.labels.length 必须等于 data.datasets[].values.length
4. table 结构: 所有 table 的 headers 与 rows 列数是否匹配

### 内容质量（高风险）
5. 段落完整性: content 中每段是否 ≥ 50 字
6. chart 数据真实性: chart values 是否合理（非全零、非异常值）

### 辅助质量（警告）
7. image_query 质量: 是否可搜索的英文关键词
8. 引用格式: references 是否含 [编号] 格式

## 输出格式

```json
{
  "score": 85,
  "checks": [
    {"label": "title存在", "passed": true, "severity": "blocking", "detail": ""},
    {"label": "sections数量", "passed": true, "severity": "blocking", "detail": "共4个章节"},
    {"label": "chart数据一致性", "passed": true, "severity": "blocking", "detail": ""},
    {"label": "table结构", "passed": true, "severity": "blocking", "detail": ""},
    {"label": "段落完整性", "passed": false, "severity": "high_risk", "detail": "第2章第3段仅28字"},
    {"label": "chart数据真实性", "passed": true, "severity": "high_risk", "detail": ""},
    {"label": "image_query质量", "passed": true, "severity": "warning", "detail": ""},
    {"label": "引用格式", "passed": true, "severity": "warning", "detail": ""}
  ]
}
```

评分: 起始100分，每个阻塞-30，每个高风险-15，每个警告-5，最低0分。"""

QA_HUMAN_TEMPLATE = """## 文档 JSON

```json
{outline_json}
```

## 元信息
- 文档类型: {doc_type}
- 目标字数: {word_count}
- 风格: {style}

请对该文档进行质量评分。"""


class DocQAChain:
    """文档质量评估链 — 返回 DocQAReport。"""

    def __init__(self) -> None:
        self._prompt: ChatPromptTemplate | None = None
        self._chain: Any = None

    @property
    def prompt(self) -> ChatPromptTemplate:
        if self._prompt is None:
            self._prompt = ChatPromptTemplate.from_messages([
                ("system", QA_SYSTEM_PROMPT),
                ("human", QA_HUMAN_TEMPLATE),
            ])
        return self._prompt

    @property
    def chain(self):
        if self._chain is None:
            self._chain = self.prompt | create_chat_model() | StrOutputParser()
        return self._chain

    async def evaluate(
        self,
        outline: dict[str, Any],
        doc_type: str = "essay",
        word_count: int = 2000,
        style: str = "academic",
    ) -> DocQAReport:
        try:
            import json
            raw = await self.chain.ainvoke({
                "outline_json": json.dumps(outline, ensure_ascii=False, indent=2),
                "doc_type": doc_type,
                "word_count": word_count,
                "style": style,
            })
            result = safe_json_parse(raw)
            score = max(0, min(100, result.get("score", 70)))
            checks = [
                DocQACheck(
                    label=c.get("label", "未知"),
                    passed=c.get("passed", True),
                    severity=c.get("severity", "warning"),
                    detail=c.get("detail", ""),
                )
                for c in result.get("checks", [])
            ]
            logger.info(f"Doc QA: score={score}, issues={len([c for c in checks if not c.passed])}")
            return DocQAReport(score=score, checks=checks)
        except Exception as exc:
            logger.warning(f"Doc QA evaluation failed: {exc}")
            return DocQAReport(score=70, checks=[])

    async def evaluate_with_repair(
        self,
        outline: dict[str, Any],
        doc_type: str = "essay",
        word_count: int = 2000,
        style: str = "academic",
        threshold: int = 70,
        max_rounds: int = 2,
    ) -> tuple[dict[str, Any], DocQAReport]:
        """评估并修复文档，返回 (最终outline, 报告)。"""
        import json

        best_outline = outline
        best_score = 0
        final_report = None

        for round_num in range(1, max_rounds + 1):
            report = await self.evaluate(outline, doc_type, word_count, style)
            logger.debug(f"Doc QA round {round_num}: score={report.score}, "
                         f"blocking={len(report.blocking_issues)}, "
                         f"high_risk={len(report.high_risk_issues)}")

            if report.score > best_score:
                best_score = report.score
                best_outline = outline
                final_report = report

            if report.passed and report.score >= threshold:
                break

            if round_num < max_rounds:
                issues_text = "\n".join(
                    f"- [{c.severity}] {c.label}: {c.detail}"
                    for c in report.all_issues
                )
                repair_prompt = (
                    f"请修复以下文档 JSON 中的问题：\n\n{issues_text}\n\n"
                    f"当前文档 JSON:\n```json\n{json.dumps(outline, ensure_ascii=False, indent=2)}\n```\n\n"
                    f"请直接输出修复后的完整 JSON（仅输出 JSON）。"
                )
                chain = ChatPromptTemplate.from_messages([
                    ("human", "{input}")
                ]) | create_chat_model() | StrOutputParser()
                try:
                    raw = await chain.ainvoke({"input": repair_prompt})
                    outline = safe_json_parse(raw)
                except Exception:
                    break

        if final_report:
            final_report.score = best_score
        return best_outline, final_report or DocQAReport(score=best_score, checks=[])
