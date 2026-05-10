"""Celery 应用实例 — 异步任务队列配置。

使用 Redis 作为 broker 和 result backend。
"""

from celery import Celery

from config import settings

app = Celery(
    "birdhelp",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
