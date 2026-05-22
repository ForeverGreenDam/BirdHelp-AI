"""PPT 渲染测试 — 用假数据验证设计系统、布局渲染器、图片占位、主题和 DNA。

运行方式: python -m tests.test_ppt_complex
输出文件: /tmp/birdhelp/test_ppt_output.pptx
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator.ppt import PptGenerator
from generator.ppt.layout import create_dna, LayoutType
from generator.ppt.theme import THEMES
from generator.ppt.shapes import SLIDE_W, SLIDE_H

# ── 测试数据 ──

TEST_OUTLINE = {
    "title": "人工智能在医疗领域的应用",
    "design_note": "科技蓝绿色调，圆润形状，图文混排展现技术前沿感",
    "style": "tech",
    "slides": [
        {
            "page_number": 1,
            "layout_type": "cover",
            "title": "人工智能在医疗领域的应用",
            "subtitle": "从诊断辅助到药物研发的全面变革",
            "body": ["2026 年度技术趋势报告"],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "gradient",
                "decorations": [
                    {"type": "accent_bar", "position": "left", "color": "accent"},
                    {"type": "circle", "position": "bottom_right", "size": "large"},
                ],
            },
            "image_query": "",
            "notes": "",
        },
        {
            "page_number": 2,
            "layout_type": "text_only",
            "title": "医疗 AI 的市场规模",
            "body": [
                "2026 年全球医疗 AI 市场规模预计突破 450 亿美元",
                "年复合增长率达 44.9%，远超传统医疗 IT 增速",
                "医学影像分析占据 38% 的市场份额，是最大的细分领域",
                "药物发现 AI 正成为增速最快的赛道，年增幅超 60%",
            ],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "solid",
                "decorations": [{"type": "line", "position": "below_title", "color": "accent"}],
            },
            "image_query": "",
            "notes": "数据来源: Grand View Research 2026",
        },
        {
            "page_number": 3,
            "layout_type": "text_image",
            "title": "AI 医学影像诊断流程",
            "body": [
                "影像采集：CT/MRI/X光 多模态数据输入",
                "预处理：去噪、增强、器官分割与配准",
                "特征提取：CNN/Transformer 自动学习病灶特征",
                "辅助诊断：输出热力图 + 良恶性概率 + 结构化报告",
            ],
            "visual_plan": {
                "strategy": "MEDIA_REQUIRED",
                "layout_hint": "text_left_image_right",
                "bg_treatment": "solid",
                "decorations": [{"type": "line", "position": "below_title", "color": "accent"}],
            },
            "image_query": "medical AI diagnostic imaging workflow",
            "image_position": "right",
            "notes": "重点解释特征提取环节的深度学习模型",
        },
        {
            "page_number": 4,
            "layout_type": "grid_cards",
            "title": "四大核心应用场景",
            "body": [
                "医学影像 | AI 辅助 CT/MRI 病灶检测，准确率达 95%+",
                "药物发现 | 深度学习加速分子筛选，研发周期缩短 40%",
                "病理分析 | 数字病理切片 AI 判读，缓解病理医生短缺",
                "健康管理 | 可穿戴数据 + AI 预测，实现个性化慢病管理",
            ],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "solid",
                "decorations": [],
            },
            "image_query": "",
            "notes": "",
        },
        {
            "page_number": 5,
            "layout_type": "section",
            "title": "技术挑战与突破",
            "subtitle": "从实验室到临床的关键一跃",
            "body": [],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "solid",
                "decorations": [{"type": "accent_bar", "position": "left", "color": "accent"}],
            },
            "image_query": "",
        },
        {
            "page_number": 6,
            "layout_type": "two_column",
            "title": "传统诊断 vs AI 辅助诊断",
            "left_label": "传统模式",
            "right_label": "AI 辅助模式",
            "body": [
                "依赖医生个人经验，存在主观偏差",
                "阅片速度受限，高峰期易漏诊",
                "罕见病例识别能力不足",
                "报告撰写耗时，占工作量的 30%",
                "AI 提供第二意见，降低主观偏差",
                "毫秒级推理，日均可处理数千例",
                "海量数据训练，覆盖罕见病特征",
                "自动生成结构化报告，效率提升 3 倍",
            ],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "solid",
                "decorations": [],
            },
            "image_query": "",
        },
        {
            "page_number": 7,
            "layout_type": "text_image",
            "title": "AI 加速药物研发管线",
            "body": [
                "靶点识别：NLP 分析文献 + 知识图谱，发现新靶点",
                "分子生成：生成式 AI 设计候选分子，覆盖更广化学空间",
                "ADMET 预测：提前筛选毒性/代谢风险，减少动物实验",
                "临床试验匹配：AI 精准匹配受试者，加速入组",
            ],
            "visual_plan": {
                "strategy": "MEDIA_REQUIRED",
                "layout_hint": "image_top_text_bottom",
                "bg_treatment": "solid",
                "decorations": [{"type": "line", "position": "below_title", "color": "accent"}],
            },
            "image_query": "AI drug discovery molecular design",
            "image_position": "top",
            "notes": "",
        },
        {
            "page_number": 8,
            "layout_type": "text_only",
            "title": "监管与伦理考量",
            "body": [
                "FDA/CE 认证：AI 医疗器械需通过严格的临床试验验证",
                "数据隐私：患者数据使用需符合 HIPAA/GDPR 合规要求",
                "可解释性：AI 诊断结论应可溯源，避免'黑箱'决策",
                "责任归属：AI 辅助诊断的医疗责任划分仍需法律明确",
            ],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "solid",
                "decorations": [{"type": "accent_bar", "position": "left", "color": "accent"}],
            },
            "image_query": "",
        },
        {
            "page_number": 9,
            "layout_type": "summary",
            "title": "感谢观看",
            "subtitle": "AI 让医疗更精准、更普惠",
            "body": ["联系: ai-med@example.com", "参考: Nature Medicine 2026"],
            "visual_plan": {
                "strategy": "BASIC_GRAPHICS_ONLY",
                "bg_treatment": "solid",
                "decorations": [],
            },
            "image_query": "",
            "notes": "",
        },
    ],
}


def test_ppt_generation():
    """测试完整 PPT 生成：设计系统 + 全部 7 种布局渲染器。"""
    print("=" * 60)
    print("Test: PPT generation (design system + 7 layouts)")
    print("=" * 60)

    gen = PptGenerator()
    output = Path("/tmp/birdhelp/test_ppt_output.pptx")
    result = gen.generate(TEST_OUTLINE, output, images_map={})

    assert result.exists(), f"Output file not found: {result}"
    size_kb = result.stat().st_size / 1024
    assert size_kb > 20, f"File too small: {size_kb:.0f} KB"
    print(f"PASS: PPT generated at {result} ({size_kb:.0f} KB)")
    return True


def test_theme_system():
    """测试主题系统：验证所有 6 套主题。"""
    print("\n" + "=" * 60)
    print("Test: Theme system (6 themes)")
    print("=" * 60)

    for name, theme in THEMES.items():
        assert theme.name == name
        assert theme.primary, f"Theme {name} missing primary"
        assert theme.background, f"Theme {name} missing background"
        assert theme.title_font, f"Theme {name} missing title_font"
        assert theme.body_font, f"Theme {name} missing body_font"
        print(f"  OK: {name} — primary=#{theme.primary}, accent=#{theme.accent}")

    print("PASS: All 6 themes valid")
    return True


def test_design_dna():
    """测试设计 DNA 的确定性生成。"""
    print("\n" + "=" * 60)
    print("Test: Design DNA determinism")
    print("=" * 60)

    dna1 = create_dna("tech", "人工智能在医疗领域的应用")
    dna2 = create_dna("tech", "人工智能在医疗领域的应用")
    dna3 = create_dna("tech", "不同的主题")

    assert dna1.shape_style == dna2.shape_style, "DNA should be deterministic"
    assert dna1.density == dna2.density
    assert dna1.decoration_level == dna2.decoration_level
    print(f"  DNA1 & DNA2 identical: shape={dna1.shape_style}, density={dna1.density}, decor={dna1.decoration_level}")
    print(f"  DNA3: shape={dna3.shape_style}, density={dna3.density}, decor={dna3.decoration_level}")

    print("PASS: Design DNA works correctly")
    return True


def test_shapes_toolkit():
    """测试形状工具包常量和渲染器分发。"""
    print("\n" + "=" * 60)
    print("Test: Shapes toolkit and renderer dispatch")
    print("=" * 60)

    from pptx.util import Inches
    assert SLIDE_W == Inches(13.333), f"Wrong slide width: {SLIDE_W}"
    assert SLIDE_H == Inches(7.5), f"Wrong slide height: {SLIDE_H}"

    from generator.ppt.layouts import dispatch_renderer
    for lt in LayoutType:
        renderer = dispatch_renderer(lt.value)
        assert callable(renderer), f"Missing renderer for {lt.value}"
        print(f"  OK: {lt.value} -> {renderer.__module__}")

    print("PASS: Shapes toolkit and renderer dispatch OK")
    return True


def test_image_placeholder():
    """测试图片占位符生成。"""
    print("\n" + "=" * 60)
    print("Test: Image placeholder generation")
    print("=" * 60)

    from generator.ppt.image_provider import _generate_placeholder

    dest = Path("/tmp/birdhelp/test_placeholder.png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _generate_placeholder("AI medical diagnosis workflow visualization", dest)
    assert result, "Placeholder generation failed"
    assert dest.exists(), f"Placeholder file not found: {dest}"
    size_kb = dest.stat().st_size / 1024
    assert size_kb > 1, f"Placeholder too small: {size_kb:.0f} KB"
    print(f"PASS: Placeholder image generated ({size_kb:.0f} KB)")
    return True


def test_layout_coverage():
    """测试数据覆盖了所有主要布局类型。"""
    print("\n" + "=" * 60)
    print("Test: Layout type coverage in test data")
    print("=" * 60)

    layout_types = {s["layout_type"] for s in TEST_OUTLINE["slides"]}
    print(f"  Layout types covered: {sorted(layout_types)}")
    expected = {"cover", "text_only", "text_image", "section", "two_column", "grid_cards", "summary"}
    missing = expected - layout_types
    if missing:
        print(f"  WARNING: Missing layout types: {missing}")
    else:
        print("  All 7 major layout types covered!")

    print("PASS: Layout coverage check done")
    return True


async def main():
    """运行全部测试。"""
    print("BirdHelp PPT — Test Suite")
    print("=" * 60)

    results = []
    results.append(("Theme System", test_theme_system()))
    results.append(("Design DNA", test_design_dna()))
    results.append(("Shapes Toolkit", test_shapes_toolkit()))
    results.append(("Image Placeholder", test_image_placeholder()))
    results.append(("Layout Coverage", test_layout_coverage()))
    results.append(("PPT Generation", test_ppt_generation()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_pass = False

    print(f"\n{'ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'}")
    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
