"""PPT 生成接口 — POST /ai/ppt/generate，同步模式。"""

from fastapi import APIRouter
from loguru import logger

from core.schemas import PptGenerateRequest, ApiResponse
from services.generation import generate_ppt

router = APIRouter(prefix="/ai/ppt", tags=["ppt"])


@router.post("/generate")
async def generate_ppt_endpoint(request: PptGenerateRequest):
    """同步生成 PPT 文件并上传至 Java 后端。

    生成流程（20–60 秒）:
    1. 扣减用户额度
    2. RAG 检索参考素材（可选）
    3. LLM 生成结构化大纲 → JSON 校验 → 失败重试（最多 3 次）
    4. python-pptx 构建 .pptx 文件
    5. 上传文件到 Java 后端存储
    6. 失败时自动退还额度
    """
    logger.info(f"PPT generate request: user={request.user_id} "
                f"topic={request.topic[:40]}... slides={request.slide_count}")
    result = await generate_ppt(request)
    return ApiResponse(code=0, message="success", data=result)
