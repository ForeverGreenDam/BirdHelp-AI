"""API 路由汇总，将各模块子路由挂载到统一前缀下。

所有 /ai/* 路由由 Java 后端代理转发，需通过 RSA-SHA256 签名验证。
文档生成（PPT/Word/PDF）已迁移到 RabbitMQ 异步模式，HTTP 端点已移除。
"""

from fastapi import APIRouter, Depends

from core.auth import require_java_caller
from api.material import router as material_router
from modify.api import router as modify_router

api_router = APIRouter(dependencies=[Depends(require_java_caller)])
api_router.include_router(material_router)
api_router.include_router(modify_router)
