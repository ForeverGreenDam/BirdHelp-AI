"""颜色主题系统 — 定义可复用的调色板和字体对，统一所有页面的视觉风格。

每套主题包含语义色（主色/辅色/强调色等）和字体指定，
Generator 和各 Layout 渲染器通过主题对象获取颜色和字体，
避免各处硬编码 RGB 值。
"""

from dataclasses import dataclass, field
from pptx.dml.color import RGBColor


@dataclass
class ColorTheme:
    """一套完整的语义颜色定义，覆盖幻灯片的全部视觉元素。"""

    name: str
    # 核心色板
    primary: RGBColor        # 主色：标题、重点形状
    secondary: RGBColor      # 辅色：装饰色块、次要强调
    accent: RGBColor         # 强调色：关键数据、CTA 按钮
    light: RGBColor          # 浅色：背景区块、卡片底色
    dark: RGBColor           # 深色：页脚、分隔线
    background: RGBColor     # 页面背景色
    # 文字色
    text_primary: RGBColor   # 主文字（标题）
    text_secondary: RGBColor # 次文字（副标题、页码、标注）
    text_body: RGBColor      # 正文（段落、要点）
    # 字体
    title_font: str          # 标题字体名
    body_font: str           # 正文字体名

    @property
    def accent_hex(self) -> str:
        """强调色的十六进制字符串，用于渐变等场景。"""
        return f"{self.accent[0]:02X}{self.accent[1]:02X}{self.accent[2]:02X}"


# ── 6 套预设主题 ──

THEMES: dict[str, ColorTheme] = {
    "academic": ColorTheme(
        name="academic",
        primary=RGBColor(0x1A, 0x3C, 0x6E),
        secondary=RGBColor(0x55, 0x6B, 0x8D),
        accent=RGBColor(0xC0, 0x39, 0x2B),
        light=RGBColor(0xF0, 0xF2, 0xF5),
        dark=RGBColor(0x0D, 0x1F, 0x3B),
        background=RGBColor(0xFA, 0xFB, 0xFC),
        text_primary=RGBColor(0x1A, 0x3C, 0x6E),
        text_secondary=RGBColor(0x7F, 0x8C, 0xA0),
        text_body=RGBColor(0x2D, 0x2D, 0x2D),
        title_font="WenQuanYi Micro Hei",
        body_font="AR PL UMing CN",
    ),
    "business": ColorTheme(
        name="business",
        primary=RGBColor(0x1B, 0x3A, 0x5C),
        secondary=RGBColor(0x5A, 0x72, 0x8C),
        accent=RGBColor(0x00, 0x6E, 0xB6),
        light=RGBColor(0xE8, 0xEC, 0xF0),
        dark=RGBColor(0x0F, 0x24, 0x3B),
        background=RGBColor(0xFD, 0xFE, 0xFF),
        text_primary=RGBColor(0x1B, 0x3A, 0x5C),
        text_secondary=RGBColor(0x8C, 0x9B, 0xAD),
        text_body=RGBColor(0x33, 0x33, 0x33),
        title_font="WenQuanYi Micro Hei",
        body_font="WenQuanYi Micro Hei",
    ),
    "creative": ColorTheme(
        name="creative",
        primary=RGBColor(0xE0, 0x4A, 0x36),
        secondary=RGBColor(0xE8, 0x7A, 0x3C),
        accent=RGBColor(0xF3, 0x9C, 0x12),
        light=RGBColor(0xFE, 0xF6, 0xF0),
        dark=RGBColor(0x3C, 0x1A, 0x12),
        background=RGBColor(0xFF, 0xFB, 0xF8),
        text_primary=RGBColor(0xE0, 0x4A, 0x36),
        text_secondary=RGBColor(0xC0, 0x7A, 0x6C),
        text_body=RGBColor(0x3C, 0x3C, 0x3C),
        title_font="WenQuanYi Micro Hei",
        body_font="WenQuanYi Micro Hei",
    ),
    "minimal": ColorTheme(
        name="minimal",
        primary=RGBColor(0x2D, 0x2D, 0x2D),
        secondary=RGBColor(0x75, 0x75, 0x75),
        accent=RGBColor(0x4A, 0x90, 0xD9),
        light=RGBColor(0xF5, 0xF5, 0xF5),
        dark=RGBColor(0x1A, 0x1A, 0x1A),
        background=RGBColor(0xFF, 0xFF, 0xFF),
        text_primary=RGBColor(0x2D, 0x2D, 0x2D),
        text_secondary=RGBColor(0x99, 0x99, 0x99),
        text_body=RGBColor(0x4D, 0x4D, 0x4D),
        title_font="WenQuanYi Micro Hei",
        body_font="WenQuanYi Micro Hei",
    ),
    "tech": ColorTheme(
        name="tech",
        primary=RGBColor(0x0D, 0x47, 0xA1),
        secondary=RGBColor(0x15, 0x6B, 0xC1),
        accent=RGBColor(0x00, 0xE6, 0x76),
        light=RGBColor(0xE3, 0xF2, 0xFD),
        dark=RGBColor(0x0A, 0x2E, 0x6E),
        background=RGBColor(0xF8, 0xFC, 0xFF),
        text_primary=RGBColor(0x0D, 0x47, 0xA1),
        text_secondary=RGBColor(0x54, 0x7F, 0xB5),
        text_body=RGBColor(0x26, 0x3B, 0x5C),
        title_font="WenQuanYi Micro Hei",
        body_font="WenQuanYi Micro Hei",
    ),
    "warm": ColorTheme(
        name="warm",
        primary=RGBColor(0x8B, 0x45, 0x1E),
        secondary=RGBColor(0xB0, 0x7D, 0x5C),
        accent=RGBColor(0xE8, 0x8D, 0x2A),
        light=RGBColor(0xFE, 0xF8, 0xF0),
        dark=RGBColor(0x4A, 0x25, 0x10),
        background=RGBColor(0xFF, 0xFB, 0xF5),
        text_primary=RGBColor(0x8B, 0x45, 0x1E),
        text_secondary=RGBColor(0xB0, 0x8E, 0x78),
        text_body=RGBColor(0x4A, 0x3A, 0x2E),
        title_font="WenQuanYi Micro Hei",
        body_font="AR PL UMing CN",
    ),
}


def get_theme(style_name: str) -> ColorTheme:
    """根据风格名获取主题，未知风格回退到 academic。"""
    return THEMES.get(style_name, THEMES["academic"])
