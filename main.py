"""BirdHelp AI 模块 — FastAPI 应用入口。

负责组装应用、注册路由、异常处理、RabbitMQ 消费者生命周期管理。
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from starlette.types import ASGIApp, Scope, Receive, Send, Message

from api.router import api_router
from config import settings
from core.exceptions import BirdHelpError
from utils.file import ensure_temp_dir

CHUNK_SIZE = 65536  # ASGI 回放分块大小

_consumer_instance = None


async def _start_consumer_safe(consumer) -> None:
    """包装消费者启动，避免 RabbitMQ 连接失败导致整个应用崩溃。"""
    try:
        await consumer.start()
    except Exception as exc:
        logger.error(f"RabbitMQ consumer failed to start (HTTP server still running): {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期回调：启动时初始化临时目录与 RabbitMQ 消费者，关闭时停止。"""
    global _consumer_instance
    logger.info(f"{settings.app_name} starting, env: {'debug' if settings.debug else 'production'}")
    ensure_temp_dir()

    # 启动 RabbitMQ 消费者（后台任务，不阻塞 HTTP 服务）
    from broker.consumer import GenerationConsumer
    _consumer_instance = GenerationConsumer()
    consumer_task = asyncio.create_task(
        _start_consumer_safe(_consumer_instance)
    )

    yield

    logger.info(f"{settings.app_name} shutting down")
    if _consumer_instance:
        await _consumer_instance.stop()
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass


class BodyCacheMiddleware:
    """原始 ASGI 中间件：缓存请求体到 scope，再分块回放给下游。

    原因：FastAPI 对 multipart 请求会先调用 request.form() 消费 stream，
    导致 router 级 Depends (require_java_caller) 中的 request.body() 失败。
    本中间件在进入 FastAPI 前把 body 完整收集、存入 scope 供验签使用，
    然后分块回放，python_multipart 能正常解析。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return

        # 收集全部请求体
        body_chunks: list[bytes] = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)

        cached_body = b"".join(body_chunks)
        scope["_cached_body"] = cached_body

        # 分块回放，模拟真实 ASGI 数据流
        body_sent = 0

        async def replay_receive() -> Message:
            nonlocal body_sent
            if body_sent >= len(cached_body):
                return {"type": "http.request", "body": b"", "more_body": False}
            start = body_sent
            end = min(start + CHUNK_SIZE, len(cached_body))
            body_sent = end
            more = end < len(cached_body)
            return {"type": "http.request", "body": cached_body[start:end], "more_body": more}

        await self.app(scope, replay_receive, send)


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(BodyCacheMiddleware)


app.include_router(api_router)


@app.exception_handler(BirdHelpError)
async def birdhelp_exception_handler(request: Request, exc: BirdHelpError):
    """统一处理 BirdHelpError 及其子类，按错误码分段返回 HTTP 状态码。"""
    logger.warning(f"[{exc.code}] {exc.message}")
    return JSONResponse(
        status_code=400 if exc.code < 5000 else 500,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底捕获未预期的异常，返回通用内部错误。"""
    logger.exception(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 5001, "message": "内部未知错误", "data": None},
    )


@app.get("/")
async def health():
    """健康检查端点，用于 Java 后端探活。"""
    return {"status": "ok", "app": settings.app_name}
