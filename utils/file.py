"""临时文件工具 — 创建、命名、清理临时目录下的文件。"""

import os
import time as _time
import uuid
from pathlib import Path

from config import settings


def ensure_temp_dir() -> Path:
    """确保临时目录存在，惰性创建。"""
    p = Path(settings.temp_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def temp_file_path(extension: str = "") -> Path:
    """生成唯一的临时文件路径（不创建文件本身），调用方负责写入和清理。"""
    name = uuid.uuid4().hex
    if extension:
        name = f"{name}.{extension.lstrip('.')}"
    return ensure_temp_dir() / name


def cleanup_old_files(max_age_seconds: int = 3600) -> int:
    """清理超过指定秒数的旧临时文件，返回清理数量。"""
    now = _time.time()
    count = 0
    for f in ensure_temp_dir().iterdir():
        if f.is_file() and (now - f.stat().st_mtime) > max_age_seconds:
            f.unlink()
            count += 1
    return count
