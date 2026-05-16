"""API 路由汇总，将各模块子路由挂载到统一前缀下。

所有 /ai/* 路由由 Java 后端代理转发，需通过 RSA-SHA256 签名验证。
"""

from fastapi import APIRouter, Depends

from core.auth import require_java_caller
from api.material import router as material_router
from api.ppt import router as ppt_router
from api.word import router as word_router
from api.pdf import router as pdf_router

api_router = APIRouter(dependencies=[Depends(require_java_caller)])
api_router.include_router(material_router)
api_router.include_router(ppt_router)
api_router.include_router(word_router)
api_router.include_router(pdf_router)
