# BirdHelp RAG 管线详解

> 检索增强生成（RAG）管线的完整流程、架构设计与模块说明。

---

## 一、管线概览

RAG 管线由两大阶段组成：**摄取（Ingestion）** 和 **检索（Retrieval）**。

```
┌─────────────────────────────────────────────────────────────────────┐
│                          摄  取  阶  段                               │
│                                                                      │
│  用户上传文件 → Java 后端存储 → 下载 → 解析 → 清洗切分 → 嵌入 → Redis │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          检  索  阶  段                               │
│                                                                      │
│  用户查询 → MultiQuery 改写 → Ensemble(向量 + BM25) → RRF 融合 → 去重 │
│     │                                                                │
│     └──→ 格式化 context 文本 → 注入 Prompt → LLM 生成                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、模块结构

```
rag/
├── ingestion.py       # 摄取管道：下载 → 解析 → 切分 → 嵌入 → 入库
├── retrieval.py       # 混合检索：向量 + BM25 + RRF 融合 + MultiQuery 改写
└── vector_store.py    # Redis Stack 向量库：用户级索引隔离 + CRUD

core/
├── embedding.py       # Embedding 模型工厂（OpenAI 兼容协议）
├── llm.py             # ChatModel 工厂（用于 MultiQuery 查询改写）
└── schemas.py         # 请求模型：rag_enabled / material_ids 字段

api/
└── material.py        # REST 接口：POST upload / GET list / DELETE {id}
```

---

## 三、摄取向段（Ingestion）

**入口：** `api/material.py` → `POST /ai/material/upload`

### 3.1 整体流程

```
用户上传（multipart/form-data）
  │
  ├─ 1. 校验扩展名（.pdf / .docx / .pptx / .txt）
  ├─ 2. 写入临时文件（/tmp/birdhelp/{uuid}.ext）
  ├─ 3. 上传至 Java 后端文件服务（client/file.py）
  ├─ 4. 从 Java 后端下载回临时路径
  ├─ 5. 文本解析（按扩展名分派 Loader）
  ├─ 6. RecursiveCharacterTextSplitter 切分
  ├─ 7. Embedding 嵌入 + 写入 Redis Stack
  └─ 8. 清理临时文件（finally）
```

### 3.2 文件格式与解析器

| 扩展名 | 解析方式 | 依赖库 |
|--------|----------|--------|
| `.pdf` | `PyPDFLoader`（LangChain 社区 Loader） | `pypdf` |
| `.docx` | 自定义 `_load_docx()`，遍历段落提取文本 | `python-docx` |
| `.pptx` | 自定义 `_load_pptx()`，遍历幻灯片文本框 | `python-pptx` |
| `.txt` | 自定义 `_load_txt()`，自动尝试 UTF-8 / GBK | 无 |

### 3.3 文本切分策略

使用 `RecursiveCharacterTextSplitter`：

| 参数 | 值 | 说明 |
|------|-----|------|
| `chunk_size` | 1000 | 每个块的最大字符数 |
| `chunk_overlap` | 200 | 相邻块之间的重叠字符数 |
| `separators` | `["\n\n", "\n", "。", ".", " ", ""]` | 优先按段落切，再按句子，最后按字符 |

分隔符优先级：**双换行 → 单换行 → 中文句号 → 英文句号 → 空格 → 逐字符**。

### 3.4 元数据注入

每个 chunk 的 Document 对象携带以下元数据：

```python
{
    "material_id": 123,          # Java 后端文件 ID
    "user_id": "456",            # 所属用户
    "file_name": "论文参考.pdf",  # 原始文件名
    "source": "java_upload",     # 来源标识
    "chunk_index": 0,            # 块序号（递增）
}
```

---

## 四、向量存储层（Vector Store）

**文件：** `rag/vector_store.py`

### 4.1 用户级索引隔离

每个用户在 Redis Stack 中拥有独立的搜索索引：

```
索引命名规则：rag_user_{user_id}
Redis Key 格式：rag_user_{user_id}:{doc_id}
```

这使得不同用户的向量数据完全隔离，查询时仅搜索当前用户的索引。

### 4.2 Redis 连接

全局懒加载单例，连接参数从 `config.Settings` 读取：

```
host / port / password → redis.Redis()
```

`decode_responses=False`（LangChain Redis 向量库要求 bytes 模式）。

### 4.3 索引 Schema

```python
_INDEX_SCHEMA = {
    "tag": [{"name": "material_id"}],
}
```

`material_id` 定义为 TAG 字段，支持按素材精确检索和删除。

### 4.4 核心操作

| 函数 | 功能 | 实现方式 |
|------|------|----------|
| `get_vectorstore(user_id)` | 获取用户向量库实例 | `langchain_community.vectorstores.redis.Redis` |
| `add_documents(user_id, docs)` | 嵌入并写入文档列表 | `store.add_documents(docs)` |
| `delete_by_material(user_id, material_id)` | 按素材删除所有 chunk | `FT.SEARCH @material_id:{id}` → `DEL keys` |
| `get_all_documents(user_id)` | 获取用户全部文档 | `SCAN rag_user_{id}:*` → `HGETALL` 重建 |

---

## 五、检索阶段（Retrieval）

**文件：** `rag/retrieval.py`

### 5.1 混合检索架构

```
用户查询
  │
  ├─ MultiQueryRetriever（LLM 改写为多个视角）
  │     │
  │     └─ EnsembleRetriever（集成检索器）
  │           │
  │           ├─ 向量检索（Redis 向量相似度） → top_k * 2 结果
  │           ├─ BM25 检索（关键词匹配）      → top_k * 2 结果
  │           └─ RRF 融合（权重 0.5 : 0.5）
  │
  └─ 去重（前 120 字符判重）→ 截断 top_k
```

### 5.2 向量检索

基于 Redis Stack 的向量相似性搜索，检索 `top_k * 2` 个候选（默认 10 个），为 RRF 融合提供语义相似度维度的召回。

### 5.3 BM25 关键词检索

每次检索时，从 Redis 加载当前用户的全部文档，使用 `BM25Retriever.from_documents()` 构建内存中的 BM25 索引。同样检索 `top_k * 2` 个候选。

**设计考量：** BM25 索引每次重建，而非持久化，是因为：
- 文档量级在千级以内，重建开销可接受
- 避免索引与 Redis 数据不一致
- 省去额外的索引同步机制

### 5.4 RRF 融合（Reciprocal Rank Fusion）

`EnsembleRetriever` 以 0.5:0.5 的权重融合两路检索结果：

```
RRF_score(d) = Σ 1 / (k + rank_i(d))
```

其中 `k=60`（LangChain 默认值），`rank_i(d)` 是文档 d 在第 i 个检索器中的排名。

### 5.5 MultiQuery 查询改写

当 `use_multiquery=True`（默认）时，使用 LLM 将用户原始查询改写成 3 个不同视角的查询变体，分别检索后合并结果。这能显著提高召回率，尤其是用户查询表述不精确时。

**改写 LLM：** 使用 `core/llm.py` 创建的 ChatOpenAI 实例（复用主模型配置）。

### 5.6 去重与截断

- 按 `page_content` 前 120 字符判重
- 去重后截断至 `top_k`（默认 5）
- 保持 RRF 融合后的排名顺序

### 5.7 格式化输出（`retrieve_formatted`）

检索结果格式化为 Prompt 可注入的文本块：

```
[参考片段 1 | 来源: 论文参考.pdf]
（文档内容...）

[参考片段 2 | 来源: 课程资料.docx]
（文档内容...）
```

---

## 六、素材删除流程

```
DELETE /ai/material/{id}
  │
  ├─ 1. Java 后端软删除（移入回收站）
  └─ 2. Redis 向量清理（FT.SEARCH @material_id:{id} → DEL）
```

删除操作先调 Java 后端接口，再清理 Redis 向量数据。Java 侧采用软删除（回收站机制），Redis 侧为物理删除（直接移除 chunks）。

---

## 七、配置参数一览

| 配置项 | 默认值 | 位置 | 说明 |
|--------|--------|------|------|
| `embedding_model` | `text-embedding-3-small` | `config.py` / `.env` | 嵌入模型名称 |
| `embedding_base_url` | `""`（回退到 `llm_base_url`） | `config.py` / `.env` | 嵌入 API 地址 |
| `embedding_api_key` | `""`（回退到 `llm_api_key`） | `config.py` / `.env` | 嵌入 API 密钥 |
| `embedding_dimension` | `1536` | `config.py` / `.env` | 向量输出维度 |
| `chunk_size` | `1000` | `config.py` / `.env` | 文本块大小（字符） |
| `chunk_overlap` | `200` | `config.py` / `.env` | 块间重叠字符数 |
| `retrieval_top_k` | `5` | `config.py` / `.env` | 最终返回文档数 |
| `retrieval_mode` | `"hybrid"` | `config.py` / `.env` | 检索模式 |
| `redis_host` / `redis_port` | `127.0.0.1` / `6379` | `config.py` / `.env` | Redis Stack 连接 |

### 嵌入配置回退机制

`effective_embedding_base_url` 和 `effective_embedding_api_key` 为计算属性——如果未单独配置嵌入模型凭据，自动回退到 LLM 的 `base_url` 和 `api_key`。这使得可以使用同一服务商同时提供 LLM 和 Embedding（如通义千问），也可以使用不同服务商。

---

## 八、错误处理

| 错误码 | 异常类 | 触发场景 |
|--------|--------|----------|
| `2003` | `EmbeddingError` | 嵌入模型调用失败 |
| `3003` | `MaterialIngestionError` | 文档摄取流程失败 |
| — | `MaterialFormatError` | 上传文件格式不支持 |

摄取失败时，`api/material.py` 的 `upload_material` 会尝试清理 Java 后端已上传的文件（尽力而为）。

---

## 九、技术依赖

```text
langchain              # RAG 编排（Retriever / MultiQuery / Ensemble）
langchain-community    # PyPDFLoader / Redis 向量库 / BM25Retriever
langchain-openai       # OpenAIEmbeddings / ChatOpenAI（OpenAI 兼容协议）
langchain-text-splitters  # RecursiveCharacterTextSplitter
redis                  # Redis Stack 客户端
pypdf                  # PDF 文本提取
python-docx            # .docx 文本提取
python-pptx            # .pptx 文本提取
```

---

## 十、待扩展能力（Phase 2+）

以下字段和目录已在代码中预留：

| 项目 | 位置 | 说明 |
|------|------|------|
| `material_ids` 过滤 | `core/schemas.py` → `GenerateRequest` | 限定检索范围至特定素材 |
| `chains/` | 目录（占位） | LangChain Chain：Prompt + LLM + OutputParser |
| `graph/` | 目录（占位） | LangGraph 状态图：RAG → 生成 → 检查 → 重试 |
| `services/` | 目录（占位） | 业务编排层 |
| `generator/` | 目录（骨架） | Office 文件生成器具体实现 |
