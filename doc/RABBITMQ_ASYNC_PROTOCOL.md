# BirdHelp 文档生成异步消息协议 v1.0

> **目标**：将文档生成从同步 HTTP 改为 RabbitMQ 异步消费，解决 QA 评分耗时导致前端超时的问题。
>
> **角色**：Java 后端 = 生产者（Producer），Python AI 模块 = 消费者（Consumer）。
>
> **对接规则**：双方严格按本文档开发，字段名、类型、枚举值不得有任何偏差。

---

## 一、RabbitMQ 拓扑结构

### 1.1 核心组件

| 组件                   | 名称                              | 类型      | durable | 说明         |
|----------------------|---------------------------------|---------|---------|------------|
| Exchange             | `birdhelp.doc.generation`       | topic   | true    | 文档生成任务交换机  |
| Queue                | `birdhelp.doc.generation.tasks` | classic | true    | 主任务队列      |
| Routing Key          | `doc.generate.ppt`              | —       | —       | PPT 生成任务   |
| Routing Key          | `doc.generate.word`             | —       | —       | Word 生成任务  |
| Routing Key          | `doc.generate.pdf`              | —       | —       | PDF 生成任务   |
| Dead Letter Exchange | `birdhelp.doc.generation.dlx`   | topic   | true    | 死信交换机      |
| Dead Letter Queue    | `birdhelp.doc.generation.dlq`   | classic | true    | 死信队列（人工处理） |

### 1.2 队列参数

```
birdhelp.doc.generation.tasks:
  x-dead-letter-exchange: birdhelp.doc.generation.dlx
  x-dead-letter-routing-key: doc.generate.dlq
  x-message-ttl: 600000           # 消息 TTL = 10 分钟（单次生成超时上限）
  x-max-priority: 10              # 支持消息优先级 0-10
```

### 1.3 绑定关系

```
birdhelp.doc.generation  →  doc.generate.ppt   →  birdhelp.doc.generation.tasks
birdhelp.doc.generation  →  doc.generate.word  →  birdhelp.doc.generation.tasks
birdhelp.doc.generation  →  doc.generate.pdf   →  birdhelp.doc.generation.tasks
birdhelp.doc.generation.dlx  →  doc.generate.dlq  →  birdhelp.doc.generation.dlq
```

> **说明**：当前 3 种文档类型路由到同一队列。后续如需独立扩容，增加新队列并改绑 routing key 即可，消息格式不变。

---

## 二、消息规范

### 2.1 消息格式

- **序列化**：JSON（UTF-8 编码）
- **Content-Type**：`application/json`
- **Content-Encoding**：无（不压缩）
- **Delivery Mode**：2（persistent，持久化到磁盘）

### 2.2 消息体 Schema

```json
{
  "version": "1.0",
  "taskId": "550e8400-e29b-41d4-a716-446655440000",
  "callbackId": "req_20260523_abc123",
  "docType": "ppt",
  "userId": "42",
  "projectId": "100",
  "topic": "人工智能发展史",
  "language": "zh",
  "extraPrompt": "请重点介绍深度学习部分",
  "materialIds": [
    "mat_001",
    "mat_002"
  ],
  "ragEnabled": false,
  "style": "academic",
  "slideCount": 10,
  "enableImages": true,
  "docSubtype": "essay",
  "wordCount": 2000,
  "timestamp": 1716451200000
}
```

### 2.3 字段定义（必填/选填）

#### 通用字段（所有 docType 必填）

| 字段           | 类型      | 必填    | 说明                                             |
|--------------|---------|-------|------------------------------------------------|
| `version`    | string  | **是** | 协议版本，当前固定 `"1.0"`。Python 收到不支持的版本应 NACK 不重试    |
| `taskId`     | string  | **是** | 任务唯一 ID，UUID v4 格式（36 字符，含连字符）。Java 生成，用于全链路追踪 |
| `callbackId` | string  | **是** | Java 端原始请求 ID，用于关联业务流水                         |
| `docType`    | string  | **是** | 文档类型，枚举：`"ppt"` \| `"word"` \| `"pdf"`         |
| `userId`     | string  | **是** | 用户 ID（Java 端为 Long，传字符串避免精度问题）                 |
| `projectId`  | string  | **是** | 项目 ID，用于知识库隔离和文件归属                             |
| `topic`      | string  | **是** | 文档主题/标题，非空，最大 500 字符                           |
| `apiKey`     | string  | **是** | LLM API 密钥，明文。由 Java 从数据库解密后传入，Python 直接使用     |
| `baseUrl`    | string  | **是** | LLM API 基础地址                                     |
| `modelName`  | string  | **是** | 使用的模型名称                                         |
| `language`   | string  | **是** | 语言，枚举：`"zh"` \| `"en"`                         |
| `ragEnabled` | boolean | **是** | 是否启用 RAG 检索。false 时忽略 materialIds              |
| `timestamp`  | number  | **是** | 消息生产时间戳（毫秒），用于延迟监控，非签名用                        |

#### 选填通用字段

| 字段             | 类型             | 必填 | 默认值          | 说明                                                                                          |
|----------------|----------------|----|--------------|---------------------------------------------------------------------------------------------|
| `extraPrompt`  | string\|null   | 否  | `null`       | 用户补充指令，最大 2000 字符                                                                           |
| `materialIds`  | string[]\|null | 否  | `null`       | RAG 素材 ID 列表，ragEnabled=true 时有效                                                            |
| `style`        | string         | 否  | `"academic"` | 设计风格，枚举：`"academic"` \| `"business"` \| `"creative"` \| `"minimal"` \| `"tech"` \| `"warm"` |
| `enableImages` | boolean        | 否  | `true`       | 是否自动搜索配图                                                                                    |

#### PPT 专属字段（docType = "ppt" 时）

| 字段           | 类型     | 必填 | 默认值  | 约束                  | 说明    |
|--------------|--------|----|------|---------------------|-------|
| `slideCount` | number | 否  | `10` | 1 ≤ slideCount ≤ 50 | 幻灯片页数 |

#### Word 专属字段（docType = "word" 时）

| 字段           | 类型     | 必填 | 默认值       | 约束                                                 | 说明    |
|--------------|--------|----|-----------|----------------------------------------------------|-------|
| `docSubtype` | string | 否  | `"essay"` | `"essay"` \| `"report"` \| `"letter"` \| `"paper"` | 文档子类型 |
| `wordCount`  | number | 否  | `2000`    | 500 ≤ wordCount ≤ 10000                            | 目标字数  |

#### PDF 专属字段（docType = "pdf" 时）

| 字段           | 类型     | 必填 | 默认值        | 约束                                   | 说明    |
|--------------|--------|----|------------|--------------------------------------|-------|
| `docSubtype` | string | 否  | `"report"` | `"report"` \| `"resume"` \| `"form"` | 文档子类型 |

> **严格规则**：Java 端发送的字段必须与上表一致，多余字段 Python 忽略（forward compatible），缺失必填字段 Python NACK 并记日志。

### 2.4 完整示例

#### PPT 消息

```json
{
  "version": "1.0",
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "callbackId": "req_20260523_001",
  "docType": "ppt",
  "userId": "42",
  "projectId": "100",
  "topic": "人工智能技术综述",
  "apiKey": "sk-xxxx",
  "baseUrl": "https://api.openai.com/v1",
  "modelName": "gpt-4o",
  "language": "zh",
  "extraPrompt": "每页不超过5个要点",
  "materialIds": [
    "mat_001",
    "mat_002"
  ],
  "ragEnabled": true,
  "style": "tech",
  "slideCount": 15,
  "enableImages": true,
  "timestamp": 1716451200000
}
```

#### Word 消息

```json
{
  "version": "1.0",
  "taskId": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
  "callbackId": "req_20260523_002",
  "docType": "word",
  "userId": "42",
  "projectId": "100",
  "topic": "深度学习在NLP中的应用",
  "apiKey": "sk-xxxx",
  "baseUrl": "https://api.openai.com/v1",
  "modelName": "gpt-4o",
  "language": "zh",
  "extraPrompt": null,
  "materialIds": null,
  "ragEnabled": false,
  "style": "academic",
  "enableImages": true,
  "docSubtype": "paper",
  "wordCount": 5000,
  "timestamp": 1716451210000
}
```

#### PDF 消息

```json
{
  "version": "1.0",
  "taskId": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "callbackId": "req_20260523_003",
  "docType": "pdf",
  "userId": "42",
  "projectId": "100",
  "topic": "2025年度项目报告",
  "apiKey": "sk-xxxx",
  "baseUrl": "https://api.openai.com/v1",
  "modelName": "gpt-4o",
  "language": "zh",
  "extraPrompt": null,
  "materialIds": null,
  "ragEnabled": false,
  "style": "business",
  "enableImages": false,
  "docSubtype": "report",
  "timestamp": 1716451220000
}
```

---

## 三、消费者 ACK / NACK 规则

Python 消费者处理消息时必须遵守以下规则：

| 场景                  | 动作            | requeue   | 说明                    |
|---------------------|---------------|-----------|-----------------------|
| 生成成功                | **ACK**       | —         | 正常完成                  |
| version 不兼容         | **NACK**      | **false** | 协议版本不支持，重试无意义，直接入 DLQ |
| JSON 解析失败           | **NACK**      | **false** | 消息格式错误，重试无意义，直接入 DLQ  |
| 必填字段缺失              | **NACK**      | **false** | 缺少关键字段，重试无意义，直接入 DLQ  |
| docType 不在枚举中       | **NACK**      | **false** | 不支持的类型，重试无意义，直接入 DLQ  |
| LLM 调用临时失败 (5xx/超时) | **NACK**      | **true**  | 外部服务临时故障，重新投递         |
| 额度不足                | **ACK** 后回调失败 | —         | 不重试，通过回调告知 Java       |
| 文件生成异常              | **NACK**      | **true**  | 临时 I/O 错误，最多重试 3 次    |
| 文件上传到 Java 失败       | **NACK**      | **true**  | 网络临时故障，最多重试 3 次       |

> **重要**：Python 侧需实现重试计数。用消息 header `x-retry-count` 记录重试次数，达到 3 次后 NACK 且不 requeue，直接入 DLQ。

---

## 四、回调规范（Python → Java HTTP）

生成完成后，Python 通过 **RSA-SHA256 签名 HTTP** 调用 Java 内部接口回传结果。签名机制与现有 `JAVA_CALLER.md` 一致。

### 4.1 任务完成回调

**请求**

```
POST /api/internal/task/callback
Content-Type: application/json
X-Timestamp: 1716451230456
X-Nonce: uuid-random
X-Signature: Base64(RSA-SHA256(METHOD\nPATH\nBODY\nTIMESTAMP\nNONCE))
```

**请求体**

```json
{
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "callbackId": "req_20260523_001",
  "userId": 42,
  "projectId": 100,
  "status": "completed",
  "fileId": 999,
  "fileUrl": "https://cdn.example.com/files/report.pptx",
  "fileName": "人工智能技术综述.pptx",
  "qaLowestScore": 72,
  "qaPassedCount": 14,
  "qaTotalCount": 15,
  "generationTimeMs": 45230,
  "errorCode": 0,
  "errorMessage": ""
}
```

**响应**

```json
{
  "code": 0,
  "message": "ok",
  "data": null
}
```

### 4.2 任务失败回调

```json
{
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "callbackId": "req_20260523_001",
  "userId": 42,
  "projectId": 100,
  "status": "failed",
  "fileId": null,
  "fileUrl": null,
  "fileName": null,
  "qaLowestScore": null,
  "qaPassedCount": null,
  "qaTotalCount": null,
  "generationTimeMs": 12500,
  "errorCode": 5002,
  "errorMessage": "大纲验证失败：缺少主标题字段"
}
```

### 4.3 回调字段定义

| 字段                 | 类型           | 必填    | 说明                                              |
|--------------------|--------------|-------|-------------------------------------------------|
| `taskId`           | string       | **是** | 与消息体中的 taskId 完全一致                              |
| `callbackId`       | string       | **是** | 与消息体中的 callbackId 完全一致                          |
| `userId`           | long         | **是** | 用户 ID                                           |
| `projectId`        | long         | **是** | 项目 ID                                           |
| `status`           | string       | **是** | `"completed"` \| `"failed"`                     |
| `fileId`           | long\|null   | 否     | 生成成功时的文件 ID（来自 `/api/internal/file/upload` 返回值） |
| `fileUrl`          | string\|null | 否     | 生成成功时的文件访问 URL                                  |
| `fileName`         | string\|null | 否     | 生成的文件名（含扩展名）                                    |
| `qaLowestScore`    | number\|null | 否     | QA 最低评分（0-100），仅 PPT 返回；Word/PDF 返回整体评分         |
| `qaPassedCount`    | number\|null | 否     | QA 通过的页数/章节数                                    |
| `qaTotalCount`     | number\|null | 否     | QA 总评估页数/章节数                                    |
| `generationTimeMs` | number       | **是** | 实际生成耗时（毫秒），从消费消息到文件上传完成                         |
| `errorCode`        | number       | **是** | 错误码，成功为 `0`（详见第五节）                              |
| `errorMessage`     | string       | **是** | 错误描述，成功为空字符串 `""`                               |

### 4.4 任务进度通知（可选）

生成过程中，Python 可周期性推送进度。**非必须实现**，但建议支持以改善用户体验。

```
POST /api/internal/task/progress
Content-Type: application/json
```

```json
{
  "taskId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "callbackId": "req_20260523_001",
  "status": "processing",
  "stage": "running_qa",
  "progress": 65,
  "message": "正在质量评审：第 10/15 页"
}
```

| 字段           | 类型     | 必填    | 说明                                                                                                                                                                                                 |
|--------------|--------|-------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `taskId`     | string | **是** | 任务 ID                                                                                                                                                                                              |
| `callbackId` | string | **是** | 业务流水 ID                                                                                                                                                                                            |
| `status`     | string | **是** | 固定 `"processing"`                                                                                                                                                                                  |
| `stage`      | string | **是** | 当前阶段，枚举：`"retrieving_context"` \| `"generating_outline"` \| `"validating_outline"` \| `"rendering_charts"` \| `"fetching_images"` \| `"running_qa"` \| `"building_document"` \| `"uploading_file"` |
| `progress`   | number | **是** | 进度百分比，0-100 整数                                                                                                                                                                                     |
| `message`    | string | 否     | 可读状态描述                                                                                                                                                                                             |

---

## 五、错误码

### 5.1 错误码分段

| 范围     | 类别            |
|--------|---------------|
| `0`    | 成功            |
| `1xxx` | 客户端/消息错误（不重试） |
| `2xxx` | 额度/权限错误（不重试）  |
| `5xxx` | 服务端/生成错误      |
| `6xxx` | 外部依赖错误（可重试）   |

### 5.2 具体错误码

| 错误码    | 枚举名                         | 说明                          | 是否重试          |
|--------|-----------------------------|-----------------------------|---------------|
| `0`    | `SUCCESS`                   | 成功                          | —             |
| `1001` | `INVALID_MESSAGE`           | 消息格式错误（JSON 解析失败）           | 否             |
| `1002` | `MISSING_REQUIRED_FIELD`    | 必填字段缺失                      | 否             |
| `1003` | `UNSUPPORTED_VERSION`       | 不支持的协议版本                    | 否             |
| `1004` | `UNSUPPORTED_DOC_TYPE`      | 不支持的 docType                | 否             |
| `1005` | `INVALID_FIELD_VALUE`       | 字段值不合法（如 slideCount > 50）   | 否             |
| `2001` | `QUOTA_INSUFFICIENT`        | 用户额度不足                      | 否             |
| `2002` | `QUOTA_CONSUME_FAILED`      | 额度扣减接口调用失败                  | 否             |
| `5001` | `OUTLINE_GENERATION_FAILED` | 大纲生成失败（LLM 返回无效 JSON）       | 否             |
| `5002` | `OUTLINE_VALIDATION_FAILED` | 大纲验证失败（结构不满足要求）             | 否             |
| `5003` | `DOCUMENT_BUILD_FAILED`     | 文件构建失败（python-pptx/docx 异常） | 否             |
| `5004` | `PDF_CONVERSION_FAILED`     | PDF 转换失败（LibreOffice 异常）    | 否             |
| `5005` | `CHART_RENDER_FAILED`       | 图表渲染失败                      | 否             |
| `5006` | `QA_SCORE_TOO_LOW`          | QA 最终评分仍低于阈值                | 否             |
| `5007` | `FILE_UPLOAD_FAILED`        | 文件上传到 Java 后端失败             | **是**（最多 3 次） |
| `6001` | `LLM_SERVICE_ERROR`         | LLM 服务错误（5xx）               | **是**         |
| `6002` | `LLM_TIMEOUT`               | LLM 调用超时                    | **是**         |
| `6003` | `IMAGE_SEARCH_FAILED`       | 图片搜索失败（不影响主流程，降级为占位图）       | 否             |
| `6004` | `RAG_RETRIEVAL_FAILED`      | RAG 检索失败（降级为空 context）      | 否             |
| `9999` | `UNKNOWN_ERROR`             | 未知错误                        | **是**（最多 3 次） |

---

## 六、Java 端需实现的接口

### 6.1 新增接口

| 方法   | 路径                            | Content-Type       | 说明           |
|------|-------------------------------|--------------------|--------------|
| POST | `/api/internal/task/callback` | `application/json` | 接收任务完成/失败回调  |
| POST | `/api/internal/task/progress` | `application/json` | 接收任务进度更新（可选） |

### 6.2 已有接口（继续使用）

| 方法   | 路径                            | 说明               |
|------|-------------------------------|------------------|
| POST | `/api/internal/quota/consume` | Python 消费消息后扣减额度 |
| POST | `/api/internal/quota/refund`  | 生成失败时退还额度        |
| POST | `/api/internal/file/upload`   | Python 上传生成的文件   |

### 6.3 鉴权

以上所有接口均需 RSA-SHA256 签名验证，与现有 `JAVA_CALLER.md` 一致。Python 侧已有完整的签名 HTTP 客户端实现（
`client/http.py`）。

---

## 七、完整时序图

```
用户        Java后端           RabbitMQ            Python AI模块      LLM/外部服务
 │             │                  │                     │                  │
 ├─POST /doc──▶│                  │                     │                  │
 │   generate  │                  │                     │                  │
 │             ├─生成 taskId──────▶│                     │                  │
 │             │  publish message  │                     │                  │
 │             │                  │                     │                  │
 │◀─200 {taskId, status:pending}─┤                     │                  │
 │             │                  │                     │                  │
 │             │                  ├────consume─────────▶│                  │
 │             │                  │                     │                  │
 │             │                  │◁───ACK (delivery)───┤                  │
 │             │                  │                     │                  │
 │             │                  │                     ├─扣减额度─────────▶│ (Java)
 │             │                  │                     │◀─code:0──────────┤
 │             │                  │                     │                  │
 │  (可选)     │◀──POST /task/progress───processing─────┤                  │
 │             │                  │                     │                  │
 │             │                  │                     ├─RAG检索──────────▶│ (Redis)
 │             │                  │                     ├─大纲生成──────────▶│ (LLM)
 │             │                  │                     ├─QA评分(多轮)──────▶│ (LLM)
 │             │                  │                     ├─配图搜索──────────▶│ (Unsplash)
 │             │                  │                     ├─文件构建──────────┤
 │             │                  │                     │                  │
 │  (可选)     │◀──POST /task/progress───building───────┤                  │
 │             │                  │                     │                  │
 │             │◀──POST /task/callback───completed──────┤                  │
 │             │   (含 fileId, fileUrl)                 │                  │
 │             │                  │                     │                  │
 │◀─WebSocket/poll─task completed─┤                     │                  │
 │   {fileUrl} │                  │                     │                  │
```

---

## 八、Java 端消息发送规范

### 8.1 连接配置参数

Java 端需与 Python 端使用相同的连接参数：

| 参数                 | 值                               | 说明             |
|--------------------|---------------------------------|----------------|
| Host               | 环境变量 `RABBITMQ_HOST`            | RabbitMQ 服务器地址 |
| Port               | 环境变量 `RABBITMQ_PORT` 或默认 `5672` | —              |
| Virtual Host       | 环境变量 `RABBITMQ_VHOST` 或默认 `/`   | —              |
| Username           | 环境变量 `RABBITMQ_USER`            | —              |
| Password           | 环境变量 `RABBITMQ_PASSWORD`        | —              |
| Connection Timeout | `5000ms`                        | —              |
| Automatic Recovery | `true`                          | 网络恢复后自动重连      |

### 8.2 发送要求

1. **持久化**：`deliveryMode = 2`（消息持久化到磁盘）
2. **消息 ID**：设置 `messageId` 为 `taskId`，便于去重和追踪
3. **优先级**：PPT 可设较高优先级（5-10），Word/PDF 默认（0-4）
4. **时间戳**：设置 `timestamp`（Java `Date`），与消息体中的 `timestamp` 一致
5. **发布确认**：必须开启 Publisher Confirms，确保消息已写入队列

### 8.3 发布确认失败处理

如果 RabbitMQ 返回 publish nack：

1. 立即返回用户"系统繁忙，请稍后重试"
2. 不落库补偿（避免双写复杂性），由用户自己重试
3. 记录 ERROR 日志含 taskId 和 nack 原因

---

## 九、Python 端消费规范

### 9.1 连接与 Channel

- 使用 `aio-pika`（async）连接 RabbitMQ
- 连接配置从 `config.py` 的环境变量读取（新增 RabbitMQ 相关配置项）
- QOS（prefetch_count）：默认 `1`，一次只消费一条消息（避免 QA 并行导致 LLM 限流）
- 需要连接断开重连机制

### 9.2 消费流程

```
1. 接收消息
2. 校验 version → 不支持则 NACK(requeue=false)
3. 校验 docType → 不支持则 NACK(requeue=false)
4. 校验必填字段（含 apiKey/baseUrl/modelName）→ 缺失则 NACK(requeue=false)
5. 从消息体读取 apiKey/baseUrl/modelName — 直接使用，无需额外请求
6. 调用 Java 扣减额度 → 失败则回调 Java (errorCode=2001) + ACK
7. 执行 LangGraph 生成流程（含 QA）
8. 上传文件到 Java → 失败则 NACK(requeue=true)
9. 回调 Java 任务完成 → ACK
```

### 9.3 新增配置项

```python
# .env 新增（开发环境实际值）
RABBITMQ_HOST=124.221.105.18
RABBITMQ_PORT=6673
RABBITMQ_VHOST=/
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=753951JcJ~
RABBITMQ_QUEUE=birdhelp.doc.generation.tasks
RABBITMQ_PREFETCH=1
```

> 生产环境请替换为生产 RabbitMQ 的地址和凭据。

---

## 十、环境变量对照表

| 变量名                 | Java 端 | Python 端 | 默认值                             | 说明                                   |
|---------------------|--------|----------|---------------------------------|--------------------------------------|
| `RABBITMQ_HOST`     | ✓      | ✓        | `124.221.105.18`                | RabbitMQ 服务器地址                       |
| `RABBITMQ_PORT`     | ✓      | ✓        | `6673`                          | RabbitMQ 端口                          |
| `RABBITMQ_VHOST`    | ✓      | ✓        | `/`                             | 虚拟主机                                 |
| `RABBITMQ_USER`     | ✓      | ✓        | `admin`                         | 用户名                                  |
| `RABBITMQ_PASSWORD` | ✓      | ✓        | `753951JcJ~`                    | 密码                                   |
| `RABBITMQ_EXCHANGE` | ✓      | ✓        | `birdhelp.doc.generation`       | 交换机名称                                |
| `RABBITMQ_QUEUE`    | —      | ✓        | `birdhelp.doc.generation.tasks` | 消费队列名（Java 不需要直接知道队列名，只需发到 exchange） |
| `RABBITMQ_PREFETCH` | —      | ✓        | `1`                             | 消费者 prefetch 数量                      |

---

## 十一、不兼容变更规则

1. 协议版本号 `version` 字段是唯一的兼容性判断依据
2. 新增**选填**字段 → `version` 不变（如 `"1.0"` → 仍为 `"1.0"`），旧消费者忽略新字段
3. 新增**必填**字段 → 升级到新 version（如 `"1.0"` → `"1.1"`），不支持新版本的消费者 NACK 入 DLQ
4. 修改已有字段类型 → 升级主版本号（如 `"1.0"` → `"2.0"`）

---

## 十二、开发检查清单

### Java 端（已完成 2026-05-23）

- [x] 配置 RabbitMQ ConnectionFactory（host/port/vhost/user/password）
- [x] 声明 Exchange：`birdhelp.doc.generation`（topic, durable）
- [x] 声明 Queue：`birdhelp.doc.generation.tasks`（含死信参数）
- [x] 声明 DLX / DLQ
- [x] 绑定 routing key
- [x] 实现消息发布（开启 Publisher Confirms）
- [x] 实现 `POST /api/internal/task/callback` 接口（含签名验证）
- [x] 实现 `POST /api/internal/task/progress` 接口（可选，含签名验证）
- [x] 发送消息时校验必填字段齐全
- [x] taskId 生成为 UUID v4（36 字符标准格式）
- [x] 实现 `GET /task/{taskId}` 前端轮询接口
- [x] 移除旧的同步 HTTP 生成代理（AiModuleCaller.generateXxx / 3 个 VO）

### Python 端

- [ ] 在 `config.py` 新增 RabbitMQ 配置项
- [ ] 在 `.env` 新增 RabbitMQ 环境变量（见 9.3 节）
- [ ] 实现 `aio-pika` 消费者启动逻辑
- [ ] 实现消息校验（version / docType / 必填字段）
- [ ] 实现消费流程（额度扣减 → 生成 → 上传 → 回调）
- [ ] 实现重试计数（x-retry-count header）
- [ ] 实现进度推送（可选，推送到 `/api/internal/task/progress`）
- [ ] 连接断开自动重连
- [ ] 消费完成后 ACK，不可重试错误 NACK(requeue=false)，可重试错误 NACK(requeue=true)
- [ ] 移除旧的 `/ai/ppt/generate`、`/ai/word/generate`、`/ai/pdf/generate` 同步接口（Java 已不再调用）
- [ ] 调用新的 `/api/internal/task/callback` 替代旧的返回文件信息方式（含 RSA 签名，与现有 `client/http.py` 一致）
- [ ] 调用 `/api/internal/task/progress` 推送进度（RSA 签名，格式见 4.4 节）
