from client.http import post
from config import settings

PREFIX = f"{settings.java_api_prefix}/internal"


async def consume_quota(user_id: int, related_id: int | None = None) -> dict:
    """生成前扣减额度。"""
    body = {"userId": user_id}
    if related_id is not None:
        body["relatedId"] = related_id
    return await post(f"{PREFIX}/quota/consume", body)


async def refund_quota(user_id: int, related_id: int | None = None) -> dict:
    """生成失败退还额度。"""
    body = {"userId": user_id}
    if related_id is not None:
        body["relatedId"] = related_id
    return await post(f"{PREFIX}/quota/refund", body)
