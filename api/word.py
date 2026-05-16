"""Word 生成接口 — POST /ai/word/generate，同步模式。"""

from fastapi import APIRouter
from loguru import logger

from core.schemas import WordGenerateRequest, ApiResponse
from services.generation import generate_word

router = APIRouter(prefix="/ai/word", tags=["word"])


@router.post("/generate")
async def generate_word_endpoint(request: WordGenerateRequest):
    """同步生成 Word 文件并上传至 Java 后端。

    生成流程（20–60 秒）:
    1. 扣减用户额度
    2. RAG 检索参考素材（可选）
    3. LLM 生成结构化文档内容 → JSON 校验 → 失败重试（最多 3 次）
    4. python-docx 构建 .docx 文件
    5. 上传文件到 Java 后端存储
    6. 失败时自动退还额度
    """
    logger.info(f"Word generate request: user={request.user_id} "
                f"topic={request.topic[:40]}... doc_type={request.doc_type}")
    result = await generate_word(request)
    return ApiResponse(code=0, message="success", data=result)
