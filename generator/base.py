import json
from pathlib import Path
from typing import Any


class BaseGenerator:
    """文件生成器基类。"""

    output_extension: str = ""

    def generate(self, content: dict[str, Any], output_path: Path) -> Path:
        raise NotImplementedError

    @staticmethod
    def _parse_content(raw: str | dict) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)
