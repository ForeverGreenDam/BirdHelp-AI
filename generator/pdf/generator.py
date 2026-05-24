"""PDF 文件生成器 — DocxBuilder 构建 .docx → LibreOffice 无头转换为 .pdf。

与 Word Generator 共享同一套 DocxBuilder 渲染逻辑。
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

from loguru import logger

from core.exceptions import FileGenerationError
from generator.base import BaseGenerator, inject_image_paths
from generator._design import get_palette
from generator._docx_builder import DocxBuilder
from utils.file import temp_file_path, ensure_temp_dir


class PdfGenerator(BaseGenerator):
    """PDF 生成器 — LLM 输出 → DocxBuilder → .docx → LibreOffice → .pdf。"""

    output_extension = ".pdf"

    def generate(
        self,
        content: dict[str, Any],
        output_path: Path,
        images_map: dict[str, list[str]] | None = None,
    ) -> Path:
        parsed = self._parse_content(content)
        style_name = parsed.get("style", "academic")
        palette = get_palette(style_name)
        enable_images = images_map is not None and len(images_map) > 0

        if enable_images:
            inject_image_paths(parsed.get("sections", []), images_map)

        # 1. 构建 .docx（与 Word 共用 DocxBuilder）
        docx_path = temp_file_path(".docx")
        builder = DocxBuilder(palette, enable_images=enable_images, enable_charts=True)
        doc = builder.build_document(parsed)

        docx_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(docx_path))
        logger.info(f"DOCX built for PDF: {docx_path}")

        # 2. LibreOffice 转换
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = self._convert_to_pdf(docx_path, output_dir)

        if pdf_path:
            if pdf_path != output_path:
                shutil.move(str(pdf_path), str(output_path))
            logger.info(f"PDF generated: {output_path}, style={style_name}")
            if docx_path.exists():
                docx_path.unlink()
            return output_path
        else:
            if docx_path.exists():
                docx_path.unlink()
            raise FileGenerationError(
                "LibreOffice 转换 PDF 失败，请检查服务端 LibreOffice 是否正常安装"
            )

    @staticmethod
    def _convert_to_pdf(docx_path: Path, output_dir: Path) -> Path | None:
        """使用 LibreOffice 将 .docx 转换为 .pdf。"""
        try:
            result = subprocess.run(
                ["libreoffice", "--headless", "--convert-to", "pdf",
                 "--outdir", str(output_dir), str(docx_path)],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.error(f"LibreOffice conversion failed: {result.stderr}")
                return None
            pdf_path = output_dir / docx_path.with_suffix(".pdf").name
            return pdf_path if pdf_path.exists() else None
        except FileNotFoundError:
            logger.warning("LibreOffice not found on system")
            return None
        except Exception as exc:
            logger.error(f"LibreOffice conversion error: {exc}")
            return None
