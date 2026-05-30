# BirdHelp AI 模块接口调用指南

> 本文档面向 **Java 后端开发人员**，说明如何对 BirdHelp Python AI 模块接口发起签名请求。Java 后端作为调用方，通过代理转发前端请求到
> AI 模块。

---

## 一、签名机制概述

AI 模块的 `/ai/**` 接口由 Java 后端代理转发给前端，Java 后端在转发前需要对请求进行 **RSA-SHA256 加签**，AI 模块验签通过后才处理。

- **算法**：SHA256withRSA（RSA 密钥长度 2048 位）
- **私钥用途**：Java 后端持有，对请求签名
- **公钥用途**：AI 模块持有，验证签名（配置项 `JAVA_CALLER_PUBLIC_KEY_B64`）
- **时间窗口**：默认 300 秒（5 分钟），超出窗口的请求会被拒绝

> **注意**：此密钥对与 AI 模块调用 Java 内部接口（`/api/internal/**`）使用的密钥对是**独立的两对**，不可混用。

---

## 二、请求头

每个请求必须携带以下 Header：

| Header         | 说明                                 | 示例                                     |
|----------------|------------------------------------|----------------------------------------|
| `Content-Type` | 根据接口不同，见各接口说明                      | `application/json`                     |
| `X-Timestamp`  | Unix 时间戳（**毫秒**），与服务器时间偏差不能超过 5 分钟 | `1746889200000`                        |
| `X-Nonce`      | 随机字符串，每次请求不同，建议 UUID               | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `X-Signature`  | Base64 编码的 RSA 签名（详见第三节）           | `MmBxQJvP...`                          |

---

## 三、签名字符串构造

### 3.1 拼接规则

将以下 5 个部分用换行符 `\n` 拼接为一个字符串：

```
{METHOD}\n{PATH}\n{BODY}\n{TIMESTAMP}\n{NONCE}
```

| 占位符         | 说明                                 | 示例                                     |
|-------------|------------------------------------|----------------------------------------|
| `METHOD`    | HTTP 方法，大写                         | `POST`                                 |
| `PATH`      | 请求路径（含 `/ai` 前缀及 query string）     | `/ai/material/upload`                  |
| `BODY`      | 请求体原样字符串（JSON 或 multipart 完整 body） | `{"userId":1,"projectId":5}`           |
| `TIMESTAMP` | 同 `X-Timestamp` 的值                 | `1746889200000`                        |
| `NONCE`     | 同 `X-Nonce` 的值                     | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |

### 3.2 示例

假设请求参数如下：

```
METHOD    = DELETE
PATH      = /ai/material/42?userId=1&projectId=5
BODY      =
TIMESTAMP = 1746889200000
NONCE     = a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

拼接后的待签名字符串：

```
DELETE
/ai/material/42?userId=1&projectId=5

1746889200000
a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**重要**：`\n` 表示换行符（ASCII 10），不是字面量字符串 `\n`。BODY 为空字符串时占一行。

---

## 四、签名生成（Java 调用方）

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;

/**
 * AI 模块调用客户端 — 对 /ai/** 接口发起带签名的 HTTP 请求。
 */
public class AiModuleCaller {

    /** Java 后端持有此私钥，用于对发往 AI 模块的请求签名（PKCS#8 DER Base64） */
    private static final String CALL_AI_PRIVATE_KEY_B64 = "MIIEvQIBADANBgkqhkiG9w0BAQE...";  // 见第七节

    private static final String AI_MODULE_BASE_URL = "http://localhost:8000";

    private static PrivateKey loadPrivateKey(String b64Key) throws Exception {
        byte[] keyBytes = Base64.getDecoder().decode(b64Key);
        PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(keyBytes);
        return KeyFactory.getInstance("RSA").generatePrivate(spec);
    }

    private static String sign(String method, String path, String body,
                               String timestamp, String nonce) throws Exception {
        PrivateKey privateKey = loadPrivateKey(CALL_AI_PRIVATE_KEY_B64);
        String signString = method + "\n" + path + "\n" + body + "\n" + timestamp + "\n" + nonce;

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(signString.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signature.sign());
    }

    // ── JSON 请求 ──

    public static HttpResponse<String> signedJsonRequest(
            String method, String path, String jsonBody) throws Exception {

        String timestamp = String.valueOf(Instant.now().toEpochMilli());
        String nonce = UUID.randomUUID().toString();
        String signature = sign(method, path, jsonBody, timestamp, nonce);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(AI_MODULE_BASE_URL + path))
                .header("Content-Type", "application/json")
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .method(method, HttpRequest.BodyPublishers.ofString(jsonBody))
                .build();

        return HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());
    }

    // ── 无 Body 请求（GET / POST / DELETE） ──

    public static HttpResponse<String> signedNoBodyRequest(
            String method, String path) throws Exception {

        String timestamp = String.valueOf(Instant.now().toEpochMilli());
        String nonce = UUID.randomUUID().toString();
        String signature = sign(method, path, "", timestamp, nonce);

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(AI_MODULE_BASE_URL + path))
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature);

        HttpRequest request = switch (method) {
            case "DELETE" -> builder.DELETE().build();
            case "POST"   -> builder.POST(HttpRequest.BodyPublishers.noBody()).build();
            default       -> builder.GET().build();
        };

        return HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());
    }

    // ── Multipart 文件上传 ──

    /**
     * @param fields          普通表单字段 (key → value)
     * @param fileFieldName   文件字段名，固定为 "file"
     * @param fileName        原始文件名（含扩展名）
     * @param fileContent     文件二进制内容
     * @param fileContentType 文件 MIME 类型，如 "application/octet-stream"
     */
    public static HttpResponse<String> signedMultipartRequest(
            String path, Map<String, String> fields,
            String fileFieldName, String fileName, byte[] fileContent,
            String fileContentType) throws Exception {

        // 先构建完整的 multipart 请求体，再对其签名
        String boundary = UUID.randomUUID().toString().replace("-", "");
        java.io.ByteArrayOutputStream bodyOs = new java.io.ByteArrayOutputStream();

        for (var entry : fields.entrySet()) {
            bodyOs.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
            bodyOs.write(("Content-Disposition: form-data; name=\"" + entry.getKey() + "\"\r\n\r\n")
                    .getBytes(StandardCharsets.UTF_8));
            bodyOs.write(entry.getValue().getBytes(StandardCharsets.UTF_8));
            bodyOs.write("\r\n".getBytes(StandardCharsets.UTF_8));
        }

        bodyOs.write(("--" + boundary + "\r\n").getBytes(StandardCharsets.UTF_8));
        bodyOs.write(("Content-Disposition: form-data; name=\"" + fileFieldName
                + "\"; filename=\"" + fileName + "\"\r\n").getBytes(StandardCharsets.UTF_8));
        bodyOs.write(("Content-Type: " + fileContentType + "\r\n\r\n")
                .getBytes(StandardCharsets.UTF_8));
        bodyOs.write(fileContent);
        bodyOs.write("\r\n".getBytes(StandardCharsets.UTF_8));
        bodyOs.write(("--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
        byte[] bodyBytes = bodyOs.toByteArray();

        // 基于完整 multipart body 签名
        String timestamp = String.valueOf(Instant.now().toEpochMilli());
        String nonce = UUID.randomUUID().toString();
        String bodyStr = new String(bodyBytes, StandardCharsets.UTF_8);
        String signature = sign("POST", path, bodyStr, timestamp, nonce);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(AI_MODULE_BASE_URL + path))
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofByteArray(bodyBytes))
                .build();

        return HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());
    }
}
```

---

## 五、当前可用接口

> **重要**：文档生成接口（PPT/Word/PDF）已从同步 HTTP 迁移到 RabbitMQ 异步消息。
> 生产环境 Java 后端应发送消息到 RabbitMQ Exchange `birdhelp.doc.generation`，
> 而非调用 `/ai/ppt/generate` 等接口。完整协议见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`。

### 5.1 接口总览

| 方法     | 路径                               | Content-Type          | 说明                    |
|--------|----------------------------------|-----------------------|-----------------------|
| POST   | `/ai/material/upload`            | `multipart/form-data` | 上传参考素材并触发 RAG 摄取      |
| DELETE | `/ai/material/{id}`              | —                     | 删除素材（Java 软删除 + 向量清理） |
| POST   | `/ai/material/{id}/reindex`      | —                     | 回收站恢复后重建向量索引          |
| POST   | `/ai/material/{id}/vector-purge` | —                     | 强制删除后清理残留向量           |
| POST   | `/ai/chat/modify`                | `application/json`    | 对话修改文档（v5.2 新增）       |
| POST   | `/ai/chat/discuss`               | `application/json`    | 仅讨论/问答（v5.2 新增）       |

### 5.2 统一响应格式

所有接口返回统一的 JSON 响应体：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

| code   | 含义               |
|--------|------------------|
| `0`    | 成功               |
| `1xxx` | 参数 / 业务错误        |
| `2xxx` | LLM / 嵌入模型错误     |
| `3xxx` | 文件生成 / 上传错误      |
| `5xxx` | 内部未知错误（HTTP 500） |

### 5.3 POST /ai/material/upload — 上传素材并触发 RAG 摄取

> Multipart 请求。签名时 BODY 为完整的 multipart 编码请求体，**不是**仅字段的 JSON。
>
> **调用流程**：Java 端先自行完成文件上传至存储（拿到 `javaFileId`），再调用本接口将已下载的文件传递给 AI 模块进行 RAG 摄取。

| 字段           | 类型   | 必填 | 说明                           |
|--------------|------|----|------------------------------|
| `file`       | file | 是  | 已从 Java 存储下载的文件              |
| `userId`     | long | 是  | 用户 ID                        |
| `projectId`  | long | 是  | 项目 ID，用于隔离知识库                |
| `javaFileId` | long | 是  | Java 端文件存储后返回的文件 ID，用于向量索引关联 |

```java
byte[] fileContent = Files.readAllBytes(Path.of("material.pdf"));
var fields = Map.of("userId", "1", "projectId", "5", "javaFileId", "42");
HttpResponse<String> resp = AiModuleCaller.signedMultipartRequest(
    "/ai/material/upload", fields,
    "file", "material.pdf", fileContent, "application/octet-stream"
);
```

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "file_id": 42,
    "chunk_count": 35,
    "file_name": "material.pdf"
  }
}
```

格式不支持：

```json
{"code": 1003, "message": "不支持的格式: .xlsx，支持: .pdf, .docx, .pptx, .txt", "data": null}
```

支持的扩展名：`.pdf` `.docx` `.pptx` `.txt`

### 5.4 DELETE /ai/material/{id} — 删除素材

> 无 Body，签名字符串中 BODY = `""`。

| 参数          | 位置    | 类型     | 必填 | 说明              |
|-------------|-------|--------|----|-----------------|
| `id`        | path  | long   | 是  | 素材 ID           |
| `userId`    | query | long   | 是  | 用户 ID           |
| `projectId` | query | string | 是  | 项目 ID，用于定位对应知识库 |

```java
HttpResponse<String> resp = AiModuleCaller.signedNoBodyRequest(
    "DELETE", "/ai/material/42?userId=1&projectId=5"
);
```

成功响应：

```json
{"code": 0, "message": "success", "data": {"deleted_chunks": 35}}
```

### 5.5 POST /ai/material/{id}/reindex — 回收站恢复后重建向量索引

> 无 Body，签名字符串中 BODY = `""`。

Java 端在用户从回收站恢复文件后调用，AI 模块从 Java 重新下载文件，解析、切分、嵌入、入库。

| 参数          | 位置    | 类型     | 必填 | 说明                           |
|-------------|-------|--------|----|------------------------------|
| `id`        | path  | long   | 是  | 素材 / 文件 ID                   |
| `userId`    | query | long   | 是  | 用户 ID                        |
| `projectId` | query | string | 是  | 项目 ID                        |
| `fileName`  | query | string | 是  | 原始文件名（含扩展名），如 `material.pdf` |

```java
HttpResponse<String> resp = AiModuleCaller.signedNoBodyRequest(
    "POST", "/ai/material/42/reindex?userId=1&projectId=5&fileName=material.pdf"
);
```

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "file_id": 42,
    "chunk_count": 35,
    "file_name": "material.pdf"
  }
}
```

解析失败：

```json
{"code": 3003, "message": "素材摄取失败", "data": null}
```

### 5.6 POST /ai/material/{id}/vector-purge — 强制删除后清理残留向量

> 无 Body，签名字符串中 BODY = `""`。

Java 端在以下场景调用：
- 用户在回收站点击"永久删除"
- 回收站超时 30 天自动清理
- Java 侧直接删除文件记录

| 参数          | 位置    | 类型     | 必填 | 说明         |
|-------------|-------|--------|----|------------|
| `id`        | path  | long   | 是  | 素材 / 文件 ID |
| `userId`    | query | long   | 是  | 用户 ID      |
| `projectId` | query | string | 是  | 项目 ID      |

```java
HttpResponse<String> resp = AiModuleCaller.signedNoBodyRequest(
    "POST", "/ai/material/42/vector-purge?userId=1&projectId=5"
);
```

成功响应：

```json
{"code": 0, "message": "success", "data": {"deleted_chunks": 35}}
```

### 5.7 文档生成（PPT / Word / PDF）— ❌ 已移除

文档生成接口已从 HTTP 同步模式完全迁移到 RabbitMQ 异步模式。

- 原 `POST /ai/ppt/generate` → 现通过 RabbitMQ Exchange `birdhelp.doc.generation`，routing key `doc.generate.ppt`
- 原 `POST /ai/word/generate` → routing key `doc.generate.word`
- 原 `POST /ai/pdf/generate` → routing key `doc.generate.pdf`

Java 后端需：

1. 将生成任务作为 JSON 消息发布到 RabbitMQ
2. 实现 `POST /api/internal/task/callback` 接收 Python 的完成/失败回调

> 完整协议规范见 `doc/RABBITMQ_ASYNC_PROTOCOL.md`

### 5.8 POST /ai/chat/modify — 对话修改文档（v5.2 新增）

通过 LLM 修改文档大纲并重建文件。流程：获取大纲 → LLM 修改 → 校验 → 重建 → 上传 → 同步会话。

**请求**：`POST /ai/chat/modify`
```json
{
    "userId": "1",
    "projectId": "1",
    "sessionId": "uuid-v4",
    "fileId": "100",
    "docType": "ppt",
    "message": "把第二页标题改得激进一些",
    "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
    "regenerateFile": true,
    "callbackId": "cb-xxx"
}
```

**响应**：
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "sessionId": "uuid-v4",
        "reply": "已根据您的指令修改文档大纲（3 处变更）。",
        "outline": {"slides": [...]},
        "changes": [{"page_number": 2, "action": "modified", "summary": "标题已修改"}],
        "fileId": "101",
        "fileUrl": "https://...",
        "success": true
    }
}
```

### 5.9 POST /ai/chat/discuss — 仅讨论/问答（v5.2 新增）

仅 LLM 文本回复，不重建文件（`regenerateFile=false`）。

**请求**：`POST /ai/chat/discuss`，参数同 `/modify` 但无需 `regenerateFile` 字段。

**响应**：与 `/modify` 类似，但 `fileId` 和 `fileUrl` 均为 `null`。

---

## 六、验签失败排查

| 错误信息             | 原因             | 解决                                         |
|------------------|----------------|--------------------------------------------|
| 缺少签名请求头          | Header 缺失      | 确保传了 `X-Timestamp`、`X-Nonce`、`X-Signature` |
| X-Timestamp 格式无效 | 时间戳不是纯数字       | 传毫秒级 Unix 时间戳字符串                           |
| 请求已过期或时间偏差过大     | 时间戳超出 300 秒窗口  | 检查调用方机器时间是否同步，或签名后是否过太久才发出请求               |
| 签名不匹配            | 签名字符串构造有误或密钥不对 | 逐段比对 METHOD/PATH/BODY/TIMESTAMP/NONCE      |

常见坑：

- `PATH` 没有带 `/ai` 前缀（AI 模块实际监听 `/ai/...`）
- 时间戳用了**秒**而不是毫秒
- 签名字符串中的 `\n` 写成了字面量字符串 `\n` 而非真正的换行符（ASCII 10）
- **DELETE 请求**：BODY 为空字符串 `""`（占一行），不是 `null` 或 `"{}"`
- **路径含 query string**：签名 PATH 必须包含完整 query string（如 `/ai/material/42?userId=1&projectId=5`）
- **multipart 请求**：必须先构建完整的 multipart 请求体，再对完整 body 签名。不要只对 form 字段的 JSON 签名

---

## 七、密钥信息

| 密钥 | 持有方          | 格式                   | AI 模块配置项                     |
|----|--------------|----------------------|------------------------------|
| 私钥 | Java 后端（调用方） | PKCS#8 DER，Base64 编码 | —                            |
| 公钥 | AI 模块（验签方）   | X.509 DER，Base64 编码  | `JAVA_CALLER_PUBLIC_KEY_B64` |

> **两对密钥的角色对照：**
>
> | 通信方向 | 私钥持有方 | 公钥持有方 |
> |----------|----------|----------|
> | AI → Java (`/api/internal/**`) | AI 模块 | Java 后端 |
> | Java → AI (`/ai/**`) | Java 后端 | AI 模块 |
>
> 生产环境请为两个方向分别生成独立的密钥对，当前开发环境可共用一对。

> 生成命令：
> ```bash
> # 生成私钥（Java 调用方持有）
> openssl genpkey -algorithm RSA -out java_caller_private.pem -pkeyopt rsa_keygen_bits:2048
> # 导出公钥（AI 模块持有）
> openssl rsa -pubout -in java_caller_private.pem -out java_caller_public.pem
> # 转为 Base64
> openssl pkcs8 -topk8 -nocrypt -in java_caller_private.pem -outform DER | base64 -w0  # 私钥（Java 端）
> openssl rsa -pubin -in java_caller_public.pem -outform DER | base64 -w0              # 公钥（AI 模块 .env）
> ```

---

## 八、AI 模块验签实现

AI 模块侧通过 FastAPI 依赖项 `require_java_caller` 验签，已挂载到 `api/router.py` 的 `api_router` 上，所有 `/ai/*`
路由自动受保护。

核心实现位于 `core/auth.py`：

```python
"""Java 后端调用方签名验证 — FastAPI 依赖项。

签名字符串格式: {METHOD}\n{PATH}\n{BODY}\n{TIMESTAMP}\n{NONCE}
"""

import base64
import time

from fastapi import Request, HTTPException
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.exceptions import InvalidSignature

from config import settings

_public_key = None


def _load_public_key():
    global _public_key
    if _public_key is None:
        key_bytes = base64.b64decode(settings.java_caller_public_key_b64)
        _public_key = serialization.load_der_public_key(key_bytes)
    return _public_key


def _verify_signature(method: str, path: str, body: str,
                      timestamp: str, nonce: str, signature_b64: str) -> bool:
    sign_string = f"{method}\n{path}\n{body}\n{timestamp}\n{nonce}"
    try:
        signature = base64.b64decode(signature_b64)
        _load_public_key().verify(
            signature,
            sign_string.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False


async def require_java_caller(request: Request):
    # 1. 提取签名头
    timestamp = request.headers.get("X-Timestamp", "")
    nonce = request.headers.get("X-Nonce", "")
    signature_b64 = request.headers.get("X-Signature", "")

    if not timestamp or not nonce or not signature_b64:
        raise HTTPException(status_code=401,
            detail={"code": 401, "message": "缺少签名请求头", "data": None})

    # 2. 校验时间戳格式与时效
    try:
        ts_ms = int(timestamp)
    except ValueError:
        raise HTTPException(status_code=401,
            detail={"code": 401, "message": "X-Timestamp 格式无效", "data": None})

    drift_ms = abs(int(time.time() * 1000) - ts_ms)
    if drift_ms > settings.java_sign_timeout_seconds * 1000:
        raise HTTPException(status_code=401,
            detail={"code": 401, "message": "请求已过期或时间偏差过大", "data": None})

    # 3. 读取请求体（Starlette 自动缓存到 _body，下游可重复读取）
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace")

    # 4. 构造签名路径（含 query string）
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    # 5. 验签
    if not _verify_signature(request.method, path, body_str, timestamp, nonce, signature_b64):
        raise HTTPException(status_code=401,
            detail={"code": 401, "message": "签名不匹配", "data": None})
```

路由挂载方式（`api/router.py`）：

```python
from fastapi import APIRouter, Depends
from core.auth import require_java_caller

api_router = APIRouter(dependencies=[Depends(require_java_caller)])
api_router.include_router(material_router)
# 后续新增路由 include 进来即可自动受保护
```

配置项（`.env`）：

```bash
# Java 后端调用 AI 模块时使用的公钥（X.509 DER Base64）
JAVA_CALLER_PUBLIC_KEY_B64=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...
```

---

## 九、健康检查

Java 后端在启动或负载均衡时可探测 AI 模块存活状态（无需签名）：

```
GET /
```

响应：

```json
{"status": "ok", "app": "BirdHelp"}
```
