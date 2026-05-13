"""RAG 素材管理接口 — 上传、删除、重建索引、清理向量。

POST   /ai/material/{id}/reindex      — 回收站恢复后重建向量索引
POST   /ai/material/{id}/vector-purge — 强制删除后清理向量残留
"""
from fastapi import APIRouter, UploadFile, File, Form, Query
from loguru import logger

from core.schemas import ApiResponse
from core.exceptions import MaterialFormatError
from rag.ingestion import ingest_from_java, SUPPORTED_EXTENSIONS
from rag.vector_store import delete_by_material
from client.file import upload as java_upload, delete as java_delete
from utils.file import temp_file_path, ensure_temp_dir

router = APIRouter(prefix="/ai/material", tags=["material"])



@router.post("/upload")
async def upload_material(
    user_id: int = Form(..., description="用户 ID"),
    project_id: str = Form(..., description="项目 ID，用于隔离知识库"),
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
        java_result = await java_upload(str(tmp_path), user_id, int(project_id), file.filename)
        java_file_id = java_result.get("data", {}).get("id") or java_result.get("data")
        if isinstance(java_file_id, dict):
            java_file_id = java_file_id.get("id")
        if not java_file_id:
            raise RuntimeError(f"Java 文件上传失败: {java_result}")

        # 3. RAG 摄取（下载 → 解析 → 切分 → 嵌入 → 入库）
        ingest_result = await ingest_from_java(
            user_id=str(user_id),
            project_id=project_id,
            java_file_id=int(java_file_id),
            file_name=file.filename,
        )

        return ApiResponse(code=0, message="success", data=ingest_result)

    except Exception:
        # 清理已上传到 Java 的文件（尽力）
        if 'java_file_id' in dir():
            try:
                await java_delete(int(java_file_id), user_id)
            except Exception:
                pass
        raise
    finally:
        if tmp_path.exists():
            tmp_path.unlink()



@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    user_id: int = Query(..., description="用户 ID"),
    project_id: str = Query(..., description="项目 ID，用于定位对应知识库"),
):
    """删除素材：Java 后端软删除（移入回收站）+ Redis 向量清理。"""
    # 1. Java 软删除
    await java_delete(material_id, user_id)

    # 2. 清理向量数据
    removed = delete_by_material(str(user_id), project_id, material_id)
    logger.info(f"Deleted material #{material_id} from project {project_id}: removed {removed} vectors")

    return ApiResponse(code=0, message="success", data={"deleted_chunks": removed})


@router.post("/{material_id}/reindex")
async def reindex_material(
    material_id: int,
    user_id: int = Query(..., description="用户 ID"),
    project_id: str = Query(..., description="项目 ID，用于定位对应知识库"),
    file_name: str = Query(..., description="原始文件名（含扩展名），用于选 Loader"),
):
    """回收站恢复后重建向量索引。

    Java 端在用户从回收站恢复文件后调用此接口。
    从 Java 下载文件 → 解析 → 切分 → 嵌入 → 入库，跳过上传步骤。
    """
    ingest_result = await ingest_from_java(
        user_id=str(user_id),
        project_id=project_id,
        java_file_id=material_id,
        file_name=file_name,
    )
    logger.info(f"Reindexed material #{material_id} in project {project_id}: "
                f"{ingest_result['chunk_count']} chunks")
    return ApiResponse(code=0, message="success", data=ingest_result)


@router.post("/{material_id}/vector-purge")
async def purge_material_vectors(
    material_id: int,
    user_id: int = Query(..., description="用户 ID"),
    project_id: str = Query(..., description="项目 ID，用于定位对应知识库"),
):
    """强制删除后清理 Redis 中的残留向量。

    Java 端在用户永久删除文件（跳过回收站）/ 回收站 30 天自动清理后调用此接口。
    仅清理向量数据，不操作 Java 文件。
    """
    removed = delete_by_material(str(user_id), project_id, material_id)
    logger.info(f"Purged vectors for material #{material_id} in project {project_id}: "
                f"removed {removed} vectors")
    return ApiResponse(code=0, message="success", data={"deleted_chunks": removed})
