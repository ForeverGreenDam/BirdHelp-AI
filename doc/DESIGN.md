# BirdHelp AI 模块设计文档

> v3.3 | 2026-05-16 | Phase 3 全部完成 (PPT / Word / PDF)

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
| PPT 生成 | python-pptx | 轻量纯 Python，无需 LibreOffice |
| Word 生成 | python-docx | 同上 |
| PDF 生成 | python-docx → LibreOffice 无头转换 | 先建 docx 再转 PDF，保证排版一致性 |
| 文档解析 | LangChain Loaders (PyPDF / python-docx / python-pptx) | 生态统一，TextSplitter 无缝衔接 |
| PDF OCR 兜底 | PyMuPDF (fitz) + PaddleOCR | PDF 页→图片渲染→OCR，解决扫描版/图片型 PDF |
| PPT/Word 图片 OCR | python-pptx/docx 图片提取 + PaddleOCR | 导出嵌入图片 blb → OCR 识别 |
| OCR 引擎 | PaddleOCR | 中文识别准确率高、离线可用、配置简单 |
| 同步任务 | FastAPI BackgroundTasks | 轻量场景（素材上传触发摄取），无需额外组件 |
| 异步任务队列 | RabbitMQ + aio-pika | 生成类长任务解耦；成熟可靠的消息中间件；支持 ACK/重试/死信队列；aio-pika 提供 async 原生 API，兼容 FastAPI |
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
├── api/                    # 对外 API（✅ 已实现: router, material, ppt, word, pdf）
│   ├── router.py           #   │ 待实现: chat, ocr
│   ├── material.py         # ✅ POST /ai/material/upload
│   ├── ppt.py              # ✅ POST /ai/ppt/generate
│   ├── word.py             # ✅ POST /ai/word/generate
│   ├── pdf.py              # ✅ POST /ai/pdf/generate
│   ├── chat.py             # ⬜ POST /ai/chat/modify
│   └── ocr.py              # ⬜ POST /ai/ocr/recognize
│
├── chains/                 # LangChain Chain（✅ ppt / word / pdf 已实现）
│   ├── ppt_chain.py        # ✅ PPT 大纲生成 Chain
│   ├── word_chain.py       # ✅ Word 内容生成 Chain
│   ├── pdf_chain.py        # ✅ PDF 内容生成 Chain
│   └── chat_chain.py       # ⬜ 对话修改 Chain
│
├── graph/                  # LangGraph 工作流（✅ generation_graph 已实现）
│   ├── generation_graph.py # ✅ 文档生成状态图 (RAG→Chain→校验→重试→构建)
│   └── chat_graph.py       # ⬜ 对话修改状态图
│
├── rag/                    # RAG 管线（✅ 已实现）
│   ├── ingestion.py        # ✅ 文档下载→解析→切分→嵌入→入库
│   ├── retrieval.py        # ✅ 混合检索 (向量 + BM25 + RRF)
│   └── vector_store.py     # ✅ Redis Stack 用户索引隔离 + CRUD
│
├── generator/              # Office 文件生成（⬜ 仅骨架 base.py）
│   ├── base.py             # ✅ 抽象基类
│   ├── ppt.py              # ✅ PPT 生成器（python-pptx，支持 5 种布局 + 3 套风格）
│   ├── word.py             # ✅ Word 生成器（python-docx）
│   └── pdf.py              # ✅ PDF 生成器（python-docx → LibreOffice）
│
├── services/               # 业务编排（✅ 已实现: generation）
│   ├── generation.py      # ✅ 文档生成业务编排（额度→生成→上传→退款，支持 PPT/Word/PDF）
│   ├── chat.py            # ⬜ 对话修改业务编排
│   └── ocr.py             # ⬜ OCR 业务逻辑（含 PDF/PPT/Word 图片 OCR）
│
├── worker/                 # 异步任务队列（⬜ 待实现）
│   ├── broker.py           # ⬜ RabbitMQ 连接管理 + 队列/交换机声明
│   ├── producer.py         # ⬜ 消息生产者（发布生成任务到队列）
│   └── consumer.py         # ⬜ 消息消费者（消费任务 → 生成 → 回调）
│
├── client/                 # Java 后端调用（✅ 已实现）
│   ├── http.py             # ✅ RSA-SHA256 签名 HTTP 客户端
│   ├── quota.py            # ✅ 额度消耗/退还
│   └── file.py             # ✅ 文件上传/下载/删除
│
├── core/                   # 基础设施（✅ 已实现）
│   ├── llm.py              # ✅ ChatModel 工厂
│   ├── embedding.py        # ✅ Embedding 工厂
│   ├── schemas.py          # ✅ Pydantic 模型
│   └── exceptions.py       # ✅ 异常 + 错误码
│
└── utils/                  # 工具（✅ 已实现）
    ├── file.py             # ✅ 临时文件路径/清理
    └── format.py           # ✅ JSON 安全解析
```

> ✅ 已实现  |  ⬜ 待实现

---

## 四、API 清单

### 4.1 AI 模块对外接口（Java 代理转发）

| 方法 | 路径 | 用途 | 状态 |
|------|------|------|------|
| POST | `/ai/material/upload` | 上传 RAG 参考素材并触发摄取 | ✅ |
| GET | `/ai/material/list` | 查询素材列表 | ✅ |
| DELETE | `/ai/material/{id}` | 删除素材（Java 回收站 + Redis 向量清理） | ✅ |
| POST | `/ai/ppt/generate` | 生成 PPT（支持 RAG） | ✅ |
| POST | `/ai/word/generate` | 生成 Word（支持 RAG） | ✅ |
| POST | `/ai/pdf/generate` | 生成 PDF（支持 RAG） | ✅ |
| POST | `/ai/chat/modify` | 对话式修改文档 | ⬜ |
| POST | `/ai/ocr/recognize` | 独立 OCR 识别接口 | ⬜ |
| GET | `/ai/task/{task_id}/status` | 查询异步任务状态 | ⬜ |

所有生成接口请求体统一包含 `material_ids` 和 `rag_enabled` 可选字段。

### 4.2 调用的 Java 内部接口

| 方法 | 路径 | 调用时机 | 状态 |
|------|------|---------|------|
| POST | `/api/internal/quota/consume` | 生成开始前扣额度 | ✅ |
| POST | `/api/internal/quota/refund` | 生成失败退额度 | ✅ |
| POST | `/api/internal/file/upload` | 文件生成完成后上传 | ✅ |

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

### 6.1 文档生成（API 快速响应 + Worker 异步执行）

**Phase 3 同步模式（初期）：** API 直接执行生成流程，请求阻塞直到完成。

**Phase 7 异步模式（后期）：** 生成任务推入消息队列，API 立即返回 `task_id`，前端轮询状态。

```
POST /ai/ppt/generate
  │
  ├─ 1. 校验 material_ids + rag_enabled
  ├─ 2. 扣减额度（quota.consume）
  ├─ 3. 入队 SAQ Queue → 立即返回 {task_id, status: "queued"}
  │
  └─ Worker 异步消费:
         ├─ RAG 检索 (可选) → 注入 context
         ├─ LangChain Chain 执行 (Prompt → LLM → JSON 解析)
         ├─ 解析成功? ── YES → 文件生成 → 上传 Java → 任务完成
         └─ NO (重试 ≤3 次) → 回到 LLM 调用 │ 仍失败 → 退款 (quota.refund)
```

### 6.2 对话修改

```
用户消息 → LangGraph 恢复会话状态
  → 判断是否需要 RAG → Chat Chain 输出修改指令 JSON
  → 代码执行增量编辑 (python-pptx/docx 对象模型)
  → 保存新文件 → 上传
```

### 6.3 异步任务架构（Phase 7 引入）

文档生成耗时较长（LLM 推理 10–30s + 文件生成 5–15s），必须异步化以避免 HTTP 超时和阻塞 FastAPI worker 线程。

**选型：RabbitMQ + aio-pika**

```
FastAPI (producer)                     Worker (consumer)
─────────────────                     ─────────────────
POST /ai/ppt/generate
  → publish message ───┐
  → return {task_id}   │              ┌─ consumer process
                        ├─ RabbitMQ ─▶├─ consumer process
客户端轮询:              │  Queue      └─ consumer process
GET /ai/task/{id} ← retrieve status ← Redis
```

**为什么选 RabbitMQ 而非 Celery / SAQ：**
- RabbitMQ 是成熟可靠的消息中间件，社区庞大、文档丰富、运维经验充足
- 支持灵活的路由策略（Direct / Topic / Fanout），便于后续扩展不同优先级和类型的任务
- 内置消息确认（ACK）+ 死信队列（DLX），天然支持重试和故障恢复
- aio-pika 提供 async 原生的 Python 客户端，完美兼容 FastAPI 的 async/await 模型
- 任务状态用 Redis 维护（复用已有实例），RabbitMQ 只做消息投递，职责清晰

**消息流设计：**

```
Exchange: birdhelp.tasks (direct)
  ├── Routing Key: ppt.generate   → Queue: birdhelp.ppt.queue
  ├── Routing Key: word.generate  → Queue: birdhelp.word.queue
  └── Routing Key: pdf.generate   → Queue: birdhelp.pdf.queue

Dead Letter Exchange: birdhelp.dlx (direct)
  └── Routing Key: failed → Queue: birdhelp.failed.queue
```

**任务生命周期状态机：**

```
queued → running → complete
               ↘ failed → retry (≤3) → complete
                            ↘ exhausted → DLX → refund_quota → failed
```

**Worker 内部流程（以 PPT 生成为例）：**

```python
import aio_pika
import json

async def on_ppt_message(message: aio_pika.IncomingMessage):
    async with message.process():
        payload = json.loads(message.body)
        user_id = payload["user_id"]

        # 1. RAG 检索（可选）
        context = await retrieve_formatted(user_id, payload["query"]) if payload["rag_enabled"] else ""

        # 2. Chain 执行（含重试，利用 DLX 实现最多 3 次）
        result = await ppt_chain.ainvoke({"context": context, **payload})
        parsed = parse_result(result)

        # 3. 文件生成
        file_path = await ppt_generator.generate(parsed)

        # 4. 上传 Java 后端
        await java_upload(file_path, user_id)

        # 5. 更新任务状态
        await update_task_status(payload["task_id"], "complete", result={...})
```

**API 端调用方式：**

```python
from worker.producer import publish_task

@router.post("/ppt/generate")
async def generate_ppt(payload: GenerateRequest, user: Depends(get_user)):
    task_id = await publish_task(
        routing_key="ppt.generate",
        user_id=user.id,
        payload=payload.model_dump(),
    )
    return ApiResponse(code=0, data={"task_id": task_id, "status": "queued"})
```

**任务状态查询接口：**

```
GET /ai/task/{task_id}/status → {"task_id": "...", "status": "running", "progress": 0.6}
GET /ai/task/{task_id}/result → {"task_id": "...", "status": "complete", "data": {...}}
```

任务元数据（状态、进度、结果）存储在 Redis 中，RabbitMQ 仅负责消息投递。

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
  - `ppt_chain.py` — ✅ PPT 大纲 Prompt + LLM + JSON OutputParser
  - `word_chain.py` — Word 内容 Prompt + LLM + JSON OutputParser
  - `pdf_chain.py` — PDF 内容 Prompt + LLM + JSON OutputParser
- Office 文件生成器：
  - `generator/ppt.py` — ✅ 基于 python-pptx 的 PPT 生成（5 种布局、3 套风格配色）
  - `generator/word.py` — 基于 python-docx 的 Word 生成（标题层级、段落样式、表格）
  - `generator/pdf.py` — python-docx → LibreOffice 无头转换
- LangGraph 生成状态图：
  - `graph/generation_graph.py` — ✅ RAG 检索 → Chain 执行 → JSON 校验 → 失败重试（≤3 次）
- 业务编排：
  - `services/generation.py` — ✅ 额度扣减 → LangGraph 执行 → 文件上传 → 失败退款
- 生成接口：`POST /ai/ppt/generate` ✅ / `/ai/word/generate` / `/ai/pdf/generate`
- 生成完成后上传文件至 Java 后端

### Phase 4: 对话修改（第 4–5 周）

**目标：** 用户通过多轮对话对已生成文档进行增量修改。

- Chat Chain：`chains/chat_chain.py`（对话 → 修改指令 JSON → 增量编辑）
- LangGraph 对话状态图：
  - `graph/chat_graph.py` — 会话管理、RAG 可选注入、修改 → 检查 → 重试循环
- 增量编辑能力（python-pptx / python-docx 对象模型操作）
- 多轮对话历史持久化
- `POST /ai/chat/modify` 接口
- OCR 兜底功能（延迟至时间充裕时实现，见 [七、Phase 6](#phase-6-ocr-兜底--图片识别后续迭代)）

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

### Phase 7: 异步任务队列（后续迭代）

> **优先级：低。** Phase 3–4 先以同步模式跑通，此阶段在时间充裕且生成耗时成为瓶颈时进行。

**背景：** 文档生成的耗时大头在 LLM 推理（10–30s）和 Office 文件构建（5–15s），单次生成累计可达 20–60 秒。如果 API 同步阻塞执行：HTTP 易超时、FastAPI worker 被占满、前端体验差。引入消息队列解耦提交与执行。

**技术选型：**

| 选项 | 放弃理由 | 选用理由 |
|------|----------|----------|
| Celery + Redis | 项目历史已将其移除（`bd2aede`, `refactor`），过于沉重 | — |
| **SAQ + Redis** | — | async 原生，不足千行代码；复用已有 Redis 做 broker，零额外运维；天然兼容 FastAPI；支持自动重试、优先级、Dashboard |

**子任务：**

1. **Worker 框架搭建**
   - `worker/broker.py` — SAQ Queue 初始化，复用已配置的 Redis 连接
   - `worker/tasks.py` — 生成任务协程定义（`ppt_task`、`word_task`、`pdf_task`）
   - `worker/jobs.py` — 业务回调：`on_complete`（通知/日志）、`on_failure`（退款 + 错误记录）
   - 依赖新增：`saq`

2. **API 层适配**
   - 生成接口（`ppt.py`、`word.py`、`pdf.py`）改为入队模式：`enqueue` → 返回 `task_id`
   - 新增 `GET /ai/task/{task_id}/status` — 实时查询任务状态
   - 新增 `GET /ai/task/{task_id}/result` — 完成后获取结果数据

3. **任务状态管理**
   - SAQ 内置 Job 状态 → 映射到前端展示：`queued` / `running` / `complete` / `failed`
   - 进度上报（可选）：`ctx.info["progress"] = 0.6`，前端轮询显示进度条
   - 任务过期清理：TTL 24 小时，避免 Redis 堆积

4. **Worker 进程管理**
   - 独立 Worker 进程：`saq worker.py --workers 3`（可配置并发数）
   - systemd / Docker 容器内与 API 一起启动（`Procfile` 或 `docker-compose`）
   - 优雅关闭：`SIGTERM → 等待当前任务完成 → 退出`

5. **故障恢复**
   - 任务重试：执行失败自动重试 ≤3 次（SAQ 内置）
   - 最终失败：退还额度（`quota.refund`）+ 记录错误日志
   - Worker 崩溃：任务重回队列（SAQ 的 `at_least_once` 语义 + Redis 持久化）

**架构对比：**

| | Phase 3 同步模式 | Phase 7 异步模式 |
|------|------|------|
| API 响应时间 | 20–60s（阻塞） | < 200ms（仅入队） |
| 并发能力 | 受 FastAPI worker 数限制 | Worker 可独立横向扩容 |
| 超时风险 | 高（HTTP/网关超时） | 无（WebSocket/轮询获取结果） |
| 故障隔离 | 生成崩溃影响 API | Worker 独立，崩溃任务自动重试 |
| 运维复杂度 | 低（无额外进程） | 中（需管理 Worker 进程） |

---

## 八、核心依赖

```text
# Web & AI 框架
fastapi                    langchain                  langchain-openai
langchain-community        langgraph                  langchain-text-splitters

# 文件生成
python-pptx                python-docx                pypdf

# 向量存储
redis

# HTTP 客户端
httpx

# 异步任务队列（Phase 7 新增）
saq                        # Simple Async Queue，Redis 背书，async 原生

# OCR（Phase 6 新增 PyMuPDF）
paddleocr                  paddlepaddle
PyMuPDF                    # PDF → 图片渲染，OCR 兜底

# 配置 & 日志
pydantic-settings          loguru
```
