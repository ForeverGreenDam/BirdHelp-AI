"""Java 后端文件服务客户端 — 上传、下载、删除。

文件由 Java 后端统一存储（本地磁盘 / 阿里云 OSS），AI 模块通过此客户端
下载文件进行 RAG 处理，或上传生成结果。

所有接口均为内部接口（/api/internal/file/*），需 RSA-SHA256 签名。
"""

from client.http import download_file as _download, delete as _del
from config import settings

INTERNAL = f"{settings.java_api_prefix}/internal/file"


async def upload(
    file_path: str,
    user_id: int,
    project_id: int,
    file_name: str,
    version_of: int | None = None,
) -> dict:
    """上传文件到 Java 后端存储（内部接口）。

    对应 POST /api/internal/file/upload，multipart/form-data。

    Args:
        file_path: 本地文件路径
        user_id: 用户 ID
        project_id: 项目 ID
        file_name: 文件名（含扩展名）
        version_of: 上一版本文件 ID（修改链，可选）。修改版上传时传入此字段，
                    Java 据此建立 file_record.version_of 版本链
    """
    from client.http import upload_file as _upload_file
    fields: dict[str, str] = {
        "userId": str(user_id),
        "projectId": str(project_id),
        "fileName": file_name,
    }
    if version_of is not None:
        fields["versionOf"] = str(version_of)
    return await _upload_file(f"{INTERNAL}/upload", file_path, fields)


async def download(file_id: int, save_path: str = "") -> bytes:
    """下载文件（内部接口），返回原始字节。传 save_path 则同步写入磁盘。

    对应 GET /api/internal/file/{id}/download。
    """
    return await _download(f"{INTERNAL}/{file_id}/download", save_path=save_path)

