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
from cryptography.hazmat.exceptions import InvalidSignature

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
                      timestamp: str, nonce: str, signature_b64: str) -> bool:
    """验证 RSA-SHA256 签名。"""
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

    # 3. 读取请求体（FastAPI/Starlette 自动缓存到 _body，下游可重复读取）
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8", errors="replace")

    # 4. 构造签名路径（含 query string）
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    # 5. 验签
    if not _verify_signature(request.method, path, body_str, timestamp, nonce, signature_b64):
        raise HTTPException(
            status_code=401,
            detail={"code": 401, "message": "签名不匹配", "data": None},
        )
