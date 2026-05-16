# PDF 文档生成设计

> v1.0 | 2026-05-16 | Phase 3 PDF 生成

---

## 一、概述

PDF 生成采用两步策略：LLM 生成结构化内容 → python-docx 构建 .docx → LibreOffice 无头转换为 .pdf。相比直接操作 PDF 库，此方案保证了排版一致性和中文字体支持。

复用 PPT/Word 的 LangGraph 状态图架构，通过 `doc_type` 字段分发。

---

## 二、核心流程

```
POST /ai/pdf/generate
  → quota.consume（扣额度）
  → LangGraph 状态图:
      ├─ retrieve_context（RAG 检索，可选）
      ├─ generate_outline（PdfChain → LLM → JSON 解析）
      ├─ validate_outline（校验 title + sections）
      ├─ build_document（PdfGenerator）:
      │     ├─ python-docx 构建 .docx 临时文件
      │     └─ LibreOffice --headless 转换 → .pdf
      └─ handle_error（失败重试 ≤3 次）
  → file.upload（上传 Java 后端）
  → 失败时 quota.refund（退额度）
```

---

## 三、Chain 设计 (`chains/pdf_chain.py`)

**PdfChain** — Prompt 模板 + LLM 调用 + JSON 结构化输出。

**支持的文档类型：**

| doc_type | 说明 | 结构特点 |
|----------|------|----------|
| `report` | 报告 | title + abstract 章节 + 多个 content 章节 |
| `resume` | 简历 | 个人信息 + 教育经历 + 工作经历 + 技能 |
| `form` | 表单 | title + 描述 + 表格数据 |

**LLM 输出 JSON 结构：**

```json
{
  "title": "文档标题",
  "subtitle": "副标题（可选）",
  "author": "作者（可选）",
  "date": "日期（可选）",
  "sections": [
    {"heading": "章节标题", "content": ["段落1", "段落2"]}
  ],
  "tables": [
    {"caption": "表格标题", "headers": ["列1", "列2"], "rows": [["值1", "值2"]]}
  ]
}
```

---

## 四、生成器设计 (`generator/pdf.py`)

**PdfGenerator** — 两步生成策略。

### 步骤 1：python-docx 构建 .docx

**页面设置：** A4 (21cm × 29.7cm)，1 英寸边距。

**构建顺序：**
1. 标题（居中，26pt，粗体）
2. 副标题 + 作者 + 日期（居中）
3. 分隔线
4. 章节内容（Heading 1 标题 + 段落文本）
5. 表格（可选，含标题 + 表头 + 数据行，Table Grid 样式）

### 步骤 2：LibreOffice 转换

```bash
libreoffice --headless --convert-to pdf --outdir <dir> <file.docx>
```

- 超时：120 秒
- 失败回退：若 LibreOffice 不可用，返回 .docx 文件并记录警告日志

### 风格主题

| 风格 | 标题字体 | 正文字体 | 主色 |
|------|----------|----------|------|
| academic | SimHei | SimSun | #1A3C6E |
| business | Microsoft YaHei | Microsoft YaHei | #1B3A5C |
| creative | Microsoft YaHei | Microsoft YaHei | #E04A36 |

---

## 五、状态图集成

`graph/generation_graph.py` 通过 `state["doc_type"] == "pdf"` 分发：

- `_generate_outline`: 创建 `PdfChain`，传入 `doc_type`、`language` 等参数
- `_validate_outline`: 校验 `title` 非空 + `sections` 至少 1 个
- `_build_document`: 创建 `PdfGenerator`，输出 `.pdf`（或回退 `.docx`）

---

## 六、API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/ai/pdf/generate` | 同步生成 PDF 文档 |

请求体 (`PdfGenerateRequest`) 继承 `GenerateRequest`，扩展字段：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| doc_type | str | 否 | report | report / resume / form |

---

## 七、环境依赖

PDF 生成需要系统安装 LibreOffice：

```bash
# Ubuntu/Debian
apt-get install libreoffice-writer

# Docker
RUN apt-get update && apt-get install -y libreoffice-writer
```

若未安装，生成器会自动回退为 .docx 文件输出。
