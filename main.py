"""BirdHelp AI 模块 — FastAPI 应用入口。

负责组装应用、注册路由、异常处理与生命周期管理。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from api.router import api_router
from config import settings
from core.exceptions import BirdHelpError
from utils.file import ensure_temp_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期回调：启动时初始化临时目录，关闭时打印日志。"""
    logger.info(f"{settings.app_name} starting, env: {'debug' if settings.debug else 'production'}")
    ensure_temp_dir()
    yield
    logger.info(f"{settings.app_name} shutting down")


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    lifespan=lifespan,
)

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
