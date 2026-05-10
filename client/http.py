"""基于 RSA-SHA256 签名的异步 HTTP 客户端。

与 Java 后端内部通信，签名机制替代传统 Bearer Token：
- 每个请求携带 X-Timestamp / X-Nonce / X-Signature 头
- 签名字符串格式: METHOD\nPATH\nBODY\nTIMESTAMP\nNONCE
"""

import base64
import time
import uuid

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from config import settings

_private_key = None


def _load_private_key():
    """懒加载 RSA 私钥，全局只解析一次。"""
    global _private_key
    if _private_key is None:
        key_bytes = base64.b64decode(settings.java_private_key_b64)
        _private_key = serialization.load_der_private_key(
            key_bytes, password=None, backend=default_backend()
        )
    return _private_key


def _sign(method: str, path: str, body: str, timestamp: str, nonce: str) -> str:
    """使用 RSA-SHA256 生成请求签名。"""
    sign_string = f"{method}\n{path}\n{body}\n{timestamp}\n{nonce}"
    private_key = _load_private_key()
    signature = private_key.sign(
        sign_string.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


def _make_headers(method: str, path: str, body: str) -> dict[str, str]:
    """构造包含签名、时间戳、随机数的请求头。"""
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())
    signature = _sign(method, path, body, timestamp, nonce)
    return {
        "Content-Type": "application/json",
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


async def post(path: str, json_body: dict | None = None) -> dict:
    """向 Java 后端发送带签名的 POST 请求，返回 JSON 响应。"""
    body_str = "{}" if json_body is None else _dump_json(json_body)
    headers = _make_headers("POST", path, body_str)

    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=30.0,
    ) as c:
        resp = await c.post(path, content=body_str, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def upload_file(path: str, file_path: str, fields: dict | None = None) -> dict:
    """以 multipart/form-data 上传文件到 Java 后端。

    文件内容不参与签名，签名仅基于 fields 的 JSON 序列化值。
    """
    fields = fields or {}
    body_str = _dump_json(fields)
    headers = _make_headers("POST", path, body_str)

    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=60.0,
    ) as c:
        headers.pop("Content-Type", None)
        with open(file_path, "rb") as f:
            resp = await c.post(
                path,
                files={"file": f},
                data=fields,
                headers=headers,
            )
        resp.raise_for_status()
        return resp.json()


def _dump_json(obj: dict) -> str:
    """紧凑 JSON 序列化，不含空格，保持与 Java 端签名一致。"""
    import json
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
