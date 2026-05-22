"""公共设计系统 — 颜色主题和字体定义，PPT/Word/PDF 三种格式共用。

颜色以十六进制字符串存储，各格式的生成器自行转换为对应的 RGBColor 类型。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ColorPalette:
    """一套语义颜色定义。所有颜色以十六进制字符串存储，与具体渲染库解耦。"""

    name: str
    # 核心色板
    primary: str        # 主色（标题、强调）
    secondary: str      # 辅色（装饰元素）
    accent: str         # 强调色（关键数据、CTA）
    light: str          # 浅色（背景区块、卡片底色）
    dark: str           # 深色（页脚、分隔线）
    background: str     # 页面背景色
    # 文字色
    text_primary: str        # 主文字（标题）
    text_secondary: str      # 次文字（副标题、页码、标注）
    text_body: str           # 正文（段落）
    # 字体
    title_font: str          # 标题字体名
    body_font: str           # 正文字体名
    heading_font: str        # 章节标题字体名

    def hex_to_tuple(self, color_name: str) -> tuple[int, int, int]:
        """将指定颜色名的 hex 转为 (R, G, B) 元组。"""
        h = getattr(self, color_name, "000000").lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ── 6 套预设主题 ──

THEMES: dict[str, ColorPalette] = {
    "academic": ColorPalette(
        name="academic",
        primary="#1A3C6E", secondary="#556B8D", accent="#C0392B",
        light="#F0F2F5", dark="#0D1F3B", background="#FAFBFC",
        text_primary="#1A3C6E", text_secondary="#7F8CA0", text_body="#2D2D2D",
        title_font="WenQuanYi Micro Hei", body_font="AR PL UMing CN",
        heading_font="WenQuanYi Micro Hei",
    ),
    "business": ColorPalette(
        name="business",
        primary="#1B3A5C", secondary="#5A728C", accent="#006EB6",
        light="#E8ECF0", dark="#0F243B", background="#FDFEFF",
        text_primary="#1B3A5C", text_secondary="#8C9BAD", text_body="#333333",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
    ),
    "creative": ColorPalette(
        name="creative",
        primary="#E04A36", secondary="#E87A3C", accent="#F39C12",
        light="#FEF6F0", dark="#3C1A12", background="#FFFBF8",
        text_primary="#E04A36", text_secondary="#C07A6C", text_body="#3C3C3C",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
    ),
    "minimal": ColorPalette(
        name="minimal",
        primary="#2D2D2D", secondary="#757575", accent="#4A90D9",
        light="#F5F5F5", dark="#1A1A1A", background="#FFFFFF",
        text_primary="#2D2D2D", text_secondary="#999999", text_body="#4D4D4D",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
    ),
    "tech": ColorPalette(
        name="tech",
        primary="#0D47A1", secondary="#156BC1", accent="#00E676",
        light="#E3F2FD", dark="#0A2E6E", background="#F8FCFF",
        text_primary="#0D47A1", text_secondary="#547FB5", text_body="#263B5C",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
    ),
    "warm": ColorPalette(
        name="warm",
        primary="#8B451E", secondary="#B07D5C", accent="#E88D2A",
        light="#FEF8F0", dark="#4A2510", background="#FFFBF5",
        text_primary="#8B451E", text_secondary="#B08E78", text_body="#4A3A2E",
        title_font="WenQuanYi Micro Hei", body_font="AR PL UMing CN",
        heading_font="WenQuanYi Micro Hei",
    ),
}


def get_palette(style_name: str) -> ColorPalette:
    """根据风格名获取调色板，未知风格回退到 academic。"""
    return THEMES.get(style_name, THEMES["academic"])
