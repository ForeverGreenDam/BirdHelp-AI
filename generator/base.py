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


def inject_image_paths(sections: list[dict],
                       images_map: dict[str, list[str]]) -> None:
    """将下载好的图片路径按顺序注入到各 section 的 images 中。"""
    flat_images: list[str] = []
    for key in sorted(images_map.keys()):
        flat_images.extend(images_map[key])
    img_idx = 0
    for section in sections:
        for img_spec in section.get("images", []):
            if img_idx < len(flat_images):
                img_spec["_local_path"] = flat_images[img_idx]
                img_idx += 1
