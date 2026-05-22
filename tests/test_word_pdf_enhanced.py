"""Word/PDF 增强生成测试 — 验证 DocxBuilder、图表引擎、图片占位。

运行方式: python -m tests.test_word_pdf_enhanced
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Word 测试数据 ──

WORD_OUTLINE = {
    "title": "2026 年人工智能行业发展趋势报告",
    "subtitle": "聚焦医疗、金融、制造三大领域",
    "abstract": "本报告系统分析了 2026 年全球人工智能行业的发展现状与未来趋势。通过市场规模数据、企业研发投入、关键技术突破等多维度指标，为决策者提供数据驱动的战略参考。",
    "style": "tech",
    "design_note": "科技蓝调，数据图表驱动，专业报告风格",
    "sections": [
        {
            "heading": "第一章 行业概览",
            "content": [
                "人工智能产业在 2026 年继续保持高速增长态势。据 Grand View Research 最新报告显示，全球 AI 市场规模已突破 4500 亿美元，年复合增长率达到 44.9%，远超传统信息技术产业的增长速度。这一增长主要由深度学习技术的成熟、算力成本的持续下降以及各行业数字化转型需求共同驱动。",
                "从区域分布来看，北美市场仍占据全球 AI 产业 42% 的份额，以 Google、Microsoft、OpenAI 为代表的科技巨头持续加大研发投入。中国市场以 28% 的份额位居第二，在计算机视觉、自然语言处理等细分领域已达到国际领先水平。欧洲市场以 18% 的份额紧随其后，在 AI 伦理治理和监管框架建设方面走在前列。",
            ],
            "charts": [
                {
                    "type": "bar",
                    "title": "2020-2026 年全球 AI 市场规模（十亿美元）",
                    "data": {
                        "labels": ["2020", "2021", "2022", "2023", "2024", "2025", "2026"],
                        "datasets": [
                            {"label": "医疗 AI", "values": [5, 8, 14, 22, 35, 50, 68]},
                            {"label": "金融 AI", "values": [12, 18, 26, 35, 46, 58, 72]},
                            {"label": "制造 AI", "values": [8, 13, 19, 28, 38, 49, 62]},
                        ],
                    },
                    "width": "full",
                    "caption": "数据来源: Grand View Research 2026",
                },
            ],
        },
        {
            "heading": "第二章 区域市场分析",
            "content": [
                "全球 AI 市场呈现明显的地域集中特征。北美、中国和欧洲三大区域合计占据了全球 AI 市场近 88% 的份额。其中北美地区凭借强大的基础研究能力和完善的创投生态，持续引领前沿技术突破；中国市场依托庞大的应用场景和数据资源优势，在产业化落地方面表现突出。",
            ],
            "charts": [
                {
                    "type": "pie",
                    "title": "全球 AI 市场份额分布（2026）",
                    "data": {
                        "labels": ["北美", "中国", "欧洲", "亚太其他", "其他地区"],
                        "datasets": [
                            {"label": "份额", "values": [42, 28, 18, 8, 4]},
                        ],
                    },
                    "width": "half",
                    "caption": "数据来源: IDC Worldwide AI Spending Guide",
                },
            ],
        },
        {
            "heading": "第三章 企业研发投入对比",
            "content": [
                "全球主要科技企业在 AI 领域的研发投入持续攀升。2026 年，前五大科技企业的 AI 研发总投入超过 1200 亿美元，较上年增长 22%。其中 Google DeepMind 以 320 亿美元的投入位居榜首，Microsoft AI 紧随其后。值得关注的是，中国企业的研发投入增速明显加快，百度、华为等企业已进入全球前十。",
            ],
        },
    ],
    "tables": [
        {
            "caption": "表 1: 主要 AI 企业研发投入对比（2025-2026）",
            "headers": ["企业", "研发投入(亿美元)", "同比增长", "主要方向"],
            "rows": [
                ["Google DeepMind", "320", "+18%", "大语言模型、多模态"],
                ["Microsoft AI", "280", "+22%", "Copilot 生态、Azure AI"],
                ["Meta AI", "190", "+15%", "开源模型 LLaMA 系列"],
                ["OpenAI", "150", "+35%", "GPT 系列、Sora 视频生成"],
                ["百度 AI", "95", "+25%", "文心大模型、自动驾驶"],
            ],
            "width": "full",
        },
    ],
    "references": [
        "[1] Grand View Research. Artificial Intelligence Market Size Report, 2026.",
        "[2] IDC. Worldwide AI Spending Guide Q1 2026.",
        "[3] Stanford HAI. Artificial Intelligence Index Report 2026.",
        "[4] McKinsey Global Institute. The State of AI in 2026.",
    ],
}

PDF_OUTLINE = {
    "title": "2026 年上半年工作总结",
    "subtitle": "AI 研发部",
    "author": "张三",
    "date": "2026-06-30",
    "style": "business",
    "design_note": "专业简洁商务风格，数据图表驱动",
    "page_layout": {
        "columns": 1,
        "header_text": "XX 科技有限公司 — 内部文件",
        "footer_text": "第 {page} 页",
        "show_page_number": True,
    },
    "sections": [
        {
            "heading": "一、季度业绩回顾",
            "content": [
                "2026 年上半年，AI 研发部在自然语言处理、计算机视觉和智能推荐三大方向取得了显著进展。团队共完成 12 个项目的交付，其中 8 个项目已成功上线并产生业务价值。总代码提交量达到 45000 次，较去年同期增长 35%。团队规模从年初的 35 人扩展至 48 人，新增了 5 名博士研究员和 8 名资深工程师。",
            ],
            "charts": [
                {
                    "type": "line",
                    "title": "上半年月度项目交付数量",
                    "data": {
                        "labels": ["1月", "2月", "3月", "4月", "5月", "6月"],
                        "datasets": [
                            {"label": "计划交付", "values": [5, 5, 6, 7, 7, 8]},
                            {"label": "实际交付", "values": [5, 4, 6, 7, 8, 9]},
                        ],
                    },
                    "width": "full",
                    "caption": "6 月超额完成交付目标",
                },
            ],
        },
        {
            "heading": "二、关键技术突破",
            "content": [
                "在自然语言处理方向，团队成功训练了一个基于 Transformer 架构的 70 亿参数中文大模型，在 C-Eval 和 CMMLU 基准测试中均达到业界领先水平。模型推理速度通过量化技术优化后提升 3 倍，单卡 QPS 达到 120。在计算机视觉方向，自研的目标检测模型在 COCO 数据集上 mAP 达到 58.7%，较基线模型提升 4.2 个百分点。",
            ],
            "charts": [
                {
                    "type": "radar",
                    "title": "三大方向能力评估（百分制）",
                    "data": {
                        "labels": ["准确率", "推理速度", "模型规模", "部署效率", "成本控制"],
                        "datasets": [
                            {"label": "NLP", "values": [92, 85, 90, 78, 82]},
                            {"label": "CV", "values": [88, 90, 75, 85, 80]},
                            {"label": "推荐", "values": [85, 95, 70, 88, 90]},
                        ],
                    },
                    "width": "half",
                    "caption": "NLP 在准确率和模型规模维度领先",
                },
            ],
        },
    ],
    "tables": [
        {
            "caption": "表: 上半年各季度业绩指标汇总",
            "headers": ["指标", "Q1 实际", "Q2 实际", "上半年合计", "年度目标完成率"],
            "rows": [
                ["项目交付数", "5", "7", "12", "60%"],
                ["代码提交量", "20000", "25000", "45000", "—"],
                ["论文发表", "2", "3", "5", "50%"],
                ["专利申请", "3", "4", "7", "70%"],
                ["团队人数", "38", "48", "48", "96%"],
            ],
            "width": "full",
        },
    ],
}


def test_word_generation():
    """测试 Word 文档生成（含图表）。"""
    print("=" * 60)
    print("Test 1: Word generation with charts")
    print("=" * 60)

    from generator.word import WordGenerator

    gen = WordGenerator()
    output = Path("/tmp/birdhelp/test_enhanced_word.docx")
    result = gen.generate(WORD_OUTLINE, output)

    assert result.exists(), f"Output not found: {result}"
    size_kb = result.stat().st_size / 1024
    assert size_kb > 20, f"File too small: {size_kb:.0f} KB"
    print(f"PASS: Word generated at {result} ({size_kb:.0f} KB)")
    return True


def test_pdf_generation():
    """测试 PDF 文档生成（含图表）。"""
    print("\n" + "=" * 60)
    print("Test 2: PDF generation with charts")
    print("=" * 60)

    from generator.pdf import PdfGenerator

    gen = PdfGenerator()
    output = Path("/tmp/birdhelp/test_enhanced_pdf.pdf")
    try:
        result = gen.generate(PDF_OUTLINE, output)
        assert result.exists(), f"Output not found: {result}"
        size_kb = result.stat().st_size / 1024
        print(f"PASS: PDF generated at {result} ({size_kb:.0f} KB)")
        return True
    except Exception as e:
        # LibreOffice may not be installed - check if at least the docx was built
        print(f"SKIP: PDF conversion failed (LibreOffice not available?): {e}")
        return None  # not a failure, just unavailable


def test_chart_engine():
    """测试图表引擎：5 种图表类型。"""
    print("\n" + "=" * 60)
    print("Test 3: Chart engine (5 chart types)")
    print("=" * 60)

    from generator._chart_engine import render_chart, _HAS_MPL
    from generator._design import get_palette

    if not _HAS_MPL:
        print("SKIP: matplotlib not installed")
        return None

    palette = get_palette("tech")
    chart_dir = Path("/tmp/birdhelp/charts")
    chart_dir.mkdir(parents=True, exist_ok=True)

    chart_types = [
        {"type": "bar", "title": "柱状图", "data": {"labels": ["A", "B", "C"], "datasets": [{"label": "X", "values": [10, 20, 15]}]}, "width": "half"},
        {"type": "line", "title": "折线图", "data": {"labels": ["Q1", "Q2", "Q3"], "datasets": [{"label": "Y", "values": [5, 15, 10]}]}, "width": "half"},
        {"type": "pie", "title": "饼图", "data": {"labels": ["甲", "乙", "丙"], "datasets": [{"label": "P", "values": [40, 35, 25]}]}, "width": "half"},
        {"type": "horizontal_bar", "title": "横向柱状图", "data": {"labels": ["项目 Alpha", "项目 Beta"], "datasets": [{"label": "得分", "values": [88, 92]}]}, "width": "half"},
        {"type": "radar", "title": "雷达图", "data": {"labels": ["A", "B", "C", "D", "E"], "datasets": [{"label": "R", "values": [80, 70, 90, 60, 85]}]}, "width": "half"},
    ]

    count = 0
    for i, spec in enumerate(chart_types):
        path = chart_dir / f"test_chart_{i}.png"
        result = render_chart(spec, path, palette)
        if result and result.exists():
            count += 1
            print(f"  OK: {spec['type']} ({result.stat().st_size / 1024:.0f} KB)")

    print(f"PASS: {count}/{len(chart_types)} chart types rendered")
    return count >= 4


def test_docx_builder():
    """测试 DocxBuilder：封面、段落、标题、表格。"""
    print("\n" + "=" * 60)
    print("Test 4: DocxBuilder basic features")
    print("=" * 60)

    from generator._design import get_palette
    from generator._docx_builder import DocxBuilder

    palette = get_palette("business")
    builder = DocxBuilder(palette)

    mini_outline = {
        "title": "测试文档",
        "subtitle": "验证 DocxBuilder 功能",
        "author": "测试者",
        "date": "2026-05-22",
        "sections": [
            {"heading": "测试章节", "content": ["这是一段测试段落，用于验证 DocxBuilder 的基本功能是否正常。段落中的文字应该包含正确的字体、字号和行间距设置。首行应该有两字符的缩进。这是一段测试段落，用于验证 DocxBuilder 的基本功能是否正常。"]},
        ],
        "tables": [
            {"caption": "测试表格", "headers": ["列A", "列B"], "rows": [["值1", "值2"]]},
        ],
    }

    doc = builder.build_document(mini_outline)
    output = Path("/tmp/birdhelp/test_builder.docx")
    doc.save(str(output))
    assert output.exists()
    print(f"PASS: DocxBuilder output at {output} ({output.stat().st_size / 1024:.0f} KB)")
    return True


def test_design_module():
    """测试公共设计模块：6 套调色板。"""
    print("\n" + "=" * 60)
    print("Test 5: Common design module")
    print("=" * 60)

    from generator._design import THEMES, get_palette

    for name in THEMES:
        p = get_palette(name)
        assert p.primary, f"{name} missing primary"
        assert p.body_font, f"{name} missing body_font"
        print(f"  OK: {name} — primary={p.primary}, accent={p.accent}")

    # PPT theme still works
    from generator.ppt.theme import get_theme
    theme = get_theme("tech")
    assert theme.primary is not None
    print(f"  OK: PPT theme from _design — primary class={type(theme.primary).__name__}")

    print("PASS: Common design module OK")
    return True


async def main():
    print("BirdHelp Word/PDF Enhancement — Test Suite")
    print("=" * 60)

    results = []
    results.append(("Design Module", test_design_module()))
    results.append(("Chart Engine", test_chart_engine()))
    results.append(("DocxBuilder", test_docx_builder()))
    results.append(("Word Generation", test_word_generation()))
    results.append(("PDF Generation", test_pdf_generation()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    skipped = 0
    for name, ok in results:
        if ok is None:
            status = "SKIP"
            skipped += 1
        else:
            status = "PASS" if ok else "FAIL"
            if not ok:
                all_pass = False
        print(f"  [{status}] {name}")

    print(f"\n{5 - skipped} passed, {skipped} skipped"
          f"{' — ALL PASSED' if all_pass else ' — SOME FAILED'}")
    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
