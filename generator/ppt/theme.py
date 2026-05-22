"""PPT 颜色主题 — 从公共设计模块导入，提供 PPT 专用的 RGBColor 封装。"""

from dataclasses import dataclass

from pptx.dml.color import RGBColor

from generator._design import ColorPalette, THEMES, get_palette  # noqa: F401 (re-export)


@dataclass
class ColorTheme:
    """PPT 专用的颜色主题封装，将 hex 转为 pptx RGBColor。"""

    name: str
    primary: RGBColor
    secondary: RGBColor
    accent: RGBColor
    light: RGBColor
    dark: RGBColor
    background: RGBColor
    text_primary: RGBColor
    text_secondary: RGBColor
    text_body: RGBColor
    title_font: str
    body_font: str

    @property
    def accent_hex(self) -> str:
        return f"{self.accent[0]:02X}{self.accent[1]:02X}{self.accent[2]:02X}"

    @classmethod
    def from_palette(cls, palette: ColorPalette) -> "ColorTheme":
        """从公共调色板创建 PPT 专用的 ColorTheme。"""
        def rgb(h: str) -> RGBColor:
            h = h.lstrip("#")
            return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        return cls(
            name=palette.name,
            primary=rgb(palette.primary), secondary=rgb(palette.secondary),
            accent=rgb(palette.accent), light=rgb(palette.light),
            dark=rgb(palette.dark), background=rgb(palette.background),
            text_primary=rgb(palette.text_primary), text_secondary=rgb(palette.text_secondary),
            text_body=rgb(palette.text_body),
            title_font=palette.title_font, body_font=palette.body_font,
        )


def get_theme(style_name: str) -> ColorTheme:
    """根据风格名获取 PPT 专用 ColorTheme。"""
    return ColorTheme.from_palette(get_palette(style_name))
