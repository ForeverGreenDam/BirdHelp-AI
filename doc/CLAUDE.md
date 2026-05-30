# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BirdHelp AI 模块 — 大学生文档助手的 Python AI 能力层。与 Java 后端通过 HTTP 内部协议协作，负责大模型调用、RAG（检索增强生成）、Office 文件生成（PPT/Word/PDF）、OCR。

完整架构和开发计划参见 `DESIGN.md`。

## Commands

```bash
# 开发服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生产运行
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 3

# 安装依赖
pip install -r requirements.txt
```

## Architecture

**分层结构** (详见 DESIGN.md 第三章):
- `api/` — FastAPI 路由层，对外暴露 `/ai/*` 接口，由 Java 后端代理转发
- `chains/` — LangChain Chain 定义（ppt_chain / word_chain / pdf_chain / chat_chain），封装 Prompt + LLM + OutputParser
- `graph/` — LangGraph 状态图（generation_graph: RAG→生成→检查→重试）
- `modify/` — 对话修改文档模块（LLM 修改大纲 → Generator 重建文件，无 QA，详见 `doc/CHAT_MODIFY_DESIGN.md`）
- `rag/` — RAG 管线（ingestion → retrieval → vector_store）
- `generator/` — Office 文件生成：PPT（python-pptx + 设计系统 + 11种布局 + 7套场景profile + 图表/表格）、Word/PDF（python-docx + DocxBuilder + matplotlib 图表 + LibreOffice）
- `broker/` — RabbitMQ 消费者（消费文档生成任务 → 执行生成 → HTTP 回调通知 Java，回调时携带 outline）
- `client/` — 调用 Java 后端内部接口（quota / file / task callback / outline / chat session）
- `core/` — 基础设施（ChatModel 工厂、Embedding 工厂、Schemas、异常）

**核心流程**: Java → RabbitMQ → broker 消费 → LangGraph 状态图 → RAG 检索(可选) → LangChain Chain → LLM 生成 → 文件生成器 → 上传 Java 后端 → HTTP 回调通知结果

**RAG 管线**: 文件上传 → LangChain Loader 解析 → 清洗 → RecursiveCharacterTextSplitter → Embedding → Redis Stack → 生成时混合检索 (向量+BM25+RRF) → 注入 Prompt

## Java Backend Contract

与 Java 后端的双向通信均使用 **RSA-SHA256 签名**（2048 位），无传统 Token。

**AI → Java**（详见 `doc/JAVA_CALLER.md`）:

| 接口 | 调用时机 |
|------|---------|
| `POST /api/internal/quota/consume` | 生成开始前扣额度 |
| `POST /api/internal/quota/refund` | 生成失败退额度 |
| `POST /api/internal/file/upload` | 文件上传（素材 / 生成结果，携带 versionOf 建立版本链） |
| `GET /api/internal/file/{id}/download` | 文件下载 |
| `DELETE /api/internal/file/{id}` | 软删除文件 |
| `POST /api/internal/task/callback` | 异步任务完成/失败回调（携带 outline） |
| `POST /api/internal/task/progress` | 异步任务进度推送（可选） |
| `GET /api/internal/file/{id}/outline` | 获取文档大纲（对话修改时使用） |
| `PUT /api/internal/file/{id}/outline` | 更新文档大纲（修改完成后） |
| `POST /api/internal/chat/session` | 获取或创建对话会话 |
| `POST /api/internal/chat/session/{id}/messages` | 追加对话消息 |

**Java → AI**（详见 `doc/PYTHON_CALLER.md`）:

| 接口 | 说明 |
|------|------|
| `POST /ai/material/upload` | 上传素材并触发 RAG 摄取 |
| `DELETE /ai/material/{id}` | 删除素材（回收站 + 向量清理） |
| `POST /ai/ppt/generate` | ❌ 已移除 → RabbitMQ `doc.generate.ppt` |
| `POST /ai/word/generate` | ❌ 已移除 → RabbitMQ `doc.generate.word` |
| `POST /ai/pdf/generate` | ❌ 已移除 → RabbitMQ `doc.generate.pdf` |
| `POST /ai/chat/modify` | 对话式修改文档（Phase 5） |
| `POST /ai/ocr/recognize` | OCR 识别（Phase 4） |
| `GET /ai/task/{task_id}/status` | 任务状态查询（Phase 7） |

> **文档生成已异步化**：Java 后端通过 RabbitMQ 发送生成任务，Python broker 模块消费执行，完成后 HTTP 回调。旧 HTTP 生成接口已移除（详见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`）。

> 两个方向使用**独立的**密钥对，不可混用。AI 模块对外暴露的接口由 Java 后端代理转发给前端，AI 模块不直接面向用户。

## Key Tech Stack

- **FastAPI** + Uvicorn (Web)
- **LangChain** + **LangGraph** (LLM 编排、RAG、工作流)
- **langchain-openai** (ChatOpenAI 兼容协议，对接 DeepSeek/通义千问/GPT-4o)
- **Redis Stack** 向量数据库
- **python-pptx** / **python-docx** / **LibreOffice** (文件生成)
- **matplotlib** (图表渲染，Word/PDF 嵌入)
- **PaddleOCR** (OCR)
- **RabbitMQ** + **aio-pika** (异步文档生成消息队列)
- **httpx** (async HTTP 客户端)
- **pydantic-settings** / **loguru** (配置 / 日志)
