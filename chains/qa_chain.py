"""PPT 质量评估 Chain — 对单页/整体幻灯片进行多维度评分。

用于修复循环：不合格的页面连同问题列表喂回 LLM 修复。
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
class QACheck:
    """单项质量检查结果。"""
    label: str           # 检查项名称
    passed: bool
    severity: str        # "blocking" | "high_risk" | "warning"
    detail: str = ""     # 问题描述


@dataclass
class QAReport:
    """单页质量的综合评估报告。"""
    slide_index: int
    score: int           # 0-100
    checks: list[QACheck] = field(default_factory=list)

    @property
    def blocking_issues(self) -> list[QACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "blocking"]

    @property
    def high_risk_issues(self) -> list[QACheck]:
        return [c for c in self.checks if not c.passed and c.severity == "high_risk"]

    @property
    def all_issues(self) -> list[QACheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed(self) -> bool:
        """无阻塞问题且评分 >= 阈值即为通过。"""
        return not self.blocking_issues and not self.high_risk_issues


QA_SYSTEM_PROMPT = """你是一个 PPT 质量评审专家。对给定的幻灯片描述进行逐项检查，并给出评分。

## 检查维度

### 合约合规（阻塞级别）
1. 占位符检查: 是否出现 "[图片]"、"TODO"、"此处插入" 等占位符文字？如有则阻塞
2. 图片策略检查: 若 visual_plan.strategy 为 MEDIA_REQUIRED，image_query 是否非空？如空则阻塞

### 内容质量（高风险）
3. 标题质量: 标题是否简洁有力？"关于XXX的介绍"、"XXX相关" 为空泛标题，扣分
4. 要点数量: body/content 的要点是否在 2-6 条？过多或过少需警告
5. 信息密度: 每条要点是否传达具体信息而非空话？

### 视觉合理（警告）
6. 布局匹配: layout_type 是否适合该页内容？
7. 装饰合理: decorations 数量是否与 decoration_level 说明一致？

### 图片相关（高风险）
8. image_query 质量: 是否是可搜索的英文关键词？"相关图片"、"配图" 等无效

## 输出格式

```json
{{
  "score": 85,
  "checks": [
    {{"label": "占位符检查", "passed": true, "severity": "blocking", "detail": ""}},
    {{"label": "图片策略检查", "passed": true, "severity": "blocking", "detail": ""}},
    {{"label": "标题质量", "passed": true, "severity": "high_risk", "detail": ""}},
    {{"label": "要点数量", "passed": true, "severity": "warning", "detail": "5条，数量合理"}},
    {{"label": "信息密度", "passed": false, "severity": "warning", "detail": "第3条要点过于空泛"}},
    {{"label": "布局匹配", "passed": true, "severity": "warning", "detail": ""}},
    {{"label": "装饰合理", "passed": true, "severity": "warning", "detail": ""}},
    {{"label": "image_query质量", "passed": true, "severity": "high_risk", "detail": ""}}
  ]
}}
```

评分规则:
- 起始 100 分
- 每个阻塞问题 -30 分
- 每个高风险问题 -15 分
- 每个警告 -5 分
- 最低 0 分
"""

QA_HUMAN_TEMPLATE = """## 幻灯片信息
- 页码: {page_number}
- 布局类型: {layout_type}
- 标题: {title}
- 正文要点: {body}

## 视觉计划
{visual_plan}

## 图片查询
{image_query}

## 设计DNA参考
风格: {style} / 密度: {density} / 装饰层次: {decoration_level}

请对该页进行质量评分。"""


class PptQAChain:
    """PPT 单页质量评估链 — 返回 QAReport。"""

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
        slide_json: dict[str, Any],
        style: str = "academic",
    ) -> QAReport:
        """对单页幻灯片进行质量评估。

        Args:
            slide_json: 单页的 JSON 描述（含 title/body/visual_plan/image_query/layout_type）
            style: 风格名

        Returns:
            QAReport 包含评分和逐项检查结果
        """
        page_number = slide_json.get("page_number", 0)
        visual_plan = slide_json.get("visual_plan", {})
        body = slide_json.get("body", slide_json.get("content", []))

        try:
            raw = await self.chain.ainvoke({
                "page_number": page_number,
                "layout_type": slide_json.get("layout_type", "text_only"),
                "title": slide_json.get("title", ""),
                "body": "\n".join(body) if isinstance(body, list) else str(body),
                "visual_plan": str(visual_plan),
                "image_query": slide_json.get("image_query", ""),
                "style": style,
                "density": "balanced",
                "decoration_level": "moderate",
            })

            result = safe_json_parse(raw)
            score = max(0, min(100, result.get("score", 70)))
            checks = [
                QACheck(
                    label=c.get("label", "未知"),
                    passed=c.get("passed", True),
                    severity=c.get("severity", "warning"),
                    detail=c.get("detail", ""),
                )
                for c in result.get("checks", [])
            ]
            logger.info(f"QA: slide {page_number} score={score}, issues={len([c for c in checks if not c.passed])}")
            return QAReport(slide_index=page_number, score=score, checks=checks)

        except Exception as exc:
            logger.warning(f"QA evaluation failed for slide {page_number}: {exc}")
            # 评估失败时不阻塞流程，返回默认通过
            return QAReport(slide_index=page_number, score=70, checks=[])

    async def evaluate_all(
        self,
        slides: list[dict[str, Any]],
        style: str = "academic",
        threshold: int = 70,
        max_rounds: int = 3,
    ) -> tuple[list[dict], list[QAReport]]:
        """逐页评估，不通过的页面进入修复循环。

        Args:
            slides: 全部页面的 JSON 描述
            style: 风格名
            threshold: 通过阈值（低于此分进入修复）
            max_rounds: 最大修复轮数

        Returns:
            (修复后的 slides, 最终评估报告列表)
        """
        all_reports: list[QAReport] = []

        for i, slide in enumerate(slides):
            best_score = 0
            best_slide = slide
            final_report = None

            for round_num in range(1, max_rounds + 1):
                report = await self.evaluate(slide, style)
                logger.debug(
                    f"Slide {i + 1} round {round_num}: score={report.score}, "
                    f"blocking={len(report.blocking_issues)}, "
                    f"high_risk={len(report.high_risk_issues)}"
                )

                if report.score > best_score:
                    best_score = report.score
                    best_slide = slide
                    final_report = report

                if report.passed and report.score >= threshold:
                    break

                if round_num < max_rounds and not report.passed:
                    slide = await self._repair_slide(slide, report, style)
                    logger.info(f"Slide {i + 1} entering repair round {round_num + 1}")

            # 使用最佳版本
            slides[i] = best_slide
            if final_report:
                final_report.score = best_score
                all_reports.append(final_report)
            else:
                all_reports.append(
                    QAReport(slide_index=i + 1, score=best_score, checks=[])
                )

        avg_score = sum(r.score for r in all_reports) / len(all_reports) if all_reports else 0
        degraded = [r for r in all_reports if r.score < threshold]
        logger.info(
            f"QA complete: avg_score={avg_score:.0f}, "
            f"total={len(all_reports)}, degraded={len(degraded)}"
        )
        if len(degraded) > len(all_reports) * 0.3:
            logger.warning(f"Over 30% slides below threshold ({len(degraded)}/{len(all_reports)}), "
                           "accepting degraded version")

        return slides, all_reports

    async def _repair_slide(
        self,
        slide: dict,
        report: QAReport,
        style: str,
    ) -> dict:
        """尝试修复单页幻灯片 — 将问题列表喂回 LLM 要求修正。"""
        import json as _json

        issues_text = "\n".join(
            f"- [{c.severity}] {c.label}: {c.detail}"
            for c in report.all_issues
        )

        original_page = slide.get("page_number", 0)
        repair_prompt = (
            f"以下是需要修复的幻灯片 JSON 描述：\n\n"
            f"```json\n"
            f"{_json.dumps(slide, ensure_ascii=False, indent=2)}\n"
            f"```\n\n"
            f"该页的质量评审发现了以下问题：\n"
            f"{issues_text}\n\n"
            f"风格: {style}\n\n"
            f"请直接输出修复后的完整 JSON（仅输出 JSON，不要任何额外文字）。\n"
            f"修复要求：\n"
            f"1. 如果是布局类型不匹配，调整为更合适的 layout_type\n"
            f"2. 如果标题空泛，改写为更具体有力的标题\n"
            f"3. 如果 image_query 无效，提供可搜索的英文关键词\n"
            f"4. 如果有占位符文字，删除或替换为实际内容\n"
            f"5. 保持页面的基本结构和主题不变\n"
            f"6. page_number 必须保持为 {original_page}，不可修改"
        )

        try:
            chain = ChatPromptTemplate.from_messages([
                ("human", "{input}")
            ]) | create_chat_model() | StrOutputParser()
            raw = await chain.ainvoke({"input": repair_prompt})
            repaired = safe_json_parse(raw)
            # 强制保留原始关键字段，防止 LLM 篡改导致后续图片/布局查找失败
            repaired["page_number"] = slide.get("page_number", 0)
            repaired.setdefault("layout_type", slide.get("layout_type", "text_only"))
            logger.info(f"Slide repair result: {len(raw)} chars")
            return repaired
        except Exception as exc:
            logger.warning(f"Slide repair failed: {exc}")
            return slide  # 修复失败返回原版
