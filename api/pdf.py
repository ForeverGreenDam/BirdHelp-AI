"""PDF 生成接口 — POST /ai/pdf/generate，同步模式。"""

from fastapi import APIRouter
from loguru import logger

from core.schemas import PdfGenerateRequest, ApiResponse
from services.generation import generate_pdf

router = APIRouter(prefix="/ai/pdf", tags=["pdf"])


@router.post("/generate")
async def generate_pdf_endpoint(request: PdfGenerateRequest):
    """同步生成 PDF 文件并上传至 Java 后端。

    生成流程（20–60 秒）:
    1. 扣减用户额度
    2. RAG 检索参考素材（可选）
    3. LLM 生成结构化内容 → JSON 校验 → 失败重试（最多 3 次）
    4. python-docx 构建 .docx → LibreOffice 转换为 .pdf
    5. 上传文件到 Java 后端存储
    6. 失败时自动退还额度
    """
    logger.info(f"PDF generate request: user={request.user_id} "
                f"topic={request.topic[:40]}... doc_type={request.doc_type}")
    result = await generate_pdf(request)
    return ApiResponse(code=0, message="success", data=result)
