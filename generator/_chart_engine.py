"""图表引擎 — 基于 matplotlib 将 chart 规格渲染为 PNG 图片。

支持: bar / line / pie / horizontal_bar / radar
自动应用 ColorPalette 配色，输出高 DPI PNG 供 Word/PDF 嵌入。
"""

from __future__ import annotations

from pathlib import Path

from generator._design import ColorPalette

# matplotlib 是可选依赖，运行时存在即用
try:
    import matplotlib
    matplotlib.use("Agg")  # 无头模式，不弹窗
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False


# 中文字体尝试列表（按优先级）
_CN_FONT_CANDIDATES = [
    "WenQuanYi Micro Hei", "SimHei", "Microsoft YaHei",
    "Noto Sans CJK SC", "AR PL UMing CN", "DejaVu Sans",
]


def _setup_chinese_font() -> None:
    """配置 matplotlib 中文字体。"""
    if not _HAS_MPL:
        return
    import matplotlib.font_manager as fm
    available = {f.name for f in fm.fontManager.ttflist}
    for font_name in _CN_FONT_CANDIDATES:
        if font_name in available:
            plt.rcParams["font.sans-serif"] = [font_name, "DejaVu Sans"]
            break
    else:
        plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def render_chart(chart_spec: dict, output_path: Path, palette: ColorPalette) -> Path | None:
    """根据 chart 规格渲染一张 PNG 图表。

    Args:
        chart_spec: LLM 输出的图表规格，含 type/title/data/width/caption
        output_path: 输出 PNG 路径
        palette: 颜色调色板

    Returns:
        输出路径，不支持/失败时返回 None
    """
    if not _HAS_MPL:
        return None

    chart_type = chart_spec.get("type", "bar")
    renderer = _CHART_RENDERERS.get(chart_type)
    if renderer is None:
        return None

    _setup_chinese_font()

    title = chart_spec.get("title", "")
    data = chart_spec.get("data", {})
    labels = data.get("labels", [])
    datasets = data.get("datasets", [])

    if not labels or not datasets:
        return None

    # 配色：主题色系
    colors = [
        palette.primary, palette.accent, palette.secondary,
        palette.text_secondary, palette.dark, palette.light,
    ]

    # 图表尺寸
    width_map = {"full": (14, 5), "half": (7, 4.5), "quarter": (4, 3.5)}
    figsize = width_map.get(chart_spec.get("width", "full"), (14, 5))

    try:
        renderer(labels, datasets, title, colors, figsize, output_path, chart_spec)
        return output_path
    except Exception:
        return None


def _render_bar(labels, datasets, title, colors, figsize, output_path, spec) -> None:
    """柱状图。"""
    fig, ax = plt.subplots(figsize=figsize)
    n_groups = len(labels)
    n_bars = len(datasets)
    bar_w = 0.8 / n_bars
    x = range(n_groups)

    for i, ds in enumerate(datasets):
        values = ds.get("values", [])
        color = colors[i % len(colors)]
        offset = (i - (n_bars - 1) / 2) * bar_w
        ax.bar([xi + offset for xi in x], values, bar_w * 0.85,
               label=ds.get("label", ""), color=color, edgecolor="white", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.legend(fontsize=9, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _render_line(labels, datasets, title, colors, figsize, output_path, spec) -> None:
    """折线图。"""
    fig, ax = plt.subplots(figsize=figsize)
    for i, ds in enumerate(datasets):
        values = ds.get("values", [])
        color = colors[i % len(colors)]
        ax.plot(labels, values, marker="o", linewidth=2, markersize=5,
                label=ds.get("label", ""), color=color)

    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.legend(fontsize=9, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _render_pie(labels, datasets, title, colors, figsize, output_path, spec) -> None:
    """饼图。"""
    fig, ax = plt.subplots(figsize=figsize)
    ds = datasets[0]
    values = ds.get("values", [])
    pie_colors = [colors[i % len(colors)] for i in range(len(values))]

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=pie_colors, startangle=90, pctdistance=0.6,
    )
    for t in autotexts:
        t.set_fontsize(8)
    for t in texts:
        t.set_fontsize(9)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _render_hbar(labels, datasets, title, colors, figsize, output_path, spec) -> None:
    """横向柱状图（适合长标签）。"""
    fig, ax = plt.subplots(figsize=figsize)
    n_groups = len(labels)
    n_bars = len(datasets)
    bar_h = 0.8 / n_bars
    y = range(n_groups)

    for i, ds in enumerate(datasets):
        values = ds.get("values", [])
        color = colors[i % len(colors)]
        offset = (i - (n_bars - 1) / 2) * bar_h
        ax.barh([yi + offset for yi in y], values, bar_h * 0.85,
                label=ds.get("label", ""), color=color, edgecolor="white", linewidth=0.5)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.legend(fontsize=9, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _render_radar(labels, datasets, title, colors, figsize, output_path, spec) -> None:
    """雷达图。"""
    import numpy as np
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=figsize, subplot_kw={"projection": "polar"})
    for i, ds in enumerate(datasets):
        values = ds.get("values", [])
        values_plot = values + values[:1]
        color = colors[i % len(colors)]
        ax.fill(angles, values_plot, alpha=0.1, color=color)
        ax.plot(angles, values_plot, "o-", linewidth=2, markersize=5,
                label=ds.get("label", ""), color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=20)
    ax.legend(fontsize=9, frameon=False, loc="upper right", bbox_to_anchor=(1.3, 1.0))
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


_CHART_RENDERERS = {
    "bar": _render_bar,
    "line": _render_line,
    "pie": _render_pie,
    "horizontal_bar": _render_hbar,
    "radar": _render_radar,
}
