"""形状工具包 — 封装 python-pptx 常用形状操作，提供声明式绘图接口。

上层布局渲染器通过本模块的函数描述"画什么"（颜色、位置、尺寸），
无需直接操作 python-pptx 的 XML 级别 API。
所有尺寸参数使用 Inches() 等 EMU 值。
"""

from __future__ import annotations

from typing import Optional

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

from generator.ppt.theme import ColorTheme

# ── 幻灯片尺寸（16:9） ──
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
SAFE_L = Inches(0.8)   # 左边距
SAFE_R = Inches(12.533)  # 右边距 = slide_w - 0.8
SAFE_T = Inches(0.4)   # 上边距
SAFE_B = Inches(7.1)   # 下边距 = slide_h - 0.4


def add_rect(
    slide,
    left, top, width, height,
    fill_color: RGBColor | str,
    border_color: RGBColor | str | None = None,
    border_width: float = 0,
    corner_radius: int = 0,
) -> object:
    """添加矩形色块。corner_radius > 0 时使用圆角矩形。"""
    if corner_radius > 0:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
        )
        # 调整圆角半径（通过 XML 属性）
        try:
            prst_geom = shape._element.find(qn('a:prstGeom'))
            if prst_geom is not None:
                avlst = prst_geom.find(qn('a:avLst'))
                if avlst is not None:
                    gd = avlst.find(qn('a:gd'))
                    if gd is not None:
                        gd.set('fmla', f'val {corner_radius * 12700}')  # EMU: pt * 12700
        except Exception:
            pass
    else:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, left, top, width, height
        )
    # 填充
    shape.fill.solid()
    if isinstance(fill_color, str):
        fill_color = _hex_to_rgb(fill_color)
    shape.fill.fore_color.rgb = fill_color
    # 边框
    if border_width > 0 and border_color:
        shape.line.color.rgb = border_color if isinstance(border_color, RGBColor) else _hex_to_rgb(border_color)
        shape.line.width = Pt(border_width)
    else:
        shape.line.fill.background()
    return shape


def add_circle(
    slide,
    cx: Inches, cy: Inches, radius: Inches,
    fill_color: RGBColor | str,
) -> object:
    """添加圆形装饰元素。"""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.OVAL,
        cx - radius, cy - radius,
        radius * 2, radius * 2,
    )
    shape.fill.solid()
    if isinstance(fill_color, str):
        fill_color = _hex_to_rgb(fill_color)
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    return shape


def add_accent_bar(
    slide,
    left, top, width, height,
    color: RGBColor | str,
) -> object:
    """添加侧边强调条（细长矩形）。"""
    return add_rect(slide, left, top, width, height, color, border_width=0)


def add_line(
    slide,
    x1, y1, x2, y2,
    color: RGBColor | str,
    width: float = 1.5,
) -> object:
    """添加直线。"""
    if isinstance(color, str):
        color = _hex_to_rgb(color)
    connector = slide.shapes.add_connector(1, x1, y1, x2, y2)  # MSO_CONNECTOR.STRAIGHT = 1
    connector.line.color.rgb = color
    connector.line.width = Pt(width)
    return connector


def add_text_box(
    slide,
    left, top, width, height,
    text: str,
    font_name: str,
    font_size: int,
    font_color: RGBColor | str,
    bold: bool = False,
    alignment=PP_ALIGN.LEFT,  # noqa: ANN001 (PP_ALIGN is IntEnum)
    word_wrap: bool = True,
    vertical_anchor=MSO_ANCHOR.TOP,  # noqa: ANN001
) -> object:
    """添加统一样式的文本框，返回 shape 对象以便调用方进一步操作。"""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = word_wrap
    tf.auto_size = None
    # 设置垂直锚定
    try:
        txBox.text_frame._txBody.bodyPr.set('anchor', {
            MSO_ANCHOR.TOP: 't',
            MSO_ANCHOR.MIDDLE: 'ctr',
            MSO_ANCHOR.BOTTOM: 'b',
        }.get(vertical_anchor, 't'))
    except Exception:
        pass
    p = tf.paragraphs[0]
    p.text = text
    p.alignment = alignment
    p.font.name = font_name
    p.font.size = Pt(font_size)
    p.font.bold = bold
    if isinstance(font_color, str):
        font_color = _hex_to_rgb(font_color)
    p.font.color.rgb = font_color
    return txBox


def add_multiline_text_box(
    slide,
    left, top, width, height,
    lines: list[dict],
    theme: ColorTheme,
) -> object:
    """添加多段落文本框，每行可独立设置样式。

    lines 格式: [{"text": "...", "size": 18, "bold": False, "color": theme.text_body, "bullet": True}, ...]
    """
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        prefix = "• " if line.get("bullet", False) else ""
        p.text = f"{prefix}{line['text']}"
        p.alignment = line.get("align", PP_ALIGN.LEFT)
        p.font.name = theme.body_font
        p.font.size = Pt(line.get("size", 18))
        p.font.bold = line.get("bold", False)
        color = line.get("color", theme.text_body)
        if isinstance(color, str):
            color = _hex_to_rgb(color)
        p.font.color.rgb = color
        if line.get("space_after"):
            p.space_after = Pt(line["space_after"])
        if line.get("space_before"):
            p.space_before = Pt(line["space_before"])
    return txBox


def add_image(
    slide,
    left, top, width, height,
    image_path: str,
) -> object:
    """插入图片，自动等比缩放填充指定区域（居中裁剪）。"""
    from PIL import Image  # noqa: PLC0415 (lazy import, only needed here)
    try:
        with Image.open(image_path) as img:
            img_w, img_h = img.size
    except Exception:
        return slide.shapes.add_picture(image_path, left, top, width, height)

    slot_ratio = width / height
    img_ratio = img_w / img_h

    if abs(img_ratio - slot_ratio) < 0.01:
        return slide.shapes.add_picture(image_path, left, top, width, height)

    # 等比缩放后居中裁剪
    from io import BytesIO
    if img_ratio > slot_ratio:
        new_w = int(img_h * slot_ratio)
        offset_x = (img_w - new_w) // 2
        cropped = img.crop((offset_x, 0, offset_x + new_w, img_h))
    else:
        new_h = int(img_w / slot_ratio)
        offset_y = (img_h - new_h) // 2
        cropped = img.crop((0, offset_y, img_w, offset_y + new_h))

    buf = BytesIO()
    cropped.save(buf, format='PNG')
    buf.seek(0)
    return slide.shapes.add_picture(buf, left, top, width, height)


def set_slide_bg(slide, color: RGBColor | str) -> None:
    """设置幻灯片纯色背景。"""
    if isinstance(color, str):
        color = _hex_to_rgb(color)
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_page_number(
    slide,
    index: int,
    total: int,
    theme: ColorTheme,
) -> None:
    """在右下角添加页码 'index / total'。"""
    from pptx.util import Inches
    page_text = f"{index} / {total}"
    add_text_box(
        slide,
        Inches(11.5), Inches(7.0),
        Inches(1.5), Inches(0.4),
        page_text,
        font_name=theme.body_font,
        font_size=10,
        font_color=theme.text_secondary,
        alignment=PP_ALIGN.RIGHT,
    )


def clear_placeholders(slide) -> None:
    """移除幻灯片的所有占位符，避免空占位符导致的兼容性警告。"""
    for ph in list(slide.placeholders):
        sp = ph._element
        sp.getparent().remove(sp)


def _hex_to_rgb(hex_str: str) -> RGBColor:
    """将 '#RRGGBB' 或 'RRGGBB' 格式转为 RGBColor。"""
    h = hex_str.lstrip('#')
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
