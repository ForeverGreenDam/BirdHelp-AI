"""PPT 生成接口 — POST /ai/ppt/generate，同步模式。"""

from fastapi import APIRouter
from loguru import logger

from core.schemas import PptGenerateRequest, ApiResponse
from services.generation import generate_ppt

router = APIRouter(prefix="/ai/ppt", tags=["ppt"])


@router.post("/generate")
async def generate_ppt_endpoint(request: PptGenerateRequest):
    """同步生成 PPT 文件并上传至 Java 后端。

    生成流程（30–90 秒）:
    1. 扣减用户额度
    2. RAG 检索参考素材（可选）
    3. LLM 生成视觉描述 JSON → 校验 → 失败重试（最多 3 次）
    4. 图片搜索与下载（Unsplash→Pexels→占位图降级）
    5. Q&A 逐页质量评分 + 修复循环（最多 3 轮）
    6. 设计系统 + 布局渲染器构建 .pptx
    7. 上传文件到 Java 后端存储
    8. 失败时自动退还额度
    """
    logger.info(f"PPT generate request: user={request.user_id} "
                f"topic={request.topic[:40]}... slides={request.slide_count}")
    result = await generate_ppt(request)
    return ApiResponse(code=0, message="success", data=result)
