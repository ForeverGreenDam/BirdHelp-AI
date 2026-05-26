"""布局渲染器包 — 每种 LayoutType 对应一个模块，由 Generator 按需分发。

渲染器接口: render_<type>(slide, data, theme, dna, images) -> None
所有模块在 _RENDERERS 中注册，Generator 通过 dispatch() 调用。

Phase 3 新增: chart / table / big_number / timeline 独立渲染器
"""

from generator.ppt.layouts.cover import render_cover
from generator.ppt.layouts.section_header import render_section_header
from generator.ppt.layouts.text_only import render_text_only
from generator.ppt.layouts.text_image import render_text_image
from generator.ppt.layouts.two_column import render_two_column
from generator.ppt.layouts.grid_cards import render_grid_cards
from generator.ppt.layouts.summary import render_summary
from generator.ppt.layouts.chart import render_chart
from generator.ppt.layouts.table import render_table
from generator.ppt.layouts.big_number import render_big_number
from generator.ppt.layouts.timeline import render_timeline
from generator.ppt.layout import LayoutType


# 布局类型 -> 渲染函数 映射
_RENDERERS = {
    LayoutType.COVER: render_cover,
    LayoutType.SECTION_HEADER: render_section_header,
    LayoutType.TEXT_ONLY: render_text_only,
    LayoutType.TEXT_IMAGE: render_text_image,
    LayoutType.TWO_COLUMN: render_two_column,
    LayoutType.GRID_CARDS: render_grid_cards,
    LayoutType.SUMMARY: render_summary,
    # Phase 2: 数据可视化
    LayoutType.CHART: render_chart,
    LayoutType.TABLE: render_table,
    # Phase 3: 展示型布局
    LayoutType.BIG_NUMBER: render_big_number,
    LayoutType.TIMELINE: render_timeline,
    # 尚未实现独立渲染器的类型，回退到 text_only
    LayoutType.TOC: render_text_only,
    LayoutType.IMAGE_FULL: render_text_only,
    LayoutType.QUOTE: render_text_only,
}


def dispatch_renderer(layout_type_str: str):
    """根据布局类型字符串获取对应的渲染函数，未找到时回退到 text_only。"""
    try:
        lt = LayoutType(layout_type_str)
    except ValueError:
        lt = LayoutType.TEXT_ONLY
    return _RENDERERS.get(lt, render_text_only)
