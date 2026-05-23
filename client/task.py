"""Java 后端任务回调客户端 — 通知任务完成/失败/进度。

所有接口均为内部接口（/api/internal/task/*），需 RSA-SHA256 签名。
"""

from broker.schemas import TaskCallback, TaskProgress
from client.http import post as _post
from config import settings

INTERNAL = f"{settings.java_api_prefix}/internal/task"


async def callback(cb: TaskCallback) -> dict:
    """通知 Java 后端任务完成或失败。

    对应 POST /api/internal/task/callback。
    """
    body = cb.to_camel_dict()
    return await _post(f"{INTERNAL}/callback", body)


async def progress(prog: TaskProgress) -> dict:
    """推送任务进度到 Java 后端（可选）。

    对应 POST /api/internal/task/progress。
    """
    body = prog.to_camel_dict()
    return await _post(f"{INTERNAL}/progress", body)
