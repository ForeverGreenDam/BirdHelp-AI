# 对话修改 + 文档预览 — 完整设计方案

> v5.2 | 2026-05-30 | 就绪，可直接按此执行

---

## 执行指南（新会话入口）

### 项目位置

| 端 | 绝对路径 |
|------|------|
| Python AI 模块 | `E:\Python\BirdHelp` |
| Java 后端 | `E:\JAVA\JAVAproject\BirdHelp` |

### 核心决策速览

| 决策 | 结论 |
|------|------|
| 预览 | Java 端负责（LibreOffice → PDFBox → OSS），Python 不参与 |
| 大纲 | 生成时回传 Java 存入 `file_record.outline`，修改时 Python 从 Java API 取 |
| 修改策略 | LLM 改大纲 → Generator 重建文件，不跑 QA |
| 文件版本 | `file_record.version_of` 形成单向链表，列表只展示链尾 |
| 会话归属 | 对话窗口隶属 `session_id`，不隶属具体文件 |
| RAG | `source=1`（用户上传）才入库，`source=2`（AI 生成）不入库 |
| 存储 | MySQL = 唯一数据源，Java = 唯一 DB 操作者，Python 永不直连 MySQL |

### 实施顺序

```
Step 0: 阅读 §〇~§二 理解职责边界和数据流

===== Java 端（先做，Python 依赖这些 API）=====
J1: MySQL DDL（§四.4.1）→ 3 张表 / 3 列
J2: Entity + Mapper（§四.4.4-4.5）
J3: TaskInternalController 改（§四.4.4）→ 回调时写 outline
J4: ChatSessionService + ChatInternalController（§四.4.5）→ 4 个内部 API
J5: PreviewService（§四.4.2-4.3）→ LibreOffice + PDFBox 渲染管道
J6: FileController 新增 preview 端点
J7: FileServiceImpl.doUpload → source=1 才调 RAG（§二.2.6）

===== Python 端 =====
P0: broker/consumer.py + broker/schemas.py（§三.3.7）→ 回调携带 outline
P1: modify/schemas.py → Pydantic 模型
P2: modify/client.py → Java API 客户端
P3: modify/parser.py → 降级兜底
P4: modify/chain.py → LLM Prompt
P5: modify/graph.py → LangGraph 状态图（无 QA）
P6: modify/service.py → 业务编排
P7: modify/api.py → 2 个 HTTP 接口
P8: api/router.py + config.py → 注册

===== 联调 =====
L1: 生成 → 大纲入库 → 预览 → 修改 → 版本链 → 端到端验证
```

### 改动清单

#### Python 端新增文件 (7 个)

| 文件 | 对应章节 |
|------|:--:|
| `modify/__init__.py` | — |
| `modify/schemas.py` | §三.3.2 |
| `modify/client.py` | §三.3.5 |
| `modify/parser.py` | §三.3.6 |
| `modify/chain.py` | §三.3.3 |
| `modify/graph.py` | §三.3.4 |
| `modify/service.py` | §三.3.3 |
| `modify/api.py` | §三.3.2 |

#### Python 端修改文件 (4 个)

| 文件 | 改动 | 章节 |
|------|------|:--:|
| `broker/consumer.py` | TaskCallback 构造加 `outline` 字段 | §三.3.7 |
| `broker/schemas.py` | `TaskCallback` 新增 `outline: str \| None` | §三.3.7 |
| `api/router.py` | `include_router(modify_router)` | §三.3.7 |
| `config.py` | `modify_max_retries: int = 3` | §三.3.7 |

#### Java 端新增文件 (10 个)

| 文件 | 对应章节 |
|------|:--:|
| `entity/ChatSession.java` | §四.4.5 |
| `entity/ChatMessage.java` | §四.4.5 |
| `mapper/ChatSessionMapper.java` | §四.4.5 |
| `mapper/ChatMessageMapper.java` | §四.4.5 |
| `service/ChatSessionService.java` | §四.4.5 |
| `service/impl/ChatSessionServiceImpl.java` | §四.4.5 |
| `internal/ChatInternalController.java` | §四.4.6 |
| `service/PreviewService.java` | §四.4.2 |
| `service/impl/PreviewServiceImpl.java` | §四.4.3 |
| `vo/PreviewVO.java`（含 PreviewPage） | §四.4.2 |

#### Java 端修改文件 (7 个)

| 文件 | 改动 | 章节 |
|------|------|:--:|
| `sql/file_record.sql` | 新增 `outline`、`preview_pages`、`version_of` 列 | §四.4.1 |
| `sql/chat_session.sql` | 新建表 | §四.4.1 |
| `sql/chat_message.sql` | 新建表 | §四.4.1 |
| `entity/FileRecord.java` | +`outline`、+`previewPages`、+`versionOf` | §四.4.4 |
| `dto/TaskCallbackRequest.java` | +`outline` | §四.4.4 |
| `dto/FileInternalUploadDTO.java` | +`versionOf`（可选） | §四.4.4 |
| `vo/FileRecordVO.java` | +`outline`、+`versionOf`（按需填充） | §四.4.4 |
| `internal/TaskInternalController.java` | 回调时写 outline 到 DB | §四.4.4 |
| `controller/FileController.java` | +`GET /api/file/{id}/preview` | §四.4.3 |
| `service/impl/FileServiceImpl.java` | `source==1` 才调 RAG | §二.2.6 |
| `pom.xml` | PDFBox + TwelveMonkeys 依赖 | §四.4.3 |

---

## 〇、职责边界

```
前端 ←→ Java 后端 ←RSA签名→ Python AI 模块

预览（SVG/PNG 渲染） → Java 负责，Python 不参与
大纲（结构化 JSON）  → Java 存 MySQL，Python 通过内部 API 获取
对话修改（LLM+重建） → Python 负责
会话记忆             → Java 存 MySQL，Python 通过内部 API 读写

铁律：MySQL = 唯一数据源  |  Python 永不直连 MySQL
```

---

## 一、为什么必须要大纲

文档生成时 LLM 产出的大纲 JSON 包含 `layout_type`、`visual_plan`、`image_query` 等元信息。这些信息在文件生成后被"烧制"进视觉样式，**逆向解析保真度仅 40-50%**：

| 状态 | 字段 |
|:----:|------|
| ✅ 可恢复 | `page_number`、`title`、`body` 文本、`has_image` |
| ⚠️ 部分 | `chart_data`（格式不同）、`table_data`（丢元信息） |
| ❌ 丢失 | **`layout_type`**、**`visual_plan`**、**`image_query`**、**`style`** |

`layout_type` 是致命损失——无法区分 `big_number` / `grid_cards` / `timeline` / `text_only`。对话修改时 AI 看不到真实布局，修改质量大打折扣。

**结论：生成时将大纲随回调传给 Java，存入 `file_record.outline`。修改时 Python 从 Java API 取。**

---

## 二、整体数据流

### 2.1 大纲如何进入 MySQL

```
Python broker 生成文档
  → 上传文件到 Java（获 file_id）
  → 成功回调 TaskCallback 中新增 outline 字段（JSON 字符串）
  → Java TaskInternalController: UPDATE file_record SET outline=? WHERE id=?
```

### 2.2 预览如何工作（纯 Java）

```
前端 → GET /api/file/{fileId}/preview → Java:

  ① 查 file_record 获取文件路径 + outline + preview_pages
  ② 三级缓存判断:
     - Redis 热缓存 (preview:{fileId}, TTL 1h) → fileHash 一致 → 直接返回
     - MySQL file_record.preview_pages → fileHash 一致 → 返回 + 回填 Redis
     - 都不命中 → 重新渲染
  ③ 渲染管道: LibreOffice 无头转 PDF → PDFBox 逐页渲染 150 DPI PNG → 上传 OSS
  ④ 页面 URL 持久化到 file_record.preview_pages (JSON)，Redis 热缓存 1h
  ⑤ 返回: { fileId, totalPages, pages: [{pageNumber, imageUrl, layoutType, title}] }

  每页的 layoutType / title 标注来自 file_record.outline
```

### 2.3 对话修改如何工作

```
前端 → Java 代理 → POST /ai/chat/modify → Python modify 模块:

  ① 调 Java API: GET /internal/file/{id}/outline → 获取大纲（100% 保真）
                 POST /internal/chat/session → 获取/创建会话 + 历史消息
  ② LLM Chat Chain: 大纲 + 历史 + 用户消息 → 修改后大纲 + AI 回复 + 变更列表
  ③ 结构校验 → 失败重试 ≤3 次
  ④ Generator 重建文件 → 上传 Java（获新 file_id）
     上传时携带 version_of=上一版file_id，Java 据此跳过 RAG
  ⑤ 调 Java API: PUT /internal/file/{id}/outline（存新大纲）
                 POST /internal/chat/session/{id}/messages（追加对话，消息中记录 file_id）
  ⑥ 返回: AI 回复 + 新大纲 + 新 file_id
```

### 2.4 文件版本链与列表可见性

每次修改生成新文件，形成版本链：

```
A.version_of = NULL       （原始生成，链头）
B.version_of = A.id       （第1轮修改）
C.version_of = B.id       （第2轮修改）
D.version_of = C.id       （第3轮修改，链尾）
```

**`file_record` 新增 `version_of` 列（BIGINT NULL，自引用）：**

```sql
ALTER TABLE `file_record`
    ADD COLUMN `version_of` bigint NULL
    COMMENT '上一版本文件ID（修改链，NULL=原始文件）'
    AFTER `source`;
```

**文件列表查询（只展示链尾）：**

```sql
SELECT * FROM file_record
WHERE deleted = 0 AND user_id = ?
AND id NOT IN (
    SELECT DISTINCT version_of FROM file_record
    WHERE version_of IS NOT NULL AND deleted = 0
)
```

效果：

| 文件 | version_of | 被谁指向 | 列表可见 |
|------|:--:|------|:--:|
| A | NULL | B 指向它 | ❌ |
| B | A.id | C 指向它 | ❌ |
| C | B.id | D 指向它 | ❌ |
| D | C.id | 无人指向 | ✅ |
| E | NULL | 无人指向 | ✅（另一个独立文件）|

**一个字段实现自动级联隐藏。** 链尾天然就是最新版，无需 `is_latest` 标记，无需定时清理。

### 2.5 会话与文件的绑定关系

```
chat_session:
  original_file_id = A       ← 修改的起点（用户点击 A 的 [修改] 按钮时记录）
  current_file_id  = D       ← 当前最新版本（每次修改后更新）

chat_message:
  每条 assistant 消息记录 file_id ← 该轮产出了哪个文件

对话窗口 → 隶属于 session_id（不是 A 也不是 D）
预览区   → 默认展示 current_file_id（D），可切换查看历史版本
文件列表 → 只展示链尾文件（D）
```

用户可在对话区点击历史消息回顾任意版本，也可"回滚到某一版"——以该版为起点继续修改，旧的链尾被新链尾取代。

### 2.6 RAG 去重：AI 生成内容不入库

**核心原则：RAG 向量库只存"参考资料"，不存"输出成果"。**

| 文件来源 | source | 是否 RAG 入库 | 理由 |
|------|:--:|:--:|------|
| 用户上传的素材 | 1 | ✅ | 这是参考资料，RAG 的基石 |
| AI 生成的文档 | 2 | ❌ | 这是输出成果，本身就是参考素材写的，语义与素材高度重叠，入库是噪音 |
| AI 修改的版本 | 2 | ❌ | 同上，且版本链上的旧版已不可见 |

实现很简单——`FileServiceImpl.doUpload` 中加一个 `source` 判断：

```java
// source == 1（用户上传）→ RAG 入库
// source == 2（AI 生成）→ 跳过
if (source == 1) {
    aiModuleCaller.uploadMaterial(content, originalName, userId, projectId, record.getId());
}
```

**这比之前讨论的"versionOf != null 跳过 RAG"更根本。** `version_of` 字段完全不需要参与 RAG 逻辑——`source=2` 的文件从一开始就不会入库，无论它们处于版本链的什么位置。

---

## 三、Python 端设计

### 3.1 新增目录 `modify/`

```
modify/
├── api.py         # FastAPI Router: /ai/chat/modify, /ai/chat/discuss
├── schemas.py     # Pydantic 模型
├── chain.py       # LLM 对话修改 Chain（Prompt + 结构化输出）
├── graph.py       # LangGraph 状态图（无 QA）
├── client.py      # 调用 Java 内部 API（获取大纲、会话 CRUD）
├── parser.py      # 文档逆向解析（降级兜底：旧文件无 outline 时）
└── service.py     # 业务编排
```

### 3.2 两个接口

| 接口 | 用途 | LLM | 重建文件 |
|------|------|:--:|:--:|
| `POST /ai/chat/modify` | 对话修改文档 | ✅ | 可选 |
| `POST /ai/chat/discuss` | 仅讨论/问答 | ✅ | ❌ |

**请求核心字段：** `session_id`、`file_id`、`doc_type`、`message`、`history`(可选)、`regenerate_file`(默认 true)

**响应核心字段：** `reply`、`outline`(修改后完整大纲)、`changes[]`(变更摘要)、`file_id`(新文件)、`file_url`

### 3.3 ChatGraph 与 GenerationGraph 的区别

| 节点 | GenerationGraph | ChatGraph |
|------|:--:|:--:|
| RAG 检索 | ✅ | ❌ |
| QA 评分+修复 | ✅ | ❌ |
| 图片搜索 | ✅ | ❌ |
| LLM 生成大纲 | ✅ 从零生成 | ✅ 基于现有大纲修改 |
| JSON 结构校验 | ✅ | ✅ |
| 重建文件 | ✅ | ✅ |

**不跑 QA 的原因：** 用户修改是主观意图（"把标题改激进些"、"删掉这页"），QA 不应拦截或改写。

### 3.4 ChatGraph 结构

```
START → chat_analyze(LLM修改) → validate_output → [pass→rebuild→upload→END]
                                        ↓
                                  [retry ≤3次] [fail→END]
```

### 3.5 `modify/client.py` — 调用的 Java 内部 API

| Java API | 用途 | 备注 |
|------|------|------|
| `GET /internal/file/{id}/outline` | 获取大纲 | |
| `PUT /internal/file/{id}/outline` | 更新大纲 | |
| `POST /internal/chat/session` | 获取或创建会话 | |
| `POST /internal/chat/session/{id}/messages` | 追加消息 | 消息中带 file_id |
| `POST /internal/file/upload` | 上传修改后的文件 | 表单中携带 `versionOf` 字段，Java 据此建立版本链 |

### 3.6 `modify/parser.py` — 降级兜底

仅在 `file_record.outline` 为空时（旧文件）使用。从 .pptx/.docx 逆向提取大纲，返回时标注 `source: "file_parse"`。

### 3.7 对已有 Python 文件的改动

| 文件 | 变更 | 行数 |
|------|------|:--:|
| `broker/consumer.py` | 回调时 `TaskCallback` 构造加 `outline` 字段 | ~2 |
| `broker/schemas.py` | `TaskCallback` 新增 `outline: str \| None` | ~5 |
| `api/router.py` | `include_router(modify_router)` | +1 |
| `config.py` | `modify_max_retries: int = 3` | +1 |

---

## 四、Java 端设计

### 4.1 MySQL 变更

```sql
-- ① file_record 新增 3 列
ALTER TABLE `file_record`
    ADD COLUMN `outline` MEDIUMTEXT NULL
        COMMENT '文档大纲 JSON（AI 模块回调回传）'
        AFTER `file_url`,
    ADD COLUMN `preview_pages` MEDIUMTEXT NULL
        COMMENT '预览页面缓存 JSON'
        AFTER `outline`,
    ADD COLUMN `version_of` bigint NULL
        COMMENT '上一版本文件ID（修改链，NULL=原始文件/独立文件）'
        AFTER `source`;

-- ② 会话主表（元信息）
CREATE TABLE `chat_session` (
    `id` bigint NOT NULL AUTO_INCREMENT,
    `session_id` varchar(64) NOT NULL COMMENT '会话ID（UUID v4）',
    `user_id` bigint NOT NULL,
    `project_id` bigint NOT NULL,
    `original_file_id` bigint NOT NULL COMMENT '修改的起点文件ID',
    `current_file_id` bigint DEFAULT NULL COMMENT '当前最新版本文件ID',
    `doc_type` varchar(10) NOT NULL COMMENT 'ppt/word/pdf',
    `message_count` int NOT NULL DEFAULT 0,
    `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `del_flag` tinyint DEFAULT 0,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_session_id` (`session_id`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话修改会话表';

-- ③ 消息明细表（每条消息一行，规范化存储）
CREATE TABLE `chat_message` (
    `id` bigint NOT NULL AUTO_INCREMENT,
    `session_id` varchar(64) NOT NULL COMMENT '关联 chat_session.session_id',
    `role` varchar(16) NOT NULL COMMENT 'user / assistant',
    `content` TEXT NOT NULL COMMENT '消息内容',
    `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_session_time` (`session_id`, `create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='对话消息明细表';
```

> **说明：** 对话消息拆为独立的 `chat_message` 表而非 JSON 字段，好处是单条消息用 TEXT（64KB）足够、可按时间排序/分页、无需担心 MEDIUMTEXT 容量。`MEDIUMTEXT` 是 MySQL 4.1+ 原生类型（上限 16 MB），一个 50 页 PPT 大纲约 50-200 KB，完全兼容。

### 4.2 预览图 URL 存储流程

```
首次预览:
  原始文件 → LibreOffice 转 PDF → PDFBox 逐页渲染 PNG → 上传 OSS（获 URL）
    → 写入 file_record.preview_pages:
        {"fileHash":"abc123","pages":[
          {"pageNumber":1,"imageUrl":"https://oss/.../page_1.png","layoutType":"cover","title":"..."},
          ...
        ]}
    → Redis 热缓存 preview:{fileId}（TTL 1h）

后续预览:
  ① Redis 命中 + fileHash 一致 → 直接返回
  ② Redis 未命中 → 查 MySQL preview_pages → fileHash 一致 → 返回 + 回填 Redis
  ③ fileHash 不一致 → 重新渲染 → 更新 MySQL + Redis

文件被修改后:
  旧 file_id → 旧 preview_pages 不变，仍然有效
  新 file_id → preview_pages 初始为 NULL → 首次预览触发渲染
```

### 4.3 预览实现要点

| 要点 | 方案 |
|------|------|
| 转换引擎 | LibreOffice 无头模式（Docker 已内置） |
| PDF 渲染 | PDFBox `PDFRenderer.renderImageWithDPI(150)` |
| 输出格式 | PNG，150 DPI（屏幕预览足够） |
| 图片存储 | 上传 OSS，URL 存入 `preview_pages` JSON |
| 布局标注 | 从 `file_record.outline` 解析每页的 `layout_type` / `title` |
| 缓存策略 | Redis 1h 热缓存 + MySQL `preview_pages` 持久化 + fileHash 校验 |

### 4.4 已有文件改动

| 文件 | 变更 |
|------|------|
| `entity/FileRecord.java` | 新增 `outline`、`previewPages`、`versionOf` 字段 |
| `service/impl/FileServiceImpl.java` | `uploadByAi` 中 `versionOf != null` 时跳过 RAG 入库 |
| `dto/TaskCallbackRequest.java` | 新增 `outline` 字段 |
| `dto/FileInternalUploadDTO.java` | 新增 `versionOf` 字段（可选，修改版上传时携带） |
| `vo/FileRecordVO.java` | 新增 `outline`、`versionOf` 字段（按需填充） |
| `internal/TaskInternalController.java` | 回调成功时 `UPDATE file_record SET outline=?` |
| `controller/FileController.java` | 新增 `GET /api/file/{id}/preview` |

### 4.5 新增文件

| 文件 | 职责 |
|------|------|
| `entity/ChatSession.java` | 会话实体 |
| `entity/ChatMessage.java` | 消息明细实体 |
| `mapper/ChatSessionMapper.java` | MyBatis-Plus Mapper |
| `mapper/ChatMessageMapper.java` | MyBatis-Plus Mapper |
| `service/ChatSessionService.java` + Impl | getOrCreate / appendMessage / getMessages / delete |
| `internal/ChatInternalController.java` | 4 个内部 API（大纲读写 + 会话 CRUD） |
| `service/PreviewService.java` + Impl | LibreOffice → PDFBox 渲染管道 |
| `vo/PreviewVO.java` | 预览响应：fileId、totalPages、pages[] |
| `vo/PreviewPage.java` | 单页数据：pageNumber、imageUrl、layoutType、title |
| `pom.xml` | 新增 PDFBox + TwelveMonkeys imageio 依赖 |

### 4.6 ChatInternalController 接口清单

| 方法 | 路径 | 用途 | Python 调用 |
|------|------|------|:--:|
| `GET` | `/internal/file/{id}/outline` | 读取大纲 | ✅ |
| `PUT` | `/internal/file/{id}/outline` | 更新大纲 | ✅ |
| `POST` | `/internal/chat/session` | 获取或创建会话（幂等） | ✅ |
| `POST` | `/internal/chat/session/{id}/messages` | 追加消息 | ✅ |
| `DELETE` | `/internal/chat/session/{id}` | 删除会话 | ❌ |

---

## 五、实施计划

### Python 端（5.5 天）

| # | 内容 | 工期 |
|:--:|------|:--:|
| P0 | `broker/` 回调携带 outline | 0.5 天 |
| P1 | `modify/schemas.py` + `modify/client.py` | 0.5 天 |
| P2 | `modify/parser.py`（降级兜底） | 1 天 |
| P3 | `modify/chain.py`（LLM Prompt 调优） | 1.5 天 |
| P4 | `modify/graph.py`（无 QA 状态图） | 1 天 |
| P5 | `modify/service.py` + `modify/api.py` | 0.5 天 |
| P6 | 路由注册 + 配置 | 0.5 天 |

### Java 端（4 天）

| # | 内容 | 工期 |
|:--:|------|:--:|
| J1 | DDL + FileRecord/TaskCallback/FileRecordVO 改动 | 0.5 天 |
| J2 | chat_session + chat_message 表、Entity、Mapper | 0.5 天 |
| J3 | ChatSessionService + ChatInternalController | 1 天 |
| J4 | TaskInternalController 改（写 outline 到 DB） | 0.5 天 |
| J5 | PreviewService + PreviewServiceImpl | 1 天 |
| J6 | FileController 新增 preview 端点 | 0.5 天 |

### 联调（1 天）

**总计：7 天**（Python/Java 可并行）

---

## 六、修改能力覆盖

| 修改类型 | PPT | Word | PDF |
|----------|:--:|:----:|:---:|
| 修改标题/正文 | ✅ | ✅ | ❌ |
| 增删页面/章节 | ✅ | ✅ | ❌ |
| 调整顺序 | ✅ | ✅ | ❌ |
| 切换布局类型 | ✅ | — | — |
| 修改图表/表格数据 | ✅ | ✅ | ❌ |
| 改变整体风格/配色 | ✅ | ✅ | ❌ |
| 仅讨论/给建议 | ✅ | ✅ | ✅ |

---

## 七、风险与对策

| 风险 | 对策 |
|------|------|
| 旧文件无 outline | parser 逆向解析降级；预览无布局标注 |
| LibreOffice 转换超时 | 60s 超时 + 后台异步渲染 + 首次返回"渲染中" |
| 预览图片 OSS 存储成本 | 1h Redis 热缓存 + MySQL 持久化 + 150 DPI 压缩 |
| LLM 输出大纲格式异常 | 重试 ≤3 次；失败仅返回文本回复 |
| 大纲过大导致 context 溢出 | 截断 body 保留标题结构 |
| Java API 调用超时（Python 侧） | 3 次重试 + 优雅降级 |
