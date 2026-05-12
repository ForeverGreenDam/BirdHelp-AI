# BirdHelp AI 模块设计文档

> v2.0 | 2026-05-10

---

## 一、职责边界

```
Java 后端（已建成）              Python AI 模块（本项目）
─────────────────                ─────────────────────────
用户认证 / 权限校验              大模型调用与 Chain 编排
额度校验与扣减                   Prompt 模板管理
文件存储（OSS/本地）             RAG：文档解析 → 向量检索 → 增强生成
会员管理                         PPT / Word / PDF 文件生成
请求路由与代理转发               OCR
```

---

## 二、技术选型

| 领域 | 技术 |
|------|------|
| Web 框架 | FastAPI |
| AI 框架 | LangChain + LangGraph |
| 大模型接入 | langchain-openai (ChatOpenAI，兼容 DeepSeek/通义千问/GPT-4o) |
| 嵌入模型 | text-embedding-3-small 或 bge-large-zh-v1.5 |
| 向量数据库 | Redis Stack |
| PPT 生成 | python-pptx |
| Word 生成 | python-docx |
| PDF 生成 | python-docx → LibreOffice 无头转换 |
| 文档解析 | LangChain Loaders (PyPDF/Docx2txt/Unstructured) |
| OCR | PaddleOCR |
| 异步任务 | FastAPI BackgroundTasks |
| HTTP 客户端 | httpx (async) |
| 配置 | pydantic-settings |
| 日志 | loguru |

---

## 三、项目结构

```
BirdHelp/
├── main.py
├── config.py
│
├── api/                  # 对外 API
│   ├── router.py
│   ├── ppt.py            # POST /ai/ppt/generate
│   ├── word.py           # POST /ai/word/generate
│   ├── pdf.py            # POST /ai/pdf/generate
│   ├── chat.py           # POST /ai/chat/modify
│   ├── material.py       # /ai/material/*  素材管理
│   └── ocr.py            # POST /ai/ocr/recognize
│
├── chains/               # LangChain Chain
│   ├── ppt_chain.py
│   ├── word_chain.py
│   ├── pdf_chain.py
│   └── chat_chain.py
│
├── graph/                # LangGraph 工作流
│   ├── generation_graph.py   # RAG→生成→检查→重试
│   └── chat_graph.py         # 对话修改状态图
│
├── rag/                  # RAG 管线
│   ├── ingestion.py      # 文档加载→清洗→切分→嵌入→入库
│   ├── retrieval.py      # 混合检索 (向量 + BM25 + RRF)
│   └── vector_store.py   # Redis Stack 向量库管理
│
├── generator/            # Office 文件生成
│   ├── base.py
│   ├── ppt.py
│   ├── word.py
│   └── pdf.py
│
├── services/             # 业务编排
│   ├── generation.py
│   ├── chat.py
│   └── ocr.py
│
├── client/               # Java 后端调用
│   ├── http.py
│   ├── quota.py
│   └── file.py
│
├── core/                 # 基础设施
│   ├── llm.py            # ChatModel 工厂
│   ├── embedding.py      # Embedding 工厂
│   ├── schemas.py        # Pydantic 模型
│   └── exceptions.py     # 异常 + 错误码
│
└── utils/
    ├── file.py
    └── format.py
```

---

## 四、API 清单

### 4.1 AI 模块对外接口（Java 代理转发）

| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/ai/ppt/generate` | 生成 PPT (支持 RAG) |
| POST | `/ai/word/generate` | 生成 Word (支持 RAG) |
| POST | `/ai/pdf/generate` | 生成 PDF (支持 RAG) |
| POST | `/ai/chat/modify` | 对话式修改文档 |
| POST | `/ai/ocr/recognize` | OCR 识别 |
| POST | `/ai/material/upload` | 上传 RAG 参考素材 |
| GET | `/ai/material/list` | 查询素材列表 |
| DELETE | `/ai/material/{id}` | 删除素材 |
| GET | `/ai/task/{task_id}/status` | 查询异步任务状态 |

所有生成接口请求体统一包含 `material_ids` 和 `rag_enabled` 可选字段以启用 RAG。

### 4.2 调用的 Java 内部接口

| 方法 | 路径 | 调用时机 |
|------|------|---------|
| POST | `/internal/quota/consume` | 生成开始前 |
| POST | `/internal/quota/refund` | 生成失败时 |
| POST | `/internal/file/upload` | 文件生成完成后 |

---

## 五、RAG 管线

```
用户上传文件 (PDF/DOCX/PPTX/TXT/图片)
  → 类型检测 → LangChain Loader 解析 → 文本清洗
  → RecursiveCharacterTextSplitter (chunk=1000, overlap=200)
  → Embedding 向量化 → 存入 Redis Stack (按 user_id + material_id 隔离)

生成时检索:
  → MultiQueryRetriever (查询改写)
  → 混合检索 (向量 top10 + BM25 top10 → RRF 融合 → 取 top5)
  → 注入 Prompt {context} 占位符
```

生成接口新增可选参数 `material_ids` 限定检索范围，不传则检索用户全部素材。

---

## 六、核心流程

### 6.1 文档生成 (LangGraph 状态图)

```
开始 → 判断 rag_enabled
       ├─ YES → RAG 检索 → 注入 context
       └─ NO  → context = null
       → LangChain Chain 执行 (Prompt → LLM → JSON 解析)
       → 解析成功? ── YES → 文件生成 → 上传 Java → 结束
       └─ NO (重试 ≤3 次) → 回到 LLM 调用
```

### 6.2 对话修改

```
用户消息 → LangGraph 恢复会话状态
  → 判断是否需要 RAG → Chat Chain 输出修改指令 JSON
  → 代码执行增量编辑 (python-pptx/docx 对象模型)
  → 保存新文件 → 上传
```

---

## 七、开发计划

### Phase 1: 基础设施 (第 1–2 周)
- FastAPI 骨架 + 配置 + 日志
- LangChain ChatModel / Embedding 工厂
- Java 客户端 (`client/`)
- Pydantic Schema + 任务状态接口

### Phase 2: RAG 管线 (第 3–5 周)
- 摄取管道 (解析→切分→嵌入→入库)
- Redis Stack 集成 + 素材 CRUD API
- 混合检索器 + Query Rewriting

### Phase 3: 文档生成 (第 6–8 周)
- PPT / Word / PDF Chain + 文件生成器
- LangGraph 生成状态图
- 文件生成 + 文件上传回调

### Phase 4: 对话修改 (第 9–10 周)
- Chat Chain + LangGraph 对话状态图
- python-pptx/docx 增量编辑
- 多轮对话历史管理

### Phase 5: 辅助能力 + 上线 (第 11–12 周)
- PaddleOCR 集成
- 与 Java 后端联调 + 压测

---

## 八、核心依赖

```
fastapi                    langchain                  langchain-openai
langchain-community        langgraph
python-pptx                python-docx                pypdf
paddleocr                  redis
httpx                      pydantic-settings          loguru
```
