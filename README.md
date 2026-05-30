# BirdHelp AI 🐦

> ⚠️ **分支：`agent-refactor`** — 此分支与 `master` 有重大架构差异，详见下方对比。

**大学生文档助手 — AI 能力层**

基于 FastAPI + LangChain + LangGraph ReAct Agent 的智能文档生成服务，支持 PPT / Word / PDF 的全自动生成。采用 Agent 自主编排模式（检索→生成→图表→配图→QA→构建），集成 RAG（检索增强生成）混合检索。通过 RabbitMQ 异步消息队列与 Java 后端协作，提供 RSA-SHA256 双向签名认证。

---

## 🔀 与 `master` 分支的差异

| 维度 | `master`（Workflow） | `agent-refactor`（Agent） |
|---|---|---|
| **编排方式** | LangGraph StateGraph 固定流水线 | LangGraph ReAct Agent 自主编排 |
| **执行顺序** | 代码硬编码（代码决定每一步） | LLM 自主决定工具调用顺序 |
| **重试策略** | 固定上限 3 次 | LLM 自行判断是否需要重试 |
| **步骤跳过** | 代码 if/else 判断 | LLM 根据任务自主跳过 |
| **核心模块** | `graph/generation_graph.py` | `graph/agent.py` |
| **消费者** | 调用固定 Graph 的 `ainvoke` | 调用 Agent 的 `orchestrator.run` |
| **进度推送** | 按 Graph 节点 | 按 Agent 工具调用 |

**关键代码变更：**

```
graph/generation_graph.py   →  graph/agent.py        (新建，ReAct Agent)
broker/consumer.py          →  broker/consumer.py    (修改，_run_generation 改用 Agent)
```

**Agent 的 6 个工具：** `retrieve_knowledge` `generate_outline` `render_charts` `fetch_images` `evaluate_quality` `build_document`

---

---

## 功能特性

- **📊 PPT 生成** — 输入主题即可自动生成结构化演示文稿，支持学术/商务/创意 3 种风格、5 种布局，16:9 宽屏格式
- **📝 Word 生成** — 支持论文/报告/信件/文章 4 种文档类型，自动生成封面、摘要、正文、参考文献等完整结构
- **📄 PDF 生成** — 支持报告/简历/表单 3 种类型，通过 LibreOffice 无头转换保证排版一致性
- **🔍 RAG 混合检索** — 向量检索 + BM25 关键词检索 + RRF 融合 + MultiQuery 查询重写，上传素材即可增强生成质量
- **📚 素材管理** — 支持 PDF/DOCX/PPTX/TXT 多格式上传，自动解析、切片、向量化入库，按用户隔离索引
- **🔐 安全认证** — RSA-SHA256 (2048-bit) 双向签名认证，无传统 Token
- **🐳 Docker 部署** — 一键 `docker compose up -d`，内置 LibreOffice + 健康检查

---

## 技术栈

| 领域 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| AI 编排 | LangChain + LangGraph (ReAct Agent) |
| LLM 接入 | langchain-openai (兼容 OpenAI / DeepSeek / 通义千问) |
| 嵌入模型 | OpenAI Embeddings / 通义 text-embedding-v4 |
| 向量数据库 | Redis Stack |
| PPT 生成 | python-pptx |
| Word 生成 | python-docx |
| PDF 生成 | python-docx → LibreOffice 无头转换 |
| 文档解析 | PyPDF / python-docx / python-pptx |
| HTTP 客户端 | httpx (async) |
| 认证加密 | cryptography (RSA-SHA256) |
| 日志 | loguru |

---

## 项目结构

```
BirdHelp/
├── main.py                  # FastAPI 应用入口
├── config.py                # 全局配置 (pydantic-settings)
├── requirements.txt         # Python 依赖
├── Dockerfile               # Docker 镜像
├── docker-compose.yml       # Docker Compose 编排
│
├── api/                     # FastAPI 路由层
│   ├── material.py          # 素材上传/删除/重索引/向量清理
│   ├── ppt.py               # PPT 生成接口
│   ├── word.py              # Word 生成接口
│   └── pdf.py               # PDF 生成接口
│
├── chains/                  # LangChain Chain 定义
│   ├── ppt_chain.py         # PPT 大纲生成 Chain
│   ├── word_chain.py        # Word 内容生成 Chain
│   └── pdf_chain.py         # PDF 内容生成 Chain
│
├── graph/                   # Agent 编排层
│   └── agent.py             # ReAct Agent — 自主编排文档生成全流程
│
├── rag/                     # RAG 管线
│   ├── ingestion.py         # 文档解析、切片、向量化入库
│   ├── retrieval.py         # 混合检索 (向量 + BM25 + RRF)
│   └── vector_store.py      # Redis Stack 向量存储 (用户索引隔离)
│
├── generator/               # Office 文件生成器
│   ├── ppt.py               # PPT 生成器 (5 种布局, 3 套风格)
│   ├── word.py              # Word 生成器
│   └── pdf.py               # PDF 生成器
│
├── services/                # 业务编排层
│   └── generation.py        # 额度扣减 → 生成 → 上传 → 失败退款
│
├── client/                  # Java 后端 HTTP 客户端
│   ├── http.py              # RSA-SHA256 签名 HTTP 客户端
│   ├── quota.py             # 额度消费/退款
│   └── file.py              # 文件上传/下载
│
├── core/                    # 基础设施
│   ├── llm.py               # ChatModel 工厂
│   ├── embedding.py         # Embedding 工厂
│   ├── schemas.py           # Pydantic 数据模型
│   ├── exceptions.py        # 错误码体系
│   └── auth.py              # RSA-SHA256 签名验证中间件
│
├── utils/                   # 工具函数
├── tests/                   # 测试套件
└── doc/                     # 设计文档
    ├── DESIGN.md            # 总体架构设计
    ├── RAG_PIPELINE.md      # RAG 管线详解
    ├── JAVA_CALLER.md       # AI 调用 Java 接口文档
    ├── PYTHON_CALLER.md     # Java 调用 AI 接口文档
    └── graph/               # 各类型生成设计文档
```

---

## 快速开始

### 环境要求

- Python 3.12+
- Redis Stack（向量数据库）
- LibreOffice（PDF 生成，Docker 内置）
- OpenAI 兼容的 LLM API（如 DeepSeek、通义千问、GPT-4o）

### 本地开发

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd BirdHelp

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM API Key、Redis 连接信息、Java 后端地址等

# 4. 启动开发服务器
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker 部署

```bash
# 一键启动（确保 .env 已配置）
docker compose up -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

服务默认监听 `8686` 端口，健康检查端点：`GET /`

---

## API 端点

所有 `/ai/*` 接口均由 Java 后端代理转发，使用 RSA-SHA256 签名认证。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 健康检查 |
| POST | `/ai/material/upload` | 上传素材并触发 RAG 摄取 |
| DELETE | `/ai/material/{id}` | 删除素材（软删除 + 向量清理） |
| POST | `/ai/material/{id}/reindex` | 从回收站恢复后重建向量索引 |
| POST | `/ai/material/{id}/vector-purge` | 彻底删除向量数据 |
| POST | `/ai/ppt/generate` | 生成 PPT |
| POST | `/ai/word/generate` | 生成 Word |
| POST | `/ai/pdf/generate` | 生成 PDF |

### 请求示例

```json
POST /ai/ppt/generate
{
    "topic": "人工智能在医疗领域的应用",
    "style": "academic",
    "slide_count": 12
}
```

```json
POST /ai/word/generate
{
    "topic": "深度学习在自然语言处理中的应用研究",
    "doc_type": "paper",
    "word_count": 3000
}
```

---

## 配置说明

主要环境变量（完整列表见 `config.py`）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 大模型 API Key | — |
| `LLM_BASE_URL` | 大模型 API 地址 | — |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `EMBEDDING_MODEL` | 嵌入模型名称 | `text-embedding-3-small` |
| `REDIS_HOST` | Redis 地址 | `127.0.0.1` |
| `REDIS_PORT` | Redis 端口 | `6379` |
| `REDIS_PASSWORD` | Redis 密码 | — |
| `JAVA_BASE_URL` | Java 后端地址 | — |
| `JAVA_PRIVATE_KEY_B64` | AI 模块 RSA 私钥 (Base64) | — |
| `JAVA_CALLER_PUBLIC_KEY_B64` | Java 后端 RSA 公钥 (Base64) | — |
| `DEBUG` | 调试模式 | `false` |
| `MAX_UPLOAD_SIZE_MB` | 上传文件大小限制 (MB) | `20` |

---

## 架构概览

```
用户请求
   │
   ▼
Java 后端 (认证/路由/额度)
   │ RabbitMQ 消息
   ▼
broker/consumer.py (消费任务)
   │
   ▼
ReAct Agent (graph/agent.py)  ← LLM 自主决策工具调用序列
   ├─→ [tool] retrieve_knowledge   — RAG 混合检索（可选）
   ├─→ [tool] generate_outline     — LLM 生成结构化大纲
   ├─→ [tool] render_charts        — matplotlib 图表渲染（Word/PDF）
   ├─→ [tool] fetch_images         — Unsplash/Pexels 图片搜索
   ├─→ [tool] evaluate_quality     — 多维度 QA 评分 + 自动修复
   └─→ [tool] build_document       — 构建 Office 文件
   │
   ▼
上传文件至 Java 后端 → HTTP 回调通知 → 返回用户
```

### Agent 生成流程

与传统的固定 Workflow 不同，Agent 模式下的生成流程由 LLM 自主决策：

1. **额度扣减** — 调用 Java 后端扣减用户额度
2. **Agent 自主编排** — ReAct Agent 根据任务自主决定工具调用顺序：
   - 可跳过不需要的步骤（如纯文本文档跳过图表渲染）
   - 质量不达标时可自主重试（重新生成大纲、再次 QA）
   - 根据中间结果动态调整策略
3. **文件构建** — Agent 最终调用 build_document 工具生成 Office 文件
4. **上传交付** — 文件上传至 Java 文件存储，HTTP 回调通知 Java 端
5. **失败退款** — 生成失败自动退还额度

---

## 开发路线图

- [x] **Phase 1** — 基础设施：FastAPI 骨架、LLM/Embedding 工厂、Java 客户端、RSA 认证
- [x] **Phase 2** — RAG 管线：素材上传解析、向量化、混合检索
- [x] **Phase 3** — 文档生成：PPT / Word / PDF 全自动生成（Workflow → Agent 重构完成）
- [x] **Phase 7** — 异步任务：RabbitMQ 任务队列解耦
- [ ] **Phase 4** — 对话修改：多轮对话式文档编辑
- [ ] **Phase 5** — 投产准备：集成测试、错误覆盖、性能优化
- [ ] **Phase 6** — OCR 集成：PaddleOCR 图片/扫描件识别

---

## 许可证

MIT License

---

> Built with FastAPI · LangChain · LangGraph (ReAct Agent) · Redis Stack · python-pptx · python-docx
