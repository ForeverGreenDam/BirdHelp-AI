from client.http import upload_file as _upload_file
from config import settings

PREFIX = f"{settings.java_api_prefix}/internal"


async def upload(file_path: str, user_id: int, file_type: str = "generated") -> dict:
    """上传生成结果文件到 Java 后端。

    注意：MD_CALLER.md 尚未收录此接口，该接口的路径与签名方式可能需调整。
    """
    return await _upload_file(f"{PREFIX}/file/upload", file_path, {
        "userId": user_id,
        "fileType": file_type,
    })
