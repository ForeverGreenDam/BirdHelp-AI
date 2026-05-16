# Java ↔ Python AI 模块交互问题复盘

> 2026-05-16 | 记录从初次联调到全链路通的所有问题及解决方案

---

## 问题总览

| # | 现象 | 根因 | 影响面 |
|---|------|------|--------|
| 1 | `RuntimeError: Stream consumed` | 请求体被多次读取，ASGI 流无法复用 | 全部 `/ai/*` 接口 |
| 2 | `401 签名不匹配`（第一阶段） | `BaseHTTPMiddleware` 导致 `_CachedRequest` 包装，body 缓存断裂 | multipart 上传 |
| 3 | `401 签名不匹配`（第二阶段） | body 经 UTF-8 编解码往返后内容不一致（binary 文件） | multipart 上传 |
| 4 | `422 Field required` | Form 字段名 Java 用 camelCase，Python 用 snake_case | `/ai/material/upload` |
| 5 | `Errno 13 Permission denied` | Docker 宿主机 bind mount 权限与容器内用户 UID 不匹配 | `/tmp/birdhelp` 写入 |

---

## 问题 1：Stream consumed

### 现象

Java 调用任何 `/ai/*` POST 接口均报 500，日志：

```
RuntimeError: Stream consumed
```

### 调用链

```
Java → POST /ai/material/upload (multipart) / POST /ai/ppt/generate (JSON)
  → require_java_caller (Depends) → await request.body() → 验签
  → FastAPI 解析 body (Pydantic / Form)
```

### 根因

`require_java_caller` 为了验签调用 `await request.body()` 读取请求体，之后 FastAPI 解析 Pydantic 模型 / multipart 表单时需要再次读取。Starlette 的 `request.body()` 虽然会缓存到 `_body`，但：

1. **JSON 接口**：router 依赖先于 Pydantic body 解析执行，`body()` 成功缓存 → 下游 `json()` 从缓存读 ✅
2. **Multipart 接口**：FastAPI 的 `request.form()` 在依赖项之前消费了 `stream()`，导致 `body()` 抛出 `Stream consumed`

### 解决

**最终方案：ASGI 原始中间件 `BodyCacheMiddleware`**

在 ASGI 层（FastAPI 之前）完整收集 body，存入 `scope["_cached_body"]`，再分 64KB 块回放给下游。验签从 scope 缓存读取，multipart 解析从回放流读取。

```python
# main.py — 核心逻辑
class BodyCacheMiddleware:
    async def __call__(self, scope, receive, send):
        # 1. 收集完整 body
        while more_body:
            message = await receive()
            body_chunks.append(message.get("body", b""))
        cached_body = b"".join(body_chunks)

        # 2. 存入 scope，供验签使用
        scope["_cached_body"] = cached_body

        # 3. 分块回放，供 multipart 解析使用
        async def replay_receive():
            # 每次返回一个 64KB 分块，直到全部回放完毕
            ...

        await self.app(scope, replay_receive, send)
```

**关键决策记录：**

| 尝试过的方案 | 结果 | 失败原因 |
|-------------|------|----------|
| `@app.middleware("http")` 读 `request.body()` | ❌ | `BaseHTTPMiddleware` 创建 `_CachedRequest` 包装，body 缓存断裂 |
| 原始 ASGI 中间件，单 chunk 回放 | ❌ | `python_multipart` 解析器无法处理单一巨块 |
| 原始 ASGI 中间件，分 64KB chunk 回放 | ✅ | 模拟真实 ASGI 流，multipart 解析正常 |

---

## 问题 2：401 签名不匹配（body 编解码差异）

### 现象

验签通过中间件解决 stream 问题后，仍然 401：

```
Python: sign_string_len=815852 sha256=eda93e35...
Java:   sign_string_len=815569 sha256=d7b839a9...
```

两边的 `sign_string` 相差 **283 字节**。

### 根因

签名前需要构造 `sign_string = METHOD\nPATH\nBODY\nTIMESTAMP\nNONCE`。

Java 端：
```java
byte[] bodyBytes = bodyOs.toByteArray();          // 原始 multipart 字节
String bodyStr = new String(bodyBytes, UTF_8);    // UTF-8 → String（binary 字节被替换）
String signString = method + "\n" + path + "\n" + bodyStr + ...;
signature.update(signString.getBytes(UTF_8));     // String → UTF-8（再次编码）
```

Python 端：
```python
body_bytes = scope["_cached_body"]                # 原始 multipart 字节
body_str = body_bytes.decode("utf-8", "replace")  # UTF-8 → str（binary 字节被替换）
sign_string = f"{method}\n{path}\n{body_str}\n..."
sign_bytes = sign_string.encode("utf-8")          # str → UTF-8（再次编码）
```

问题出在 **UTF-8 往返编解码**。multipart body 中包含 PDF 二进制内容，大量字节不是合法 UTF-8 序列。Java 和 Python 的 UTF-8 解码器对无效序列的替换策略有微小差异（同样是 `U+FFFD`，但不同序列的分组方式不同），导致编解码后的字节流不一致。

### 解决

**不要 decode 再 encode，直接用原始字节构造签名字节串：**

```python
# Python: 验签用原始字节
sign_bytes = (
    method.encode() + b"\n" +
    path.encode() + b"\n" +
    body_bytes + b"\n" +          # 直接拼接原始字节
    timestamp.encode() + b"\n" +
    nonce.encode()
)
_public_key.verify(signature, sign_bytes, ...)
```

```java
// Java: 签名也用原始字节
ByteArrayOutputStream buf = new ByteArrayOutputStream();
buf.write(method.getBytes(UTF_8));
buf.write('\n');
buf.write(path.getBytes(UTF_8));
buf.write('\n');
buf.write(bodyBytes);             // 直接拼接原始字节
buf.write('\n');
buf.write(timestamp.getBytes(UTF_8));
buf.write('\n');
buf.write(nonce.getBytes(UTF_8));
signature.update(buf.toByteArray());
```

**教训：涉及 binary 内容（文件上传）的签名，永远不要将字节流解码为字符串再编码回去。**

---

## 问题 3：422 Field required

### 现象

签名通过后，返回 422：

```json
{"detail": [
  {"loc": ["body","user_id"], "msg": "Field required"},
  {"loc": ["body","project_id"], "msg": "Field required"},
  {"loc": ["body","java_file_id"], "msg": "Field required"}
]}
```

### 根因

Java 端发送的 multipart 表单字段名是 camelCase：
```
userId, projectId, javaFileId
```

Python FastAPI 的 `Form(...)` 参数名是 snake_case：
```python
user_id: int = Form(...)
project_id: str = Form(...)
java_file_id: int = Form(...)
```

FastAPI 按参数名匹配 multipart 字段，名字不对就直接报 missing。

### 解决

给 `Form` 加 `alias` 参数：

```python
user_id: int = Form(..., alias="userId")
project_id: str = Form(..., alias="projectId")
java_file_id: int = Form(..., alias="javaFileId")
```

**教训：Java 和 Python 的命名风格差异需要在接口设计阶段就约定好，或者统一加 alias。**

---

## 问题 4：Permission denied

### 现象

```
PermissionError: [Errno 13] Permission denied: '/tmp/birdhelp/xxx.pdf'
```

### 根因

`docker-compose.yml` 把 `/tmp/birdhelp` 映射到宿主机目录 `/usr/birdhelp/ai`。容器内以 `birdhelp` 用户运行（UID 非 root），但宿主机目录属主是 root，容器用户无权写入。

### 解决

改用 Docker 命名卷（自动匹配容器内权限）：

```yaml
# docker-compose.yml
volumes:
  - birdhelp-tmp:/tmp/birdhelp    # 命名卷，不再用宿主目录
```

---

## 最终架构

```
Java 后端
  │
  │  POST /ai/* (带 X-Timestamp / X-Nonce / X-Signature)
  ▼
Uvicorn (ASGI)
  │
  ▼
BodyCacheMiddleware  ←── 收集 body → scope["_cached_body"] → 分块回放
  │
  ▼
FastAPI App
  │
  ├─ require_java_caller (router Depends)
  │    ├─ 读 scope["_cached_body"] (优先) 或 request.body()
  │    ├─ 拼接原始字节 sign_bytes
  │    └─ RSA-SHA256 验签
  │
  ├─ Form / JSON 解析
  │    ├─ multipart: request.form() → 从 64KB 回放流逐块读取
  │    └─ JSON: request.json() → 从 request._body 缓存读取
  │
  └─ Handler 执行
```

## 关键文件变更

| 文件 | 变更内容 |
|------|---------|
| `main.py` | 新增 `BodyCacheMiddleware`（ASGI 原始中间件） |
| `core/auth.py` | `_verify_signature` 支持原始字节验签；body 读取加 scope 缓存回退 + RuntimeError 防护 |
| `api/material.py` | Form 字段加 `alias`，解决 camelCase/snake_case 不匹配 |
| `docker-compose.yml` | volume 改为命名卷 `birdhelp-tmp` |

## 踩坑清单

1. **不要用 `@app.middleware("http")` 处理 body 缓存** → 它的 `_CachedRequest` 包装器会破坏 body 缓存
2. **ASGI body 回放要分块** → `python_multipart` 不接受单一巨块
3. **binary 数据签名走原始字节** → 不要 UTF-8 往返编解码
4. **跨语言接口字段名要统一** → 用 alias 做兼容
5. **Docker 卷权限** → 非 root 容器慎用 host bind mount
