# Python AI Module 集成 API Key 获取指南

> **2026-05-27 更新**：文档生成时的聊天模型凭证现在直接通过 RabbitMQ 消息传递（含 apiKey/baseUrl/modelName），Python 端无需在生成时调用此接口。此接口仅用于 embedding 模型初始化（向量模型固定，直接在 Python 端启动时调用一次即可）。

## 背景

原先 Python AI 模块的 LLM API Key 是写在 `.env` 文件中的，这种方式存在以下问题：

- 密钥硬编码在文件中，存在泄露风险
- 更换 Key 需要修改代码/配置文件并重新部署
- 无法动态切换不同的 Key（如多个供应商轮换）
- Base URL 写死在代码中，不同提供商的地址无法动态切换
- 大语言模型和向量模型使用同一提供商时 base_url 可能不同，无法区分

新的管理员端 API Key 管理功能上线后，所有 LLM API Key 及 Base URL 统一由 Java 后端管理，Python 端通过内部接口动态获取。

## 接口说明

### 获取 API Key

请求方式：`POST /internal/api-key/fetch`

该接口使用 **RSA-SHA256 签名** 进行鉴权（与现有的 `/internal/file/*`、`/internal/quota/*`、`/internal/task/*` 接口相同）。

**请求 Headers**：

| Header      | 说明                  |
|-------------|---------------------|
| X-Timestamp | 当前时间戳（秒），允许 5 分钟内偏差 |
| X-Nonce     | 随机字符串，防重放           |
| X-Signature | RSA-SHA256 签名       |

**签名生成方式**：

```
签名串 = METHOD\nPATH\nBODY\nTIMESTAMP\nNONCE

例如：
POST\n/internal/api-key/fetch\n\n1700000000\nrandom-nonce-123
```

使用 Python 端的 RSA **私钥** 对签名串进行 SHA256withRSA 签名，结果 Base64 编码后放入 `X-Signature` 头。

**请求参数**：

| 参数           | 类型     | 必填 | 说明                                           |
|--------------|--------|----|----------------------------------------------|
| providerName | String | 否  | 供应商名称过滤（如 `openai`、`qwen`），不传返回全部            |

> **注意**：`modelType` 参数已移除，所有存储的密钥均为聊天模型。向量模型密钥在 Python 端启动时硬编码调用一次即可。

**请求示例**：

```
# 获取 OpenAI 的聊天模型 Key
POST /api/internal/api-key/fetch?providerName=openai
```

**响应格式**：

```json
{
  "code": 0,
  "message": "ok",
  "data": [
    {
      "providerName": "openai",
      "apiKey": "sk-proj-xxxxxxxxxxxxxxxxxxxx",
      "baseUrl": "https://api.openai.com/v1",
      "modelName": "gpt-4o"
    },
    {
      "providerName": "qwen",
      "apiKey": "sk-xxxxxxxxxxxxxxxxxxxxxxxx",
      "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
      "modelName": "qwen-max"
    },
    {
      "providerName": "openai",
      "apiKey": "sk-proj-xxxxxxxxxxxxxxxxxxxx",
      "baseUrl": "https://api.openai.com/v1",
      "modelName": "text-embedding-3-small"
    }
  ]
}
```

响应中的 `apiKey` 已经是解密后的明文，同时返回 `baseUrl` 和 `modelName`，Python 端无需硬编码任何地址。

## Python 端实现示例

```python
import requests
import time
import uuid
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key

# 配置：从环境变量读取
JAVA_BACKEND_URL = os.getenv("JAVA_BACKEND_URL", "http://localhost:7890/api")
PRIVATE_KEY_PEM = os.getenv("RSA_PRIVATE_KEY")  # Python 端的 RSA 私钥

def _sign_request(method: str, path: str, body: str = "") -> dict:
    """生成 RSA 签名请求头"""
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    sign_str = f"{method}\n{path}\n{body}\n{timestamp}\n{nonce}"

    private_key = load_pem_private_key(PRIVATE_KEY_PEM.encode(), password=None)
    signature = private_key.sign(sign_str.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.b64encode(signature).decode()

    return {
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature_b64,
    }


def fetch_api_keys(provider_name: str = None) -> list[dict]:
    """从 Java 后端获取解密的 API Key 列表"""
    path = "/internal/api-key/fetch"
    params = []
    if provider_name:
        params.append(f"providerName={provider_name}")
    if params:
        path += "?" + "&".join(params)

    url = JAVA_BACKEND_URL + path
    headers = _sign_request("POST", path)
    headers["Content-Type"] = "application/json"

    resp = requests.post(url, headers=headers)
    resp.raise_for_status()
    result = resp.json()

    if result["code"] != 0:
        raise Exception(f"获取 API Key 失败: {result['message']}")

    return result["data"]


def get_client_config(provider_name: str) -> dict | None:
    """获取指定供应商的完整客户端配置（apiKey + baseUrl）"""
    keys = fetch_api_keys(provider_name)
    if keys:
        return keys[0]  # 返回 {apiKey, baseUrl, modelName, ...}
    return None
```

## 迁移步骤

### 1. 移除 .env 中的硬编码 Key

删除或注释掉 `.env` 文件中类似以下的行：

```bash
# OPENAI_API_KEY=sk-xxxxxx  ← 删除这行
# QWEN_API_KEY=sk-xxxxxx     ← 删除这行
```

### 2. 添加新的环境变量

```bash
# Java 后端地址
JAVA_BACKEND_URL=http://localhost:7890/api

# Python 端的 RSA 私钥（与现有的 AI 模块私钥一致，用于对请求签名）
RSA_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----
```

### 3. 改造调用代码

在需要调用大模型的地方，从直接读环境变量改为调用 `get_client_config()`：

```python
# 旧代码（硬编码方式 — 密钥和地址都写死）
# client = OpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     base_url="https://api.openai.com/v1",
# )

# 新代码（动态获取方式 — 密钥和地址都从后端获取）
from api_key_client import get_client_config

config = get_client_config("openai")
client = OpenAI(api_key=config["apiKey"], base_url=config["baseUrl"])
```

**向量模型同理**：

```python
# 旧代码
# embedding_client = OpenAIEmbeddings(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     base_url="https://api.openai.com/v1",
# )

# 新代码
# 注意：embedding 模型密钥在启动时硬编码初始化，此处仅作示例
config = get_client_config("openai")
embedding_client = OpenAIEmbeddings(api_key=config["apiKey"], base_url=config["baseUrl"])
```

### 4. 添加缓存（建议）

为避免每次调用都请求 Java 后端，建议在 Python 端添加简单的内存缓存：

```python
import threading
import time

_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 600  # 10 分钟

def get_client_config_cached(provider_name: str) -> dict | None:
    cache_key = f"{provider_name}:chat"
    with _cache_lock:
        entry = _cache.get(cache_key)
        if entry and time.time() - entry["ts"] < _CACHE_TTL:
            return entry["config"]

    config = get_client_config(provider_name)
    if config:
        with _cache_lock:
            _cache[cache_key] = {"config": config, "ts": time.time()}
    return config
```

## RSA 密钥说明

- Python 端使用 **私钥**（`RSA_PRIVATE_KEY`）对请求签名
- Java 端使用对应的 **公钥**（已配置在 `internal-api.public-key`）验证签名
- 这套密钥对与现有的文件上传、额度操作等内部接口使用的密钥相同，无需额外配置

## 管理端操作

管理员登录 BirdHelp 后台后，在 "API Key 管理" 菜单中可以进行以下操作：

- **新增 Key**：填写供应商名称、Base URL、API Key 明文、模型名称 → 保存后自动加密存储（所有密钥均为聊天模型）
- **编辑 Key**：修改 Key 值、Base URL、模型名称
- **启用/禁用**：临时关闭某个 Key 而不删除
- **删除**：彻底移除不再使用的 Key
- **查看**：列表中只显示脱敏信息（前4位+后4位），详情页可查看完整 Key

### 关键字段说明

| 字段           | 说明                        | 示例                                 |
|--------------|---------------------------|------------------------------------|
| providerName | 供应商名称                     | `openai`, `qwen`, `zhipu`          |
| baseUrl      | API 基础地址                  | `https://api.openai.com/v1`        |
| apiKey       | API 密钥（明文输入，自动加密存储）       | `sk-xxxx`                          |
| modelName    | 模型名称                      | `gpt-4o`, `text-embedding-3-small` |
| modelType    | 模型类型 | 已移除，所有存储的密钥均为聊天模型（嵌入向量模型已在 Python 端硬编码） |

> **2026-05-27**：`modelType` 字段已移除，`api_key` 表仅存储聊天模型密钥。嵌入向量模型（如 `text-embedding-3-small`）在 Python 端启动时硬编码获取一次即可。
