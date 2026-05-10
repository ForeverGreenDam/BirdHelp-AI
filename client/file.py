from client.http import upload_file


async def upload(file_path: str, user_id: str, file_type: str = "generated") -> dict:
    """上传生成结果文件到 Java 后端。"""
    return await upload_file("/internal/file/upload", file_path, {
        "user_id": user_id,
        "file_type": file_type,
    })
