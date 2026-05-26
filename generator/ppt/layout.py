"""布局引擎 — 定义页面布局类型枚举和设计 DNA，驱动 Generator 的渲染分支。

设计 DNA 基于 topic + style 的哈希做确定性选择，
保证同一主题多次生成的风格一致。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from generator.ppt.theme import get_theme, ColorTheme


class LayoutType(str, Enum):
    """页面布局类型，LLM 在每页 JSON 中指定此枚举值。

    独立渲染器: cover / section / text_only / text_image / two_column /
    grid_cards / summary / chart / table / big_number / timeline
    """
    COVER = "cover"
    TOC = "toc"
    SECTION_HEADER = "section"
    TEXT_ONLY = "text_only"
    TEXT_IMAGE = "text_image"
    IMAGE_FULL = "image_full"
    TWO_COLUMN = "two_column"
    GRID_CARDS = "grid_cards"
    TIMELINE = "timeline"
    QUOTE = "quote"
    SUMMARY = "summary"
    CHART = "chart"
    TABLE = "table"
    BIG_NUMBER = "big_number"


class VisualStrategy(str, Enum):
    """图片策略 — 控制页面是否必须有图片。"""
    MEDIA_REQUIRED = "MEDIA_REQUIRED"       # 阻塞级：无图则失败
    BASIC_GRAPHICS_ONLY = "BASIC_GRAPHICS_ONLY"  # 纯形状文字
    AUTO = "AUTO"                           # 按需


@dataclass
class DesignDNA:
    """设计 DNA — 由主题哈希确定性派生的视觉参数集合。

    所有布局渲染器接收 DNA 并根据其字段调整渲染细节。
    Phase 3: 新增 info_density 和 profile 引用字段。
    """

    theme_name: str
    theme: ColorTheme
    title_font: str
    body_font: str
    layout_family: int = 0              # 0-2，决定布局变体选哪个
    shape_style: str = "rounded"        # "sharp" | "rounded" | "pill"
    density: str = "balanced"           # "sparse" | "balanced" | "dense"
    decoration_level: str = "moderate"  # "minimal" | "moderate" | "rich"
    cover_variant: int = 0              # 封面变体索引 (0-2)
    section_variant: int = 0            # 章节页变体索引 (0-2)
    # Phase 3 新增
    info_density: str = "balanced"      # "sparse" | "balanced" | "high" | "extreme"
    profile_name: str = ""              # 关联的场景 profile 名

    @property
    def corner_radius(self) -> int:
        """根据 shape_style 返回圆角半径（pt）。"""
        return {"sharp": 0, "rounded": 8, "pill": 20}[self.shape_style]

    @property
    def show_decorations(self) -> bool:
        return self.decoration_level != "minimal"

    @property
    def body_font_size(self) -> int:
        return {"sparse": 16, "balanced": 18, "dense": 14}[self.density]

    @property
    def title_font_size(self) -> int:
        return {"sparse": 36, "balanced": 32, "dense": 28}[self.density]

    @property
    def can_use_charts(self) -> bool:
        """场景是否适合使用图表。"""
        return self.info_density in ("balanced", "high", "extreme")

    @property
    def can_use_tables(self) -> bool:
        """场景是否适合使用表格。"""
        return self.info_density in ("balanced", "high", "extreme")


def create_dna(style_name: str, topic: str = "", layout_family: int | None = None) -> DesignDNA:
    """根据风格名 + 主题创建确定性的 DesignDNA。

    基于 topic + style 的 SHA256 哈希产生确定性的视觉参数，
    同一主题每次生成结果相同，不同主题有所变化。
    Phase 3: 从场景 profile 读取 info_density 等参数。
    """
    from generator.ppt.profiles import get_profile

    theme = get_theme(style_name)
    profile = get_profile(style_name)
    seed = hashlib.sha256(f"{topic}:{style_name}".encode()).hexdigest()
    seed_int = int(seed[:8], 16)

    shape_options = ["sharp", "rounded", "pill"]
    density_options = ["sparse", "balanced", "dense"]
    decoration_options = ["minimal", "moderate", "rich"]

    return DesignDNA(
        theme_name=style_name,
        theme=theme,
        title_font=theme.title_font,
        body_font=theme.body_font,
        layout_family=layout_family if layout_family is not None else seed_int % 3,
        shape_style=shape_options[seed_int % 3],
        density=density_options[(seed_int // 3) % 3],
        decoration_level=decoration_options[(seed_int // 9) % 3],
        cover_variant=seed_int % 3,
        section_variant=(seed_int // 2) % 3,
        info_density=profile.info_density,
        profile_name=profile.name,
    )
