"""公共设计系统 — 颜色主题和字体定义，PPT/Word/PDF 三种格式共用。

颜色以十六进制字符串存储，各格式的生成器自行转换为对应的 RGBColor 类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    # 图表/表格专用色（Phase 2 新增）
    chart_colors: list[str] = field(default_factory=lambda: ["#1A3C6E", "#556B8D", "#C0392B", "#27AE60", "#E67E22", "#8E44AD"])
    table_header_fill: str = ""   # 表格表头填充色（空则用 primary）
    table_body_fill: str = "#FFFFFF"
    table_alt_fill: str = "#F5F7FA"  # 表格交替行色
    table_border: str = "#D0D5DD"    # 表格边框色

    def hex_to_tuple(self, color_name: str) -> tuple[int, int, int]:
        """将指定颜色名的 hex 转为 (R, G, B) 元组。"""
        h = getattr(self, color_name, "000000").lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    def get_chart_colors(self) -> list[str]:
        """获取图表数据系列的颜色序列。"""
        return self.chart_colors if self.chart_colors else [self.primary, self.secondary, self.accent, self.light, self.dark, self.text_body]

    def get_table_header_fill(self) -> str:
        """获取表格表头填充色。"""
        return self.table_header_fill if self.table_header_fill else self.primary


# ── 6 套预设主题 ──

THEMES: dict[str, ColorPalette] = {
    "academic": ColorPalette(
        name="academic",
        primary="#1A3C6E", secondary="#556B8D", accent="#C0392B",
        light="#F0F2F5", dark="#0D1F3B", background="#FAFBFC",
        text_primary="#1A3C6E", text_secondary="#7F8CA0", text_body="#2D2D2D",
        title_font="WenQuanYi Micro Hei", body_font="AR PL UMing CN",
        heading_font="WenQuanYi Micro Hei",
        chart_colors=["#1A3C6E", "#556B8D", "#C0392B", "#2980B9", "#E67E22", "#8E44AD"],
        table_header_fill="#1A3C6E", table_alt_fill="#F5F7FA", table_border="#D5DCE5",
    ),
    "business": ColorPalette(
        name="business",
        primary="#1B3A5C", secondary="#5A728C", accent="#006EB6",
        light="#E8ECF0", dark="#0F243B", background="#FDFEFF",
        text_primary="#1B3A5C", text_secondary="#8C9BAD", text_body="#333333",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
        chart_colors=["#1B3A5C", "#5A728C", "#006EB6", "#27AE60", "#E67E22", "#8E44AD"],
        table_header_fill="#1B3A5C", table_alt_fill="#F5F7FA", table_border="#D5DCE5",
    ),
    "creative": ColorPalette(
        name="creative",
        primary="#E04A36", secondary="#E87A3C", accent="#F39C12",
        light="#FEF6F0", dark="#3C1A12", background="#FFFBF8",
        text_primary="#E04A36", text_secondary="#C07A6C", text_body="#3C3C3C",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
        chart_colors=["#E04A36", "#E87A3C", "#F39C12", "#27AE60", "#2980B9", "#8E44AD"],
        table_header_fill="#E04A36", table_alt_fill="#FFF5F3", table_border="#F0D0C8",
    ),
    "minimal": ColorPalette(
        name="minimal",
        primary="#2D2D2D", secondary="#757575", accent="#4A90D9",
        light="#F5F5F5", dark="#1A1A1A", background="#FFFFFF",
        text_primary="#2D2D2D", text_secondary="#999999", text_body="#4D4D4D",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
        chart_colors=["#2D2D2D", "#757575", "#4A90D9", "#27AE60", "#9B59B6", "#E67E22"],
        table_header_fill="#2D2D2D", table_alt_fill="#F5F5F5", table_border="#E0E0E0",
    ),
    "tech": ColorPalette(
        name="tech",
        primary="#0D47A1", secondary="#156BC1", accent="#00E676",
        light="#E3F2FD", dark="#0A2E6E", background="#F8FCFF",
        text_primary="#0D47A1", text_secondary="#547FB5", text_body="#263B5C",
        title_font="WenQuanYi Micro Hei", body_font="WenQuanYi Micro Hei",
        heading_font="WenQuanYi Micro Hei",
        chart_colors=["#0D47A1", "#156BC1", "#00E676", "#FF6D00", "#9C27B0", "#00BCD4"],
        table_header_fill="#0D47A1", table_alt_fill="#F0F5FC", table_border="#CED8E8",
    ),
    "warm": ColorPalette(
        name="warm",
        primary="#8B451E", secondary="#B07D5C", accent="#E88D2A",
        light="#FEF8F0", dark="#4A2510", background="#FFFBF5",
        text_primary="#8B451E", text_secondary="#B08E78", text_body="#4A3A2E",
        title_font="WenQuanYi Micro Hei", body_font="AR PL UMing CN",
        heading_font="WenQuanYi Micro Hei",
        chart_colors=["#8B451E", "#B07D5C", "#E88D2A", "#27AE60", "#2980B9", "#8E44AD"],
        table_header_fill="#8B451E", table_alt_fill="#FFF8F2", table_border="#E0D0C0",
    ),
}


def get_palette(style_name: str) -> ColorPalette:
    """根据风格名获取调色板，未知风格回退到 academic。"""
    return THEMES.get(style_name, THEMES["academic"])
