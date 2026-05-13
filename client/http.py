"""基于 RSA-SHA256 签名的异步 HTTP 客户端。

与 Java 后端内部通信，签名机制替代传统 Bearer Token：
- 每个请求携带 X-Timestamp / X-Nonce / X-Signature 头
- 签名字符串格式: METHOD\nPATH\nBODY\nTIMESTAMP\nNONCE
"""

import base64
import time
import uuid
from pathlib import Path

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

    通过同步 Client.build_request 先拿到完整 multipart 编码请求体，
    再对其签名，确保签名与实际发送的报文一致。
    """
    fields = fields or {}
    filename = Path(file_path).name

    with open(file_path, "rb") as f:
        file_content = f.read()

    # 1. 用同步 Client 构建请求，获取完整 multipart 请求体与 Content-Type
    with httpx.Client(base_url=settings.java_base_url) as sync_client:
        req = sync_client.build_request(
            "POST", path,
            files={"file": (filename, file_content, "application/octet-stream")},
            data=fields,
        )
        body_bytes = req.read()
        content_type = req.headers.get("content-type", "")

    # 2. 基于完整请求体生成签名
    body_str = body_bytes.decode("utf-8", errors="replace")
    headers = _make_headers("POST", path, body_str)
    headers["Content-Type"] = content_type

    # 3. 发送请求
    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=60.0,
    ) as c:
        resp = await c.post(path, content=body_bytes, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def get(path: str, params: dict | None = None) -> dict:
    """向 Java 后端发送带签名的 GET 请求，返回 JSON 响应。"""
    params = params or {}
    query_string = _encode_query(params)
    signed_path = f"{path}?{query_string}" if query_string else path
    headers = _make_headers("GET", signed_path, "")

    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=30.0,
    ) as c:
        resp = await c.get(path, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def download_file(path: str, params: dict | None = None, save_path: str = "") -> bytes:
    """从 Java 后端下载文件，返回原始字节（也可指定 save_path 写到磁盘）。"""
    params = params or {}
    query_string = _encode_query(params)
    signed_path = f"{path}?{query_string}" if query_string else path
    headers = _make_headers("GET", signed_path, "")

    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=60.0,
    ) as c:
        resp = await c.get(path, params=params, headers=headers)
        resp.raise_for_status()
        content = resp.read()
        if save_path:
            with open(save_path, "wb") as f:
                f.write(content)
        return content


async def delete(path: str, params: dict | None = None) -> dict:
    """向 Java 后端发送带签名的 DELETE 请求。"""
    params = params or {}
    query_string = _encode_query(params)
    signed_path = f"{path}?{query_string}" if query_string else path
    headers = _make_headers("DELETE", signed_path, "")

    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=30.0,
    ) as c:
        resp = await c.delete(path, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def put(path: str, params: dict | None = None, json_body: dict | None = None) -> dict:
    """向 Java 后端发送带签名的 PUT 请求。"""
    params = params or {}
    body_str = _dump_json(json_body) if json_body else "{}"
    query_string = _encode_query(params)
    signed_path = f"{path}?{query_string}" if query_string else path
    headers = _make_headers("PUT", signed_path, body_str)

    async with httpx.AsyncClient(
        base_url=settings.java_base_url,
        timeout=30.0,
    ) as c:
        resp = await c.put(path, params=params, content=body_str, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _dump_json(obj: dict) -> str:
    """紧凑 JSON 序列化，不含空格，保持与 Java 端签名一致。"""
    import json
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _encode_query(params: dict) -> str:
    """将 dict 编码为 URL query string，按 key 排序保证签名确定性。"""
    from urllib.parse import urlencode
    return urlencode(sorted(params.items()))
