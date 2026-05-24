"""Word 文件生成器 — 基于 python-docx + DocxBuilder 将结构化内容构建为 .docx 文件。

支持图表嵌入(matplotlib PNG)、图片插入、增强表格、封面设计、页眉页脚。
"""

from pathlib import Path
from typing import Any

from loguru import logger

from generator.base import BaseGenerator, inject_image_paths
from generator._design import get_palette
from generator._docx_builder import DocxBuilder


class WordGenerator(BaseGenerator):
    """Word 生成器 — LLM 输出 → DocxBuilder → .docx。"""

    output_extension = ".docx"

    def generate(
        self,
        content: dict[str, Any],
        output_path: Path,
        images_map: dict[str, list[str]] | None = None,
    ) -> Path:
        """根据结构化内容生成 Word 文件。

        Args:
            content: LLM 输出的 JSON（含 sections/charts/images/tables）
            output_path: 输出 .docx 文件路径
            images_map: section_key → 本地图片路径列表
        """
        parsed = self._parse_content(content)
        style_name = parsed.get("style", "academic")
        palette = get_palette(style_name)
        enable_images = images_map is not None and len(images_map) > 0

        # 将图片路径回填到 sections 的 images 中
        if enable_images:
            inject_image_paths(parsed.get("sections", []), images_map)

        builder = DocxBuilder(palette, enable_images=enable_images, enable_charts=True)
        doc = builder.build_document(parsed)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(output_path))

        sections_count = len(parsed.get("sections", []))
        logger.info(f"Word generated: {output_path}, {sections_count} sections, "
                    f"style={style_name}")
        return output_path
