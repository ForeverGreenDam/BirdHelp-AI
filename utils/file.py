import os
import tempfile
import uuid
from pathlib import Path

from config import settings


def ensure_temp_dir() -> Path:
    p = Path(settings.temp_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def temp_file_path(extension: str = "") -> Path:
    """返回一个临时文件路径，调用方负责写入和清理。"""
    name = uuid.uuid4().hex
    if extension:
        name = f"{name}.{extension.lstrip('.')}"
    return ensure_temp_dir() / name


def cleanup_old_files(max_age_seconds: int = 3600) -> int:
    """清理超过指定时间的临时文件，返回清理数量。"""
    import time
    now = time.time()
    count = 0
    for f in ensure_temp_dir().iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
            f.unlink()
            count += 1
    return count
