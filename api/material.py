"""RAG 素材管理接口 — 上传、列表、删除。

POST /ai/material/upload   — 上传文件并触发 RAG 摄取管道
GET  /ai/material/list     — 查询用户素材列表（代理 Java 后端）
DELETE /ai/material/{id}   — 删除素材（Java 回收站 + ChromaDB 清理）
"""

from fastapi import APIRouter, UploadFile, File, Form, Depends, Query
from loguru import logger

from core.schemas import ApiResponse
from core.exceptions import MaterialFormatError
from rag.ingestion import ingest_from_java, SUPPORTED_EXTENSIONS
from rag.vector_store import delete_by_material
from client.file import upload as java_upload, list_files, delete as java_delete
from utils.file import temp_file_path, ensure_temp_dir

router = APIRouter(prefix="/ai/material", tags=["material"])


def _ext_to_file_type(ext: str) -> int:
    """扩展名 → Java 文件类型编号。"""
    mapping = {
        ".pdf": 3,
        ".docx": 2,
        ".pptx": 1,
        ".txt": 5,
    }
    return mapping.get(ext, 5)


@router.post("/upload")
async def upload_material(
    user_id: int = Form(..., description="用户 ID"),
    file: UploadFile = File(...),
):
    """上传参考素材并触发 RAG 摄取。

    流程: 保存临时文件 → 上传 Java 后端 → 下载 → 解析切分嵌入入库 → 返回统计。
    """
    if not file.filename:
        raise MaterialFormatError("文件名为空")

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise MaterialFormatError(f"不支持的格式: {ext}，支持: {', '.join(SUPPORTED_EXTENSIONS)}")

    # 1. 保存上传文件到临时目录
    ensure_temp_dir()
    tmp_path = temp_file_path(ext)
    content = await file.read()
    tmp_path.write_bytes(content)
    logger.info(f"Received upload: {file.filename} ({len(content)} bytes)")

    try:
        # 2. 上传到 Java 后端存储
        file_type = _ext_to_file_type(ext)
        java_result = await java_upload(str(tmp_path), user_id, file_type=file_type)
        java_file_id = java_result.get("data", {}).get("id") or java_result.get("data")
        if isinstance(java_file_id, dict):
            java_file_id = java_file_id.get("id")
        if not java_file_id:
            raise RuntimeError(f"Java 文件上传失败: {java_result}")

        # 3. RAG 摄取（下载 → 解析 → 切分 → 嵌入 → 入库）
        ingest_result = await ingest_from_java(
            user_id=str(user_id),
            java_file_id=int(java_file_id),
            file_name=file.filename,
        )

        return ApiResponse(code=0, message="success", data=ingest_result)

    except Exception:
        # 清理已上传到 Java 的文件（尽力）
        if 'java_file_id' in dir():
            try:
                await java_delete(int(java_file_id))
            except Exception:
                pass
        raise
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


@router.get("/list")
async def list_materials(
    user_id: int = Query(..., description="用户 ID"),
    file_type: int | None = Query(None, description="文件类型 1-PPT 2-Word 3-PDF 4-图片 5-其他"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """查询用户上传的素材列表，代理 Java 后端文件列表接口。"""
    result = await list_files(user_id, file_type=file_type, page=page, page_size=page_size)
    return ApiResponse(code=0, message="success", data=result.get("data", result))


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    user_id: int = Query(..., description="用户 ID"),
):
    """删除素材：Java 后端软删除（移入回收站）+ ChromaDB 向量清理。"""
    # 1. Java 软删除
    await java_delete(material_id)

    # 2. 清理向量数据
    removed = delete_by_material(str(user_id), material_id)
    logger.info(f"Deleted material #{material_id}: removed {removed} vectors")

    return ApiResponse(code=0, message="success", data={"deleted_chunks": removed})
