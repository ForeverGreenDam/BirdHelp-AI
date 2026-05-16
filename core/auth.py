"""Java 后端调用方签名验证 — FastAPI 依赖项。

Java 后端代理转发前端请求到 AI 模块时，需对请求进行 RSA-SHA256 加签。
本模块提供 Depends(require_java_caller) 依赖，校验 X-Timestamp / X-Nonce / X-Signature。

签名字符串格式: {METHOD}\n{PATH}\n{BODY}\n{TIMESTAMP}\n{NONCE}
"""

import base64
import time

from fastapi import Request, HTTPException
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

from config import settings

_public_key = None


def _load_public_key():
    """懒加载 RSA 公钥，全局只解析一次。"""
    global _public_key
    if _public_key is None:
        if not settings.java_caller_public_key_b64:
            raise HTTPException(
                status_code=500,
                detail={"code": 5001, "message": "AI 模块未配置 java_caller_public_key_b64", "data": None},
            )
        key_bytes = base64.b64decode(settings.java_caller_public_key_b64)
        _public_key = serialization.load_der_public_key(key_bytes)
    return _public_key


def _verify_signature(method: str, path: str, body: str,
                      timestamp: str, nonce: str, signature_b64: str,
                      raw_body: bytes | None = None) -> bool:
    """验证 RSA-SHA256 签名。

    优先使用 raw_body 构造签名字节串，避免 binary 内容
    (如 multipart 中的 PDF) 经 UTF-8 编解码往返后与 Java 端不一致。
    raw_body 为 None 时回退到 body 字符串路径。
    """
    if raw_body is not None:
        sign_bytes = (
            method.encode() + b"\n" +
            path.encode() + b"\n" +
            raw_body + b"\n" +
            timestamp.encode() + b"\n" +
            nonce.encode()
        )
    else:
        sign_string = f"{method}\n{path}\n{body}\n{timestamp}\n{nonce}"
        sign_bytes = sign_string.encode("utf-8")
    try:
        signature = base64.b64decode(signature_b64)
        _load_public_key().verify(
            signature,
            sign_bytes,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return True
    except InvalidSignature:
        return False


async def require_java_caller(request: Request):
    """FastAPI 依赖项 — 验证请求是否来自 Java 后端（带有效签名）。

    挂载到路由上后，所有匹配的请求在进入 handler 前会先经过此校验。
    校验失败返回 401，校验成功放行。
    """
    # 1. 提取签名头
    timestamp = request.headers.get("X-Timestamp", "")
    nonce = request.headers.get("X-Nonce", "")
    signature_b64 = request.headers.get("X-Signature", "")

    if not timestamp or not nonce or not signature_b64:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "缺少签名请求头 (X-Timestamp / X-Nonce / X-Signature)", "data": None},
        )

    # 2. 校验时间戳格式与时效
    try:
        ts_ms = int(timestamp)
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "X-Timestamp 格式无效，应为毫秒级 Unix 时间戳", "data": None},
        )

    now_ms = int(time.time() * 1000)
    drift_ms = abs(now_ms - ts_ms)
    if drift_ms > settings.java_sign_timeout_seconds * 1000:
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "请求已过期或时间偏差过大", "data": None},
        )

    # 3. 读取请求体
    #    正常情况 require_java_caller (router Depends) 先于 Form/File
    #    解析执行，request.body() 是 stream 的第一个消费者。
    #    若因版本差异或 uvloop 导致 stream 已被消费，回退至 scope 缓存。
    try:
        body_bytes = await request.body()
    except RuntimeError:
        body_bytes = request.scope.get("_cached_body", b"")
    body_str = body_bytes.decode("utf-8", errors="replace")

    # 4. 构造签名路径（含 query string）
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    # 5. 验签 — 优先用原始字节避免 binary 编解码差异
    if not _verify_signature(request.method, path, body_str, timestamp, nonce, signature_b64,
                             raw_body=body_bytes):
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "签名不匹配", "data": None},
        )
