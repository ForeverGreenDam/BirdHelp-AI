from client.http import post


async def consume_quota(user_id: str, amount: int = 1, callback_id: str = "") -> dict:
    """生成前扣减额度。"""
    return await post("/internal/quota/consume", {
        "user_id": user_id,
        "amount": amount,
        "callback_id": callback_id,
    })


async def refund_quota(user_id: str, amount: int = 1, callback_id: str = "") -> dict:
    """生成失败退还额度。"""
    return await post("/internal/quota/refund", {
        "user_id": user_id,
        "amount": amount,
        "callback_id": callback_id,
    })
