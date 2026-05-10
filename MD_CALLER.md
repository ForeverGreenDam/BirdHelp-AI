# BirdHelp 内部接口调用指南

> 本文档面向 AI 模块开发人员，说明如何对 BirdHelp Java 后端内部接口发起签名请求。

---

## 一、签名机制概述

所有 `/internal/**` 接口需要对请求进行 **RSA-SHA256 加签**，后端验签通过后才放行。

- **算法**：SHA256withRSA（RSA 密钥长度 2048 位）
- **私钥用途**：AI 模块持有，对请求签名
- **公钥用途**：Java 后端持有，验证签名
- **时间窗口**：默认 300 秒（5 分钟），超出窗口的请求会被拒绝

---

## 二、请求头

每个请求必须携带以下三个 Header：

| Header | 说明 | 示例 |
|--------|------|------|
| `Content-Type` | 固定值 | `application/json` |
| `X-Timestamp` | Unix 时间戳（**毫秒**），与服务器时间偏差不能超过 5 分钟 | `1746889200000` |
| `X-Nonce` | 随机字符串，每次请求不同，建议 UUID | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `X-Signature` | Base64 编码的 RSA 签名（详见第三节） | `MmBxQJvP...` |

---

## 三、签名字符串构造

### 3.1 拼接规则

将以下 5 个部分用换行符 `\n` 拼接为一个字符串：

```
{METHOD}\n{PATH}\n{BODY}\n{TIMESTAMP}\n{NONCE}
```

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `METHOD` | HTTP 方法，大写 | `POST` |
| `PATH` | 请求路径（含 `/api` 前缀） | `/api/internal/quota/consume` |
| `BODY` | 请求体 JSON 字符串（原样，不做任何格式化） | `{"userId":1,"relatedId":123}` |
| `TIMESTAMP` | 同 `X-Timestamp` 的值 | `1746889200000` |
| `NONCE` | 同 `X-Nonce` 的值 | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |

### 3.2 示例

假设请求参数如下：

```
METHOD    = POST
PATH      = /api/internal/quota/consume
BODY      = {"userId":1,"relatedId":123}
TIMESTAMP = 1746889200000
NONCE     = a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

拼接后的待签名字符串：

```
POST
/api/internal/quota/consume
{"userId":1,"relatedId":123}
1746889200000
a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

**重要**：`\n` 表示换行符（ASCII 10），不是字面量字符串 `\n`。

---

## 四、签名生成

### 4.1 Python 示例

```python
import base64
import time
import uuid
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# 加载私钥（PKCS#8 DER Base64）
PRIVATE_KEY_B64 = "MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQCu5pbjePvwgwxzpMeI1ZhSmljArGlrKVx6WgEzcuEjMTKiqSIIrKIafJEet0SPYpdIiHT4RiOraRuk/Sdty29fRjkp5CuUYfFGagF3eZzbBBsyWD/J97d7lRg8iflTiTzUdYgBPZZjPeBLEdQiOzvRUdlJGB3uLJH61SPtZe/mMtjrKybl9ktgPFRHjFMNqnpNCG6TyiAKAxXNZ6IN3SBAIpGu4DC5YxqxOgPQ4kI94zpwnTzYaTh8jX4JenEj2k+eQ8Y5isw6Y1RLH3FsmZ9gYcKmW7w42rKkgQcOmQExrR6oGQfzA5BCeC3LWlcFGtXEyPv99RZYXS+VlPi08eoNAgMBAAECggEAGQgIdVLV3+Spjg15vzQuojfT1vN1/O/E+//Qpy/cV+CNKimBpPMsGhVU4awCBHFsTGW3M+c56KjY24Kdt4GDlYOj38J3mDtyQA0g25wMnm3WhJyLuJia6nV6rANlKxb7nT6a8e6CDP8IkEXjcei/VWRc8DCi6/j2BYumoi3SKURGEz8larRofaVJIk7B8JOgxURPbhLTydZzepJXufOM9EdBD/lRz296WBFrM6fODK9NnD0W7Dub9bK75cwXMXij5+mmeRUSrSRtfe79LWVSE/6ablwsmn0XsCnzbyd/eV461abohsW+cB6X2fc0ET6N514rzMKLXrxM6qEjMmcqUwKBgQDd7LyhxQbCzT1dTOwOVM0jWMmFzvrGGTLy5zBZqUaJUzFyKny2wQG3TCWepM53r8HoPgs/wpTVrpcHd4ETRacGh6cZf+7IgAT6EE8zRpplr+bTqNLb59Sq9zwbv8deLH7aBw/v47emRV2MwHh7gJCp2qCwC1A5Kafu0tWRQKVKZwKBgQDJwXcq6fGktl/gZ5k7zTlIPuezcLmhIaX5B8O9sVEI04agwnUWMQ+w5MdygMhfnomhCKtQCQcwCzRHzUUJ0NS+cv/LXo6NQSCxUEtD9xDUld0xQpkha70VRpLI+D7ctXbdCh9tzCydv3Ju6pCvfqCaUbwEvaTmwT4Vyfcg8LUHawKBgQCX6ECGixNBrLNgdhLvDGUO2Ou4yCEoEH+rfUy/UvuRbHzgJO0RO7Qs/9aQbUdW7dvRWQbiMhMm4UdIOSkFRBw8gAaFkeilHdxKP3e3JZDyIiHiqCENnfcYv/tJE1EoyVRbcZIbJsjC66BJhEX0Y+CiI6DyYAwd1MG63F6L+rAp6QKBgQC/hEHd37M9es2qVE1WQiqFFQmXAYOEnE9UBPXfZKmaqkia49yHk0zky1c0r2EFu5XD4lnUoK1NAuW+3vERL0Yz/zAn2fuRxOgGyUSZILe+RQByWVjJK9+Siaqe0V/C3RMXIhvRe0ZC/E/hUBLGNHq54qqLCYa2cWvA/TX08+m0PwKBgQCU0knI+7z05eH/JIQ7UWk7nc6Iimdlrq4SczKfzlK+oM5K5wFz5nbyKuNFhy8EIzTKZixLBKS2zRlkLf7e4JXFUEvFEcX2RI034ExRNvbzOXdLcMIGBSuNVo5KonqMNX7ChW7r7aodmCxEqSz8dPlTnR8IlC+Bkc1mae+zbNbibQ=="

def load_private_key(b64_key: str):
    key_bytes = base64.b64decode(b64_key)
    return serialization.load_der_private_key(key_bytes, password=None, backend=default_backend())

def sign(method: str, path: str, body: str, timestamp: str, nonce: str) -> str:
    private_key = load_private_key(PRIVATE_KEY_B64)
    sign_string = f"{method}\n{path}\n{body}\n{timestamp}\n{nonce}"
    signature = private_key.sign(
        sign_string.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    return base64.b64encode(signature).decode("utf-8")

# ---- 发起请求 ----
METHOD = "POST"
PATH = "/api/internal/quota/consume"
BODY = '{"userId":1,"relatedId":123}'
TIMESTAMP = str(int(time.time() * 1000))
NONCE = str(uuid.uuid4())

signature = sign(METHOD, PATH, BODY, TIMESTAMP, NONCE)

headers = {
    "Content-Type": "application/json",
    "X-Timestamp": TIMESTAMP,
    "X-Nonce": NONCE,
    "X-Signature": signature,
}

response = requests.post(
    f"http://localhost:7890{PATH}",
    headers=headers,
    data=BODY,
)
print(response.status_code, response.json())
```

### 4.2 Java 示例

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
import java.util.UUID;

public class InternalApiCaller {

    private static final String PRIVATE_KEY_B64 = "MIIEvwIBADAN...";  // 同上私钥
    private static final String BASE_URL = "http://localhost:7890";

    private static PrivateKey loadPrivateKey(String b64Key) throws Exception {
        byte[] keyBytes = Base64.getDecoder().decode(b64Key);
        PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(keyBytes);
        return KeyFactory.getInstance("RSA").generatePrivate(spec);
    }

    private static String sign(String method, String path, String body,
                               String timestamp, String nonce) throws Exception {
        PrivateKey privateKey = loadPrivateKey(PRIVATE_KEY_B64);
        String signString = method + "\n" + path + "\n" + body + "\n" + timestamp + "\n" + nonce;

        Signature signature = Signature.getInstance("SHA256withRSA");
        signature.initSign(privateKey);
        signature.update(signString.getBytes(StandardCharsets.UTF_8));
        return Base64.getEncoder().encodeToString(signature.sign());
    }

    public static void main(String[] args) throws Exception {
        String method = "POST";
        String path = "/api/internal/quota/consume";
        String body = "{\"userId\":1,\"relatedId\":123}";
        String timestamp = String.valueOf(Instant.now().toEpochMilli());
        String nonce = UUID.randomUUID().toString();

        String signature = sign(method, path, body, timestamp, nonce);

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(BASE_URL + path))
                .header("Content-Type", "application/json")
                .header("X-Timestamp", timestamp)
                .header("X-Nonce", nonce)
                .header("X-Signature", signature)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpClient client = HttpClient.newHttpClient();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println(response.statusCode() + " " + response.body());
    }
}
```

---

## 五、当前可用接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/internal/quota/consume` | 扣减额度（生成前调用） |
| POST | `/api/internal/quota/refund` | 退还额度（生成失败调用） |

请求体均为 JSON：

```json
{
  "userId": 1,
  "relatedId": 123
}
```

- `userId`：必填，要操作的用户 ID
- `relatedId`：可选，关联的生成任务 ID，用于流水对账

---

## 六、验签失败排查

| 错误信息 | 原因 | 解决 |
|----------|------|------|
| 缺少签名请求头 | Header 缺失 | 确保传了 `X-Timestamp`、`X-Nonce`、`X-Signature` |
| 签名请求头不能为空 | Header 值为空 | 确保各 Header 都有值 |
| X-Timestamp 格式无效 | 时间戳不是纯数字 | 传毫秒级 Unix 时间戳字符串 |
| 请求已过期或时间偏差过大 | 时间戳超出 5 分钟窗口 | 检查调用方机器时间是否与服务器同步，或生成签名后是否过太久才发出请求 |
| 签名不匹配 | 签名字符串构造有误或密钥不对 | 逐段比对 METHOD/PATH/BODY/TIMESTAMP/NONCE 与服务器期望是否一致 |

常见坑：
- `PATH` 没有带 `/api` 前缀（后端实际路径是 `/api/internal/...`）
- `BODY` 进行了格式化（加了换行/空格），应与实际发送的一致
- 时间戳用了**秒**而不是毫秒
- 签名字符串中的 `\n` 写成了字面量字符 `\n` 而非真正的换行符

---

## 七、密钥信息

| 密钥 | 持有方 | 格式 |
|------|--------|------|
| 私钥 | AI 模块（调用方） | PKCS#8 DER，Base64 编码 |
| 公钥 | Java 后端 | X.509 DER，Base64 编码 |

> 生产环境请重新生成密钥对，当前密钥仅用于开发环境。
>
> 生成命令：
> ```bash
> # 生成私钥
> openssl genpkey -algorithm RSA -out private_key.pem -pkeyopt rsa_keygen_bits:2048
> # 导出公钥
> openssl rsa -pubout -in private_key.pem -out public_key.pem
> # 转为 Base64（Java 配置用）
> openssl rsa -pubin -in public_key.pem -outform DER | base64 -w0  # 公钥
> openssl pkcs8 -topk8 -nocrypt -in private_key.pem -outform DER | base64 -w0  # 私钥
> ```
