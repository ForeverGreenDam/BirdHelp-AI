"""Java 后端额度管理客户端 — 生成前扣减、失败后退还。"""

from client.http import post
from config import settings

PREFIX = f"{settings.java_api_prefix}/internal"


async def consume_quota(user_id: int, related_id: int | None = None) -> dict:
    """文档生成前调用，扣减用户一次额度。"""
    body = {"userId": user_id}
    if related_id is not None:
        body["relatedId"] = related_id
    return await post(f"{PREFIX}/internal/quota/consume", body)


async def refund_quota(user_id: int, related_id: int | None = None) -> dict:
    """文档生成失败时调用，退还用户一次额度。"""
    body = {"userId": user_id}
    if related_id is not None:
        body["relatedId"] = related_id
    return await post(f"{PREFIX}/internal/quota/refund", body)
