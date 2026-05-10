"""API 路由汇总，将各模块子路由挂载到统一前缀下。"""

from fastapi import APIRouter

from api.task import router as task_router
from api.material import router as material_router

api_router = APIRouter()
api_router.include_router(task_router)
api_router.include_router(material_router)

# Phase 3-5 will add:
# from api.ppt import router as ppt_router
# from api.word import router as word_router
# from api.chat import router as chat_router
# ...
