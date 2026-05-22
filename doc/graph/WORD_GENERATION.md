# Word 文档生成设计

> v1.0 | 2026-05-16 | Phase 3 Word 生成

---

## 一、概述

Word 生成复用 PPT 生成的整体架构（LangGraph 状态图 + LangChain Chain + python-docx 生成器），通过 `doc_type` 字段在状态图中分发到对应的 Chain 和 Generator。

---

## 二、核心流程

```
POST /ai/word/generate
  → quota.consume（扣额度）
  → LangGraph 状态图:
      ├─ retrieve_context（RAG 检索，可选）
      ├─ generate_outline（WordChain → LLM → JSON 解析）
      ├─ validate_outline（校验 title + sections）
      ├─ build_document（WordGenerator → python-docx → .docx）
      └─ handle_error（失败重试 ≤3 次）
  → file.upload（上传 Java 后端）
  → 失败时 quota.refund（退额度）
```

---

## 三、Chain 设计 (`chains/word_chain.py`)

**WordChain** — Prompt 模板 + LLM 调用 + JSON 结构化输出。

**支持的文档类型：**

| doc_type | 说明 | 结构特点 |
|----------|------|----------|
| `essay` | 论文 | title + abstract + sections + references |
| `report` | 报告 | title + 背景/数据分析/结论 + references |
| `letter` | 信函 | title + 称谓/正文/结束语/署名 |
| `paper` | 学术论文 | title + abstract + 引言/文献综述/方法/结果/讨论/结论 + references |

**LLM 输出 JSON 结构：**

```json
{
  "title": "文档主标题",
  "subtitle": "副标题（可选）",
  "abstract": "摘要（可选，essay/paper 使用）",
  "sections": [
    {"heading": "章节标题", "content": ["段落1", "段落2"]}
  ],
  "references": ["[1] 参考文献"]
}
```

**约束：**
- 每段不少于 50 字，完整的段落文本而非要点
- 总字数控制在 word_count 范围内
- 支持 3 种风格：academic / business / creative

---

## 四、生成器设计 (`generator/word/generator.py`)

**WordGenerator** — 基于 python-docx 构建 .docx 文件。

**页面设置：** A4 (8.27" × 11.69")，1 英寸边距。

**构建顺序：**
1. 标题页（主标题居中 + 副标题 + 日期 + 分页符）
2. 摘要（可选，含"摘要"标题 + 正文 + 分页符）
3. 章节内容（Heading 1 标题 + 段落文本，首行缩进 0.28"，1.5 倍行距）
4. 参考文献（可选）

**3 套风格主题：**

| 风格 | 标题字体 | 正文字体 | 主色 |
|------|----------|----------|------|
| academic | SimHei | SimSun | #1A3C6E |
| business | Microsoft YaHei | Microsoft YaHei | #1B3A5C |
| creative | Microsoft YaHei | Microsoft YaHei | #E04A36 |

---

## 五、状态图集成

`graph/generation_graph.py` 通过 `state["doc_type"] == "word"` 分发：

- `_generate_outline`: 创建 `WordChain`，传入 `doc_type`、`word_count`、`style` 等参数
- `_validate_outline`: 校验 `title` 非空 + `sections` 至少 1 个
- `_build_document`: 创建 `WordGenerator`，输出 `.docx`

---

## 六、API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/ai/word/generate` | 同步生成 Word 文档 |

请求体 (`WordGenerateRequest`) 继承 `GenerateRequest`，扩展字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| doc_type | str | 否 | essay | essay / report / letter / paper |
| word_count | int | 否 | 2000 | 目标字数，范围 500–10000 |
