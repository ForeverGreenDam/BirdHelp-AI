"""API 路由汇总，将各模块子路由挂载到统一前缀下。"""

from fastapi import APIRouter

from api.task import router as task_router

api_router = APIRouter()
api_router.include_router(task_router)

# Phase 2-5 will add:
# from api.ppt import router as ppt_router
# from api.word import router as word_router
# ...
