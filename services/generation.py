"""文档生成业务编排 — 额度管理 → LangGraph 执行 → 文件上传 → 错误退款。"""

from pathlib import Path

from loguru import logger

from core.exceptions import BirdHelpError, FileGenerationError, QuotaInsufficientError
from core.schemas import PptGenerateRequest, WordGenerateRequest, PdfGenerateRequest
from client.quota import consume_quota, refund_quota
from client.file import upload as upload_file
from graph.generation_graph import get_generation_graph


async def generate_ppt(request: PptGenerateRequest) -> dict:
    """执行 PPT 生成的完整业务流程。"""
    user_id_int = int(request.user_id)
    related_id = int(request.callback_id) if request.callback_id else None
    quota_consumed = False
    file_path = ""

    try:
        result = await consume_quota(user_id_int, related_id)
        if not _quota_success(result):
            raise QuotaInsufficientError(
                result.get("message", "额度不足，无法开始生成任务")
            )
        quota_consumed = True
        logger.info(f"Quota consumed for user={user_id_int} project={request.project_id}")

        graph = get_generation_graph()
        graph_result = await graph.ainvoke({
            "user_id": request.user_id,
            "project_id": request.project_id,
            "topic": request.topic,
            "style": request.style,
            "slide_count": request.slide_count,
            "language": request.language,
            "extra_prompt": request.extra_prompt or "",
            "rag_enabled": request.rag_enabled,
            "material_ids": request.material_ids or [],
            "doc_type": "ppt",
            "doc_subtype": "",
            "word_count": 0,
            "context": "",
            "chain_output": "",
            "parsed_outline": {},
            "attempt": 0,
            "file_path": "",
            "error": "",
        })

        if graph_result.get("error"):
            raise FileGenerationError(graph_result["error"])

        file_path = graph_result.get("file_path", "")
        if not file_path:
            raise FileGenerationError("生成的文件路径为空")

        project_id_int = int(request.project_id) if request.project_id else 0
        upload_result = await upload_file(
            file_path=file_path,
            user_id=user_id_int,
            project_id=project_id_int,
            file_name=f"{request.topic}.pptx",
        )
        logger.info(f"PPT uploaded: {upload_result}")
        return upload_result

    except QuotaInsufficientError:
        raise
    except FileGenerationError:
        if quota_consumed:
            await _safe_refund(user_id_int, related_id)
        raise
    except Exception as exc:
        logger.error(f"PPT generation failed: {exc}")
        if quota_consumed:
            await _safe_refund(user_id_int, related_id)
        raise FileGenerationError(str(exc)) from exc

    finally:
        if file_path:
            p = Path(file_path)
            if p.exists():
                p.unlink()


async def generate_word(request: WordGenerateRequest) -> dict:
    """执行 Word 生成的完整业务流程。"""
    user_id_int = int(request.user_id)
    related_id = int(request.callback_id) if request.callback_id else None
    quota_consumed = False
    file_path = ""

    try:
        result = await consume_quota(user_id_int, related_id)
        if not _quota_success(result):
            raise QuotaInsufficientError(
                result.get("message", "额度不足，无法开始生成任务")
            )
        quota_consumed = True
        logger.info(f"Quota consumed for user={user_id_int} project={request.project_id}")

        graph = get_generation_graph()
        graph_result = await graph.ainvoke({
            "user_id": request.user_id,
            "project_id": request.project_id,
            "topic": request.topic,
            "language": request.language,
            "extra_prompt": request.extra_prompt or "",
            "rag_enabled": request.rag_enabled,
            "material_ids": request.material_ids or [],
            "doc_type": "word",
            "doc_subtype": request.doc_type,
            "style": "academic",
            "slide_count": 0,
            "word_count": request.word_count,
            "context": "",
            "chain_output": "",
            "parsed_outline": {},
            "attempt": 0,
            "file_path": "",
            "error": "",
        })

        if graph_result.get("error"):
            raise FileGenerationError(graph_result["error"])

        file_path = graph_result.get("file_path", "")
        if not file_path:
            raise FileGenerationError("生成的文件路径为空")

        project_id_int = int(request.project_id) if request.project_id else 0
        upload_result = await upload_file(
            file_path=file_path,
            user_id=user_id_int,
            project_id=project_id_int,
            file_name=f"{request.topic}.docx",
        )
        logger.info(f"Word uploaded: {upload_result}")
        return upload_result

    except QuotaInsufficientError:
        raise
    except FileGenerationError:
        if quota_consumed:
            await _safe_refund(user_id_int, related_id)
        raise
    except Exception as exc:
        logger.error(f"Word generation failed: {exc}")
        if quota_consumed:
            await _safe_refund(user_id_int, related_id)
        raise FileGenerationError(str(exc)) from exc

    finally:
        if file_path:
            p = Path(file_path)
            if p.exists():
                p.unlink()


async def generate_pdf(request: PdfGenerateRequest) -> dict:
    """执行 PDF 生成的完整业务流程。"""
    user_id_int = int(request.user_id)
    related_id = int(request.callback_id) if request.callback_id else None
    quota_consumed = False
    file_path = ""

    try:
        result = await consume_quota(user_id_int, related_id)
        if not _quota_success(result):
            raise QuotaInsufficientError(
                result.get("message", "额度不足，无法开始生成任务")
            )
        quota_consumed = True
        logger.info(f"Quota consumed for user={user_id_int} project={request.project_id}")

        graph = get_generation_graph()
        graph_result = await graph.ainvoke({
            "user_id": request.user_id,
            "project_id": request.project_id,
            "topic": request.topic,
            "language": request.language,
            "extra_prompt": request.extra_prompt or "",
            "rag_enabled": request.rag_enabled,
            "material_ids": request.material_ids or [],
            "doc_type": "pdf",
            "doc_subtype": request.doc_type,
            "style": "academic",
            "slide_count": 0,
            "word_count": 0,
            "context": "",
            "chain_output": "",
            "parsed_outline": {},
            "attempt": 0,
            "file_path": "",
            "error": "",
        })

        if graph_result.get("error"):
            raise FileGenerationError(graph_result["error"])

        file_path = graph_result.get("file_path", "")
        if not file_path:
            raise FileGenerationError("生成的文件路径为空")

        project_id_int = int(request.project_id) if request.project_id else 0
        ext = Path(file_path).suffix or ".pdf"
        upload_result = await upload_file(
            file_path=file_path,
            user_id=user_id_int,
            project_id=project_id_int,
            file_name=f"{request.topic}{ext}",
        )
        logger.info(f"PDF uploaded: {upload_result}")
        return upload_result

    except QuotaInsufficientError:
        raise
    except FileGenerationError:
        if quota_consumed:
            await _safe_refund(user_id_int, related_id)
        raise
    except Exception as exc:
        logger.error(f"PDF generation failed: {exc}")
        if quota_consumed:
            await _safe_refund(user_id_int, related_id)
        raise FileGenerationError(str(exc)) from exc

    finally:
        if file_path:
            p = Path(file_path)
            if p.exists():
                p.unlink()


def _quota_success(result: dict) -> bool:
    """判断 Java 后端额度扣减是否成功。

    Java 后端成功响应约定为 code == 0，其他均视为失败。
    """
    return result.get("code") == 0


async def _safe_refund(user_id: int, related_id: int | None) -> None:
    """安全退款，失败仅记日志，不遮蔽原始异常。"""
    try:
        await refund_quota(user_id, related_id)
        logger.info(f"Quota refunded for user={user_id}")
    except Exception as e:
        logger.error(f"Quota refund failed for user={user_id}: {e}")
