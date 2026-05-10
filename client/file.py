"""Java 后端文件服务客户端 — 上传、下载、列表、搜索、回收站操作。

文件由 Java 后端统一存储（本地磁盘 / 阿里云 OSS），AI 模块通过此客户端
下载文件进行 RAG 处理，或上传生成结果。

接口前缀说明:
  /api/file/*          — 面向用户的文件接口（下载、列表、搜索、回收站）
  /api/internal/file/* — AI 模块内部接口（上传生成结果 / 上传素材）
"""

from pathlib import Path

from client.http import post, get, download_file as _download, delete as _del, put
from config import settings

PUBLIC = f"{settings.java_api_prefix}/file"
INTERNAL = f"{settings.java_api_prefix}/internal/file"


async def upload(file_path: str, user_id: int, file_type: int = 5) -> dict:
    """上传文件到 Java 后端存储（内部接口）。

    file_type: 1-PPT 2-Word 3-PDF 4-图片 5-其他
    """
    from client.http import upload_file as _upload_file
    return await _upload_file(f"{INTERNAL}/upload", file_path, {
        "userId": user_id,
        "fileType": file_type,
    })


async def download(file_id: int, save_path: str = "") -> bytes:
    """下载文件，返回原始字节。传 save_path 则同步写入磁盘。"""
    return await _download(f"{PUBLIC}/{file_id}/download", save_path=save_path)


async def list_files(
    user_id: int,
    file_type: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """分页查询用户文件列表，可按文件类型筛选。"""
    params = {"userId": user_id, "page": page, "pageSize": page_size}
    if file_type is not None:
        params["fileType"] = file_type
    return await get(f"{PUBLIC}/list", params)


async def search_files(
    user_id: int,
    keyword: str,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """按文件名模糊搜索。"""
    return await get(f"{PUBLIC}/search", {
        "userId": user_id,
        "keyword": keyword,
        "page": page,
        "pageSize": page_size,
    })


async def delete(file_id: int) -> dict:
    """软删除文件，移入回收站（30 天自动清理）。"""
    return await _del(f"{PUBLIC}/{file_id}")


async def restore(file_id: int) -> dict:
    """从回收站恢复文件。"""
    return await put(f"{PUBLIC}/{file_id}/restore")


async def permanent_delete(file_id: int) -> dict:
    """永久删除文件（不可恢复）。"""
    return await _del(f"{PUBLIC}/{file_id}/permanent")


async def recycle_list(
    user_id: int,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """查询回收站文件列表。"""
    return await get(f"{PUBLIC}/recycle", {
        "userId": user_id,
        "page": page,
        "pageSize": page_size,
    })
