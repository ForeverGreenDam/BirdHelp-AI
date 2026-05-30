# BirdHelp AI 模块设计文档

> v5.2 | 2026-05-30 | 对话修改模块实现：LLM 修改大纲 → 重建文件（无 QA）；broker 回调携带 outline；Java 内部 API 扩展（大纲/会话）；文件预览 + 版本链 + RAG 过滤

> v4.4 | 2026-05-28 | API Key 架构升级

---

## 一、职责边界

```
Java 后端（已建成）              Python AI 模块（本项目）
─────────────────                ─────────────────────────
用户认证 / 权限校验              大模型调用与 Chain 编排
额度校验与扣减                   Prompt 模板管理
文件存储（OSS/本地）             RAG：文档解析 → 向量检索 → 增强生成
会员管理                         PPT / Word / PDF 文件生成
请求路由与代理转发               OCR（独立接口 + RAG 解析兜底）
```

---

## 二、技术选型

| 领域 | 技术 | 选型理由 |
|------|------|----------|
| Web 框架 | FastAPI | 异步原生、生态成熟、与 Java 后端 httpx 统一 |
| AI 框架 | LangChain + LangGraph | 统一的 RAG / Chain / 状态图编排 |
| 大模型接入 | langchain-openai (ChatOpenAI) | OpenAI 兼容协议，同时对接 DeepSeek / 通义千问 / GPT-4o |
| 嵌入模型 | text-embedding-3-small 或通义 text-embedding-v4 | 中文语义效果稳定，1536 维性价比高 |
| 向量数据库 | Redis Stack | 低延迟向量检索 + 用户索引隔离 + 已有机房 Redis 实例 |
| PPT 生成 | python-pptx + 设计系统 | 6套主题 + 11种布局渲染器 + 7套场景profile + 图表/表格 + 图片集成 + QA |
| Word 生成 | python-docx + DocxBuilder + matplotlib | 图表嵌入(PNG)、图片插入、增强表格、封面设计 |
| PDF 生成 | python-docx → LibreOffice | 与 Word 共享 DocxBuilder，matplotlib 图表嵌入 |
| 文档解析 | LangChain Loaders (PyPDF / python-docx / python-pptx) | 生态统一，TextSplitter 无缝衔接 |
| PDF OCR 兜底 | PyMuPDF (fitz) + PaddleOCR | PDF 页→图片渲染→OCR，解决扫描版/图片型 PDF |
| PPT/Word 图片 OCR | python-pptx/docx 图片提取 + PaddleOCR | 导出嵌入图片 blb → OCR 识别 |
| OCR 引擎 | PaddleOCR | 中文识别准确率高、离线可用、配置简单 |
| 同步任务 | FastAPI BackgroundTasks | 轻量场景（素材上传触发摄取），无需额外组件 |
| 异步任务队列 | RabbitMQ + aio-pika | ✅ 已实现。生成类长任务解耦；Topic Exchange + 死信队列；ACK/重试/进度通知；aio-pika 提供 async 原生 API |
| HTTP 客户端 | httpx (async) | 与 FastAPI 异步模型一致，支持连接池复用 |
| PDF 页面渲染 (OCR 兜底) | PyMuPDF | 纯 C 实现，比 pdf2image + poppler 更轻，Docker 友好 |
| 配置 | pydantic-settings | 自动加载 .env + 环境变量 |
| 日志 | loguru | 开箱即用，结构化日志，比 logging 模块简洁 |

---

## 三、项目结构

```
BirdHelp/
├── main.py
├── config.py
│
├── api/                    # 对外 API（✅ 已实现: router, material）
│   ├── router.py           #
│   ├── material.py         # ✅ POST /ai/material/upload
│   ├── ppt.py              # ❌ 已移除 → RabbitMQ
│   ├── word.py             # ❌ 已移除 → RabbitMQ
│   ├── pdf.py              # ❌ 已移除 → RabbitMQ
│   └── ocr.py              # ⬜ POST /ai/ocr/recognize
│
├── chains/                 # LangChain Chain（✅ 全部实现）
│   ├── ppt_chain.py        # ✅ PptChain（场景profile注入）
│   ├── qa_chain.py         # ✅ PPT QA（12维、含场景合规/图表数据检查）+ 修复循环
│   ├── word_chain.py       # ✅ WordChain（图表+插图+表格增强 Prompt）
│   ├── word_qa_chain.py    # ✅ Word/PDF 文档 QA + 修复循环
│   ├── pdf_chain.py        # ✅ PdfChain（图表+插图+表格增强 Prompt）
│
├── modify/                 # ✅ 对话修改模块 (v5.2)
│   ├── api.py              # ✅ POST /ai/chat/modify, /ai/chat/discuss
│   ├── schemas.py          # ✅ Pydantic 模型
│   ├── chain.py            # ✅ LLM 对话修改 Prompt
│   ├── graph.py            # ✅ LangGraph 状态图（无 QA）
│   ├── client.py           # ✅ Java 内部 API 客户端（大纲/会话）
│   ├── parser.py           # ✅ 文档逆向解析（降级兜底）
│   └── service.py          # ✅ 业务编排
│
├── graph/                  # LangGraph 工作流（✅ generation_graph 已实现）
│   └── generation_graph.py # ✅ 文档生成状态图 (RAG→Chain→校验→QA→重试→构建)
│
├── rag/                    # RAG 管线（✅ 已实现）
│   ├── ingestion.py        # ✅ 文档下载→解析→切分→嵌入→入库
│   ├── retrieval.py        # ✅ 混合检索 (向量 + BM25 + RRF)
│   └── vector_store.py     # ✅ Redis Stack 用户索引隔离 + CRUD
│
├── generator/              # Office 文件生成
│   ├── base.py             # ✅ 抽象基类
│   ├── _design.py          # ✅ 公共 ColorPalette（PPT/Word/PDF 共用）
│   ├── _chart_engine.py    # ✅ matplotlib 图表渲染（bar/line/pie/hbar/radar）
│   ├── _docx_builder.py    # ✅ 公共 DocxBuilder（Word/PDF 共用）
│   ├── ppt/                # ✅ PPT 生成模块
│   │   ├── generator.py        # ✅ PptGenerator
│   ├── profiles.py         # ✅ 7套场景设计配置 (v2.2)
│   │   ├── theme.py            # ✅ PPT ColorTheme（从 _design 派生，含图表/表格色）
│   │   ├── shapes.py           # ✅ 声明式绘图工具包 + 富文本 + 增强形状
│   │   ├── layout.py           # ✅ 14 种 LayoutType + DesignDNA（含 info_density）
│   │   ├── image_provider.py   # ✅ 图片搜索/下载/降级
│   │   └── layouts/            # ✅ 布局渲染器 (11 种)
│   ├── word/               # ✅ Word 生成模块
│   │   └── generator.py        # ✅ WordGenerator（DocxBuilder + 图片注入）
│   └── pdf/                # ✅ PDF 生成模块
│       └── generator.py        # ✅ PdfGenerator（DocxBuilder + LibreOffice）
│
├── services/               # 业务编排（✅ 已实现: generation）
│   ├── generation.py      # ✅ 文档生成业务编排（额度→生成→上传→退款，支持 PPT/Word/PDF）
│   ├── chat.py            # ⬜ 对话修改业务编排
│   └── ocr.py             # ⬜ OCR 业务逻辑（含 PDF/PPT/Word 图片 OCR）
│
├── broker/                 # RabbitMQ 异步消费者（✅ 已实现）
│   ├── __init__.py         # ✅ 包入口
│   ├── schemas.py          # ✅ 消息体/回调体 Pydantic 校验（camelCase ↔ snake_case）
│   └── consumer.py         # ✅ 消费者：解析→额度→生成→上传→回调，ACK/NACK/重试/DLQ
│
├── client/                 # Java 后端调用（✅ 已实现）
│   ├── http.py             # ✅ RSA-SHA256 签名 HTTP 客户端
│   ├── quota.py            # ✅ 额度消耗/退还
│   ├── file.py             # ✅ 文件上传/下载/删除
│   └── task.py             # ✅ 任务完成/失败回调 + 进度推送
│
├── core/                   # 基础设施（✅ 已实现）
│   ├── llm.py              # ✅ ChatModel 工厂（contextvars 注入凭证，.env 兜底）
│   ├── embedding.py        # ✅ Embedding 工厂（.env 配置，嵌入模型固定）
│   ├── schemas.py          # ✅ Pydantic 模型
│   └── exceptions.py       # ✅ 异常 + 错误码
│
└── utils/                  # 工具（✅ 已实现）
    ├── file.py             # ✅ 临时文件路径/清理
    └── format.py           # ✅ JSON 安全解析
```

> ✅ 已实现  |  ⬜ 待实现

### 3.1 API Key 管理（v4.4）

**聊天模型（Chat）：由 Java 端在每次请求中注入**

模型选择是业务决策（用户在前端选了哪个模型），由 Java 端负责。Java 将 `apiKey`、`baseUrl`、`modelName` 直接写入 RabbitMQ 消息体，Python 消费后通过 contextvars 注入 `create_chat_model()`。Python 端不缓存、不持久化聊天模型凭证。

```
用户在前端选择模型
  → Java 根据用户选择 / 会员等级确定模型
    → 从 DB 查出对应的 apiKey / baseUrl
      → 写入 RabbitMQ 消息 body（apiKey / baseUrl / modelName）
        → Python broker 消费 → LangGraph state["llm_config"]
          → contextvars.set() → create_chat_model() 读取
            → 用完即丢，不落盘不缓存
```

**嵌入模型（Embedding）：从 .env 读取**

同一 RAG 系统的向量必须由同一模型产出，模型不能随请求切换，因此嵌入模型配置固定写在 `.env` 中（`embedding_model` / `embedding_api_key` / `embedding_base_url`）。`embedding_api_key` / `embedding_base_url` 为空时自动回退到 `llm_api_key` / `llm_base_url`。

```
create_embeddings()
  → 读取 settings.embedding_model / embedding_api_key / embedding_base_url
    → embedding_api_key 为空 → 回退 settings.llm_api_key
    → embedding_base_url 为空 → 回退 settings.llm_base_url
```

**对比：**

| | 聊天模型 (Chat) | 嵌入模型 (Embedding) |
|---|---|---|
| 注入方式 | RabbitMQ 消息体 | .env 配置文件 |
| 切换模型 | 用户发起下一个请求立即生效 | 修改 .env 后重启生效 |
| Python 端是否缓存密钥 | ❌ 用完即丢 | ❌ 启动时一次性加载 |
| 配置位置 | Java 后端 DB | Python .env |

> 详细集成指南见 `doc/PYTHON_API_KEY_INTEGRATION.md`。
> 消息协议见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`。

---

## 四、API 清单

### 4.1 AI 模块对外接口（Java 代理转发）

| 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|
| POST | `/ai/material/upload` | 上传 RAG 参考素材并触发摄取 | ✅ |
| GET | `/ai/material/list` | 查询素材列表 | ✅ |
| DELETE | `/ai/material/{id}` | 删除素材（Java 回收站 + Redis 向量清理） | ✅ |
| POST | `/ai/ppt/generate` | 生成 PPT（支持 RAG）| ❌ 已移除 |
| POST | `/ai/word/generate` | 生成 Word（支持 RAG）| ❌ 已移除 |
| POST | `/ai/pdf/generate` | 生成 PDF（支持 RAG）| ❌ 已移除 |
| POST | `/ai/chat/modify` | 对话式修改文档（LLM 修改大纲 + 重建文件） | ✅ v5.2 |
| POST | `/ai/chat/discuss` | 仅讨论/问答（不重建文件） | ✅ v5.2 |
| POST | `/ai/ocr/recognize` | 独立 OCR 识别接口 | ⬜ |
| GET | `/ai/task/{task_id}/status` | 查询异步任务状态 | ⬜ |

> **文档生成已异步化**：生产环境不再直接调用 `/ai/{ppt,word,pdf}/generate`。改为 Java → RabbitMQ → Python broker（详见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`）。HTTP 端点保留仅用于开发调试。

所有生成接口请求体统一包含 `material_ids` 和 `rag_enabled` 可选字段。

### 4.2 调用的 Java 内部接口

| 方法 | 路径 | 调用时机 | 状态 |
|------|------|---------|------|
| POST | `/api/internal/quota/consume` | 生成开始前扣额度 | ✅ |
| POST | `/api/internal/quota/refund` | 生成失败退额度 | ✅ |
| POST | `/api/internal/file/upload` | 文件生成完成后上传 | ✅ |
| POST | `/api/internal/task/callback` | 异步任务完成/失败回调 | ✅ |
| POST | `/api/internal/task/progress` | 异步任务进度推送 | ✅ |
| GET | `/api/internal/file/{id}/outline` | 读取文档大纲（对话修改时） | ✅ v5.2 |
| PUT | `/api/internal/file/{id}/outline` | 更新文档大纲（修改完成后） | ✅ v5.2 |
| POST | `/api/internal/chat/session` | 获取或创建对话会话 | ✅ v5.2 |
| POST | `/api/internal/chat/session/{id}/messages` | 追加对话消息 | ✅ v5.2 |

---

## 五、RAG 管线

> 详见 `doc/RAG_PIPELINE.md`

### 5.1 摄取向段（当前实现）

```
用户上传文件 (PDF/DOCX/PPTX/TXT)
  → 类型检测 → Loader 解析 → 文本合并
  → RecursiveCharacterTextSplitter (chunk=1000, overlap=200)
  → Embedding 向量化 → Redis Stack (按 user_id 索引隔离)
```

**当前解析能力：**

| 格式 | 解析方式 | 能提取 | 不能提取 |
|------|----------|--------|----------|
| PDF | `PyPDFLoader` | 文本层文字 | 扫描版/图片型 PDF（无文本层） |
| DOCX | 自定义 `_load_docx()` | 段落文本 | 嵌入图片中的文字 |
| PPTX | 自定义 `_load_pptx()` | 文本框文字 | 嵌入图片/截图中的文字 |
| TXT | 自定义 `_load_txt()` | 全部文本 | — |

### 5.2 检索阶段

```
用户查询
  → MultiQueryRetriever (LLM 改写为多视角)
  → EnsembleRetriever (权重 0.5:0.5)
      ├─ 向量检索 (Redis 相似度, top_k×2)
      └─ BM25 关键词检索 (内存索引, top_k×2)
  → RRF 融合 → 去重 → 截断 top_k
  → 注入 Prompt {context} 占位符
```

### 5.3 OCR 兜底策略（Phase 4 实现）

针对当前解析器无法提取图片内文字的问题，为每种格式设计 OCR 兜底方案：

**PDF OCR 兜底（两级策略）**

```
PyPDFLoader 提取文本层
  ├── 非空 → 正常走切分管道
  └── 空 (图片型 PDF) → OCR 兜底:
          PyMuPDF(fitz) 逐页渲染为 200 DPI 图片
          → PaddleOCR 逐页识别
          → 拼接全量文本 → 进入切分管道
```

**PPTX 图片 OCR**

```
_load_pptx 提取文本框架文字
  → 遍历 shape 提取图片 blob (MSO_SHAPE_TYPE.PICTURE)
  → PaddleOCR 逐图识别
  → 与文本框架文字合并 → 进入切分管道
```

**DOCX 图片 OCR**

```
_load_docx 提取段落文字
  → 遍历 document.part.related_parts 提取图片 blob
  → PaddleOCR 逐图识别
  → 与段落文字合并 → 进入切分管道
```

**OCR 技术选型**

| 环节 | 技术 | 选型理由 |
|------|------|----------|
| PDF 渲染 | PyMuPDF (fitz) | 纯 C，Docker 友好，无需系统依赖 poppler；比 pdf2image 轻量 |
| 图片提取 (PPTX) | python-pptx `shape.image.blob` | 直接从 shape 对象拿字节数据，无需写临时文件 |
| 图片提取 (DOCX) | python-docx `document.inline_shapes` | 遍历内联图片关系获取 blob |
| OCR 引擎 | PaddleOCR | 项目已有 `paddleocr_lang` 配置；中文准确率高；离线可用 |

**性能考量**
- OCR 速度约每页 1~3 秒（CPU），纯图片 30 页 PDF 预估 30~90 秒
- 建议加页数上限（如 >50 页拒绝 OCR，提示用户拆分）
- 摄取为一次性异步操作，OCR 耗时在不阻塞请求的前提下可接受
- `paddleocr_lang` 配置项可控制语言包加载，中文场景用 `"ch"`，中英混合可用 `"ch"`（自带英文识别）

---

## 六、核心流程

### 6.1 文档生成（RabbitMQ 异步消费）

文档生成已全面异步化：Java 后端将任务发布到 RabbitMQ，Python broker 模块消费执行。

```
Java 后端                              Python AI 模块
─────────                              ──────────────
收到用户生成请求
  → 生成 taskId
  → publish 消息到 Exchange ────→  broker/consumer.py 消费
  → 返回 {taskId, status:pending}
                                     ├─ ① 解析校验消息 (version/docType/字段)
                                     ├─ ② 调用 Java 扣减额度 (quota.consume)
                                     ├─ ③ LangGraph 状态图执行
                                     │     RAG 检索(可选) → Chain → LLM → JSON → QA
                                     ├─ ④ 文件生成 (PPT/Word/PDF generator)
                                     ├─ ⑤ 上传文件到 Java (file.upload)
                                     ├─ ⑥ HTTP 回调通知 (task.callback)
                                     └─ ⑦ ACK 消息

Java 收到回调 → 更新任务状态 → 前端轮询获得结果
```

> 完整消息协议、ACK/NACK 规则、回调格式见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`。

### 6.2 对话修改（v5.2 实现）

```
前端 → Java ChatController (JWT 鉴权 + 日志)
     → AiModuleCaller (RSA 签名) → Python POST /ai/chat/modify
     → modify/service.py 编排:
        ① GET /internal/file/{id}/outline → 获取大纲（100% 保真）
          ↓ outline 为空时 → modify/parser.py 逆向解析降级
        ② POST /internal/chat/session → 获取/创建会话 + 历史消息
        ③ modify/graph.py LangGraph:
            chat_analyze (LLM 基于现有大纲修改)
            → validate_output (JSON 校验，失败重试 ≤3 次)
            → rebuild_file (Generator 重建，不复用图片搜索)
            → upload_file (上传携带 versionOf 建立版本链)
        ④ PUT /internal/file/{id}/outline → 存新大纲
        ⑤ POST /internal/chat/session/{id}/messages → 追加消息
     → 返回 AI 回复 + 新大纲 + 新 file_id
```

**与生成流程的差异：** 无 RAG 检索、无 QA 评分（用户主观修改不应被拦截）、无图片搜索（复用原文件图片）。

### 6.3 异步任务架构（Phase 7 — 已实现）

文档生成耗时较长（LLM 推理 10–30s + QA 15–40s + 文件生成 5–15s），已通过 RabbitMQ 异步化解耦。

**选型：RabbitMQ + aio-pika**（已实现）

**拓扑结构：**

```
Exchange: birdhelp.doc.generation (topic, durable)
  ├── doc.generate.ppt  ─┐
  ├── doc.generate.word ─┤
  └── doc.generate.pdf  ─┼→ Queue: birdhelp.doc.generation.tasks (TTL 10min, max_priority 10)
                          │     ↓ DLX: birdhelp.doc.generation.dlx
                          │     ↓ DLQ: birdhelp.doc.generation.dlq
                          │
                          └→ Python broker/consumer.py (prefetch=1)
```

**5 阶段消费流程：**

```
① 解析校验   → JSON → Pydantic → 版本/docType/字段枚举
② 扣减额度   → POST /api/internal/quota/consume (失败→回调 + ACK)
③ 文档生成   → LangGraph.ainvoke (RAG→LLM→QA→文件)
④ 文件上传   → POST /api/internal/file/upload (失败→最多重试3次)
⑤ 回调通知   → POST /api/internal/task/callback (completed/failed)
```

**ACK/NACK 规则：**

| 场景 | 动作 | 入 DLQ |
|------|------|--------|
| 生成成功 | ACK | — |
| 消息格式错误 | NACK(requeue=false) | 是 |
| 额度不足 | ACK + 回调失败 | — |
| LLM/上传临时故障 | 重发布(x-retry-count+1) ≤3次 | 超限后入 |
| 生成逻辑错误 | ACK + 退还额度 + 回调失败 | — |

> 完整规范见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`。

---

## 七、执行阶段

### Phase 1: 基础设施 ✅ 已完成

- FastAPI 应用骨架、全局配置、日志
- LangChain ChatModel / Embedding 工厂
- Java 后端 HTTP 客户端（RSA-SHA256 签名认证）
- 文件服务客户端（上传 / 下载 / 列表 / 删除）
- 额度管理客户端（消耗 / 退还）
- Pydantic Schema + 统一 ApiResponse
- 异常体系 + 错误码

### Phase 2: RAG 管线 ✅ 已完成

- 摄取管道：多格式解析 → 切分 → 嵌入 → Redis 入库
- Redis Stack 向量存储：用户级索引隔离 + CRUD
- 素材管理 API（上传 / 列表 / 删除）
- 混合检索器：向量 + BM25 + RRF + MultiQuery 改写
- 素材删除联动（Java 回收站 + Redis 向量清理）
- RAG 管线文档 (`doc/RAG_PIPELINE.md`)

### Phase 3: 文档生成（第 1–3 周）⚡ 同步模式 — PPT ✅ 已完成

**目标：** 用户上传素材后，AI 生成完整 Office 文档。

> **注意：** 本阶段 API 同步执行生成流程（阻塞请求），文档生成耗时较长（20–60s）。
> 后续 Phase 7 引入消息队列异步化，解耦请求与生成。初期接受同步阻塞，先跑通核心链路。

- LangChain Chain 实现：
  - `ppt_chain.py` — ✅ PPT 视觉描述（场景profile注入）+ LLM + JSON
  - `qa_chain.py` — ✅ PPT QA（12维含场景合规/图表数据检查）+ 修复循环
  - `word_chain.py` — ✅ Word 增强 Prompt（图表 + 插图 + 表格）
  - `word_qa_chain.py` — ✅ Word/PDF 文档 QA + 修复循环
  - `pdf_chain.py` — ✅ PDF 增强 Prompt（图表 + 插图 + 表格）
- Office 文件生成器：
  - `generator/ppt/` — ✅ python-pptx + 设计系统（6主题, 11布局, 7套profile, 图表/表格, 图片, QA）
  - `generator/word/` — ✅ python-docx + DocxBuilder + matplotlib 图表嵌入
  - `generator/pdf/` — ✅ DocxBuilder + LibreOffice 转换
- 公共模块：
  - `generator/_design.py` — ✅ ColorPalette（PPT/Word/PDF 共用 6 套主题）
  - `generator/_chart_engine.py` — ✅ matplotlib 图表引擎（5 种图表类型）
  - `generator/_docx_builder.py` — ✅ 增强型 DocxBuilder（图表/图片/表格/封面）
- LangGraph 生成状态图：
  - `graph/generation_graph.py` — ✅ RAG 检索 → Chain 执行 → JSON 校验 → 失败重试（≤3 次）
- 业务编排：
  - `services/generation.py` — ✅ 额度扣减 → LangGraph 执行 → 文件上传 → 失败退款
- 生成接口：`POST /ai/ppt/generate` ✅ / `/ai/word/generate` / `/ai/pdf/generate`
- 生成完成后上传文件至 Java 后端

### Phase 4: 对话修改 ✅ 已完成（v5.2）

**目标：** 用户通过多轮对话对已生成文档进行增量修改。

- ✅ `modify/chain.py` — LLM 对话修改 Prompt + 结构化输出
- ✅ `modify/graph.py` — LangGraph 状态图（chat_analyze → validate → rebuild → upload，无 QA）
- ✅ `modify/client.py` — Java 内部 API 客户端（大纲读写 + 会话 CRUD，RSA 签名）
- ✅ `modify/parser.py` — 文档逆向解析降级兜底（旧文件无 outline 时）
- ✅ `modify/service.py` — 业务编排（获取大纲→LLM→重建→同步Java）
- ✅ `modify/api.py` — `POST /ai/chat/modify` + `POST /ai/chat/discuss`
- ✅ broker 回调携带 outline → Java 存入 `file_record.outline`
- ✅ 版本链：修改版上传携带 `versionOf`，文件列表只展示链尾
- 详见 `doc/CHAT_MODIFY_DESIGN.md`

### Phase 5: 辅助能力 + 上线（第 6–7 周）

- REST API 路由全部注册
- `services/` 业务编排层（generation / chat / ocr service）
- 与 Java 后端联调（生成接口的完整调用链：提交 → 等待 → 生成 → 上传）
- 额度消耗 / 退还的完整流程验证（含失败退款）
- 异常场景覆盖（生成超时、文件损坏、额度不足、LLM 返回格式异常）
- 日志 + 链路追踪
- 性能压测 + 并发安全

### Phase 6: OCR 兜底 + 图片识别（后续迭代）

> **优先级：低。** 核心生成流程先打通，此阶段在时间充裕时进行。

**背景：** 当前 RAG 解析器只能提取文本层，面对图片型 PDF（扫描教材、PPT 截图拼成的 PDF）、PPT/Word 中的嵌入图片时，文字信息完全丢失，导致这部分素材无法参与检索和生成。

**子任务：**

1. **PDF OCR 兜底**
   - `rag/ingestion.py` 增加 `_load_pdf_with_ocr_fallback()` 函数
   - 逻辑：`PyPDFLoader` 提取文本 → 为空则 PyMuPDF 逐页渲染 → PaddleOCR 识别
   - 依赖新增：`PyMuPDF` (fitz)、`paddlepaddle` + `paddleocr`
   - 配置新增：`ocr_dpi: int = 200`、`ocr_max_pages: int = 50`

2. **PPTX 图片 OCR**
   - `rag/ingestion.py` 改造 `_load_pptx()`：遍历 shape 提取图片 blob → PaddleOCR
   - 依赖已有：`python-pptx` (shape.image.blob)、`paddleocr`

3. **DOCX 图片 OCR**
   - `rag/ingestion.py` 改造 `_load_docx()`：遍历 inline_shapes 提取图片 → PaddleOCR
   - 依赖已有：`python-docx` (document.inline_shapes)、`paddleocr`

4. **独立 OCR 接口**
   - `api/ocr.py` — `POST /ai/ocr/recognize`，支持单图片 / 单 PDF 页面 OCR
   - `services/ocr.py` — 封装 OCR 逻辑，供 ingestion 和 API 复用

5. **性能优化**
   - OCR 结果缓存（按文件 hash，避免重复识别同一文件）
   - 超时控制（大文件页数上限、单页超时）
   - GPU 加速支持（PaddleOCR 可选 CUDA 后端）

### Phase 7: 异步任务队列 ✅ 已完成

> **完成日期：2026-05-23。** 文档生成从同步 HTTP 改为 RabbitMQ 异步消费，彻底解决前端接口超时问题。

**实现方案：RabbitMQ + aio-pika**（详见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`）

| 组件 | 实现 |
|------|------|
| 消息协议 | v1.0，Java 生产 Python 消费，camelCase JSON，严格字段校验 |
| 交换机/队列 | `birdhelp.doc.generation` (topic) → `birdhelp.doc.generation.tasks` (TTL 10min, DLX) |
| 消费者 | `broker/consumer.py` — 5 阶段流水线，ACK/NACK/重试(≤3)/DLQ |
| 消息校验 | `broker/schemas.py` — Pydantic 模型，版本/类型/字段全覆盖 |
| 回调 | `client/task.py` — RSA-SHA256 签名 HTTP → `POST /api/internal/task/callback` |
| 集成 | `main.py` lifespan — 消费者随 FastAPI 自动启动/关闭 |

**架构对比：**

| | Phase 3 同步模式 | Phase 7 异步模式 (current) |
|------|------|------|
| API 响应时间 | 30–120s（阻塞） | Java 立即返回 taskId，Python 异步消费 |
| 前端超时 | 高风险 | 无（轮询/WebSocket 获取结果） |
| 故障隔离 | 生成崩溃影响 API | 消费者独立，消息持久化，重试 + DLQ |
| 并发能力 | 受 FastAPI worker 限制 | 受 prefetch 控制，可按队列独立扩容 |

---

## 八、核心依赖

```text
# Web & AI 框架
fastapi                    langchain                  langchain-openai
langchain-community        langgraph                  langchain-text-splitters

# 文件生成
python-pptx                python-docx                pypdf
matplotlib                 numpy                     # 图表生成（Word/PDF 嵌入）

# 向量存储
redis

# HTTP 客户端
httpx

# 异步任务队列
aio-pika                   aiormq                     pamqp

# OCR（Phase 6 新增 PyMuPDF）
paddleocr                  paddlepaddle
PyMuPDF                    # PDF → 图片渲染，OCR 兜底

# 配置 & 日志
pydantic-settings          loguru
```
