# BirdHelp AI 🐦

**大学生文档助手 — AI 能力层**

基于 FastAPI + LangChain + LangGraph 的智能文档生成服务，支持 PPT / Word / PDF 的全自动生成，集成 RAG（检索增强生成）混合检索。通过内部 HTTP 协议与 Java 后端协作，提供 RSA-SHA256 双向签名认证。

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
| AI 编排 | LangChain + LangGraph |
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
├── graph/                   # LangGraph 状态图
│   └── generation_graph.py  # 文档生成工作流 (RAG → Chain → 校验 → 重试 → 构建)
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
   │ RSA-SHA256 签名
   ▼
FastAPI 路由层 (/ai/*)
   │
   ▼
LangGraph 状态图
   ├─→ RAG 检索 (可选, 向量 + BM25 + RRF)
   ├─→ LangChain Chain (Prompt + LLM + OutputParser)
   ├─→ 校验与重试 (最多 3 次)
   └─→ 文件生成器 (python-pptx / python-docx / LibreOffice)
   │
   ▼
上传文件至 Java 后端 → 返回用户
```

### 生成流程

1. **额度扣减** — 调用 Java 后端扣减用户额度
2. **RAG 检索**（可选）— 如用户有上传素材，从 Redis 检索相关内容注入 Prompt
3. **LLM 生成** — LangChain Chain 调用大模型生成结构化内容
4. **内容校验** — 验证 JSON 结构完整性，失败自动重试（最多 3 次）
5. **文件构建** — 调用对应生成器（python-pptx / python-docx）生成 Office 文件
6. **上传交付** — 文件上传至 Java 文件存储，失败自动退款

---

## 开发路线图

- [x] **Phase 1** — 基础设施：FastAPI 骨架、LLM/Embedding 工厂、Java 客户端、RSA 认证
- [x] **Phase 2** — RAG 管线：素材上传解析、向量化、混合检索
- [x] **Phase 3** — 文档生成：PPT / Word / PDF 全自动生成
- [ ] **Phase 4** — 对话修改：多轮对话式文档编辑
- [ ] **Phase 5** — 投产准备：集成测试、错误覆盖、性能优化
- [ ] **Phase 6** — OCR 集成：PaddleOCR 图片/扫描件识别
- [ ] **Phase 7** — 异步任务：RabbitMQ 任务队列解耦

---

## 许可证

MIT License

---

> Built with FastAPI · LangChain · LangGraph · Redis Stack · python-pptx · python-docx
