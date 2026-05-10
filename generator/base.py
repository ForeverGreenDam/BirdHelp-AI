"""文件生成器抽象基类。

所有 Office 文件生成器（PPT/Word/PDF）继承此类，
统一输出路径和内容解析逻辑。
"""

import json
from pathlib import Path
from typing import Any


class BaseGenerator:
    """文件生成器基类。

    子类需覆写 output_extension 和 generate()。
    """

    output_extension: str = ""

    def generate(self, content: dict[str, Any], output_path: Path) -> Path:
        """根据结构化内容生成文件，返回输出路径。"""
        raise NotImplementedError

    @staticmethod
    def _parse_content(raw: str | dict) -> dict[str, Any]:
        """将 LLM 输出的字符串或字典统一解析为 dict。"""
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)
