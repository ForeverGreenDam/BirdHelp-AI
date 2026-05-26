"""场景设计配置文件 — 7 套设计哲学指导，按 style 参数分派。

将 wtfppt 的场景设计知识固化到结构化数据中，
供 PptChain prompt 动态注入和 QA 维度参考。
每套 profile 包含：设计哲学、信息密度、配色指引、字体层级、
叙事风格、内容表达技巧、布局建议、装饰禁令。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SceneProfile:
    """场景设计配置 — 一套完整的设计指导参数。"""

    name: str                           # 场景标识 (对应 style 参数)
    label: str                          # 中文名称
    applicable: str                     # 适用场景描述
    style_anchor: str                   # 风格锚点

    # 设计哲学
    design_philosophy: str = ""         # 核心设计原则

    # 信息密度
    info_density: str = "balanced"      # "sparse" | "balanced" | "high" | "extreme"
    info_density_desc: str = ""         # 信息密度具体指导
    info_density_pct: str = ""          # 填充率百分比指导

    # 图文比例
    text_visual_ratio: str = ""         # 文字与视觉元素的配比描述

    # 配色指引
    color_guidance: str = ""            # 颜色使用原则

    # 字体层级
    font_guidance: str = ""             # 字体选择与层级指导

    # 内容页结构
    content_page_structure: str = ""    # 内容页面结构描述

    # 叙事风格
    narrative_style: str = ""           # 叙事框架和表达方式
    narrative_framework: list[str] = field(default_factory=list)

    # 内容表达技巧
    content_techniques: list[str] = field(default_factory=list)

    # 装饰禁令
    decorations_forbidden: list[str] = field(default_factory=list)
    decorations_alternative: list[str] = field(default_factory=list)

    # 图片使用规则
    image_rules: str = ""

    # 推荐布局类型
    recommended_layouts: list[str] = field(default_factory=list)

    def to_prompt_section(self) -> str:
        """将 profile 转为可注入 prompt 的文本段落。"""
        sections = [
            f"## 场景: {self.label} ({self.name})",
            f"风格锚点: {self.style_anchor}",
            f"\n### 设计哲学\n{self.design_philosophy}",
            f"\n### 信息密度要求\n{self.info_density_desc}",
            f"\n### 图文比例\n{self.text_visual_ratio}",
            f"\n### 配色指引\n{self.color_guidance}",
            f"\n### 字体层级\n{self.font_guidance}",
            f"\n### 内容页结构\n{self.content_page_structure}",
            f"\n### 叙事风格\n{self.narrative_style}",
        ]
        if self.content_techniques:
            techniques = "\n".join(f"  - {t}" for t in self.content_techniques)
            sections.append(f"\n### 内容表达技巧\n{techniques}")
        if self.decorations_forbidden:
            forbidden = "\n".join(f"  - {d}" for d in self.decorations_forbidden)
            sections.append(f"\n### 装饰禁令（禁止以下操作）\n{forbidden}")
        if self.recommended_layouts:
            layouts = ", ".join(self.recommended_layouts)
            sections.append(f"\n### 优先推荐布局类型\n{layouts}")
        return "\n".join(sections)


# ── 7 套场景设计配置 ──

PROFILES: dict[str, SceneProfile] = {
    # ──────────────────────────────────────
    # 1. 学术
    # ──────────────────────────────────────
    "academic": SceneProfile(
        name="academic",
        label="学术答辩/研究报告",
        applicable="论文答辩、课题组汇报、学术会议、科研项目汇报",
        style_anchor="Nature/Science 论文图表风 + 学术会议报告标准",
        design_philosophy=(
            "内容为王，视觉服务于学术内容。所有设计决策以清晰传达研究发现为首要目标，"
            "避免任何过度装饰。保持严谨规范，图表标注完整，数据来源可追溯。"
            "严禁幻觉——所有内容必须有真实完整的引用。"
            "逻辑清晰可见：问题→方法→结果→结论，每页承担明确的论证节点。"
        ),
        info_density="high",
        info_density_desc=(
            "每页聚焦一个研究点，内容区填充率 70-85%，留白控制在 15-30%。"
            "图表和数据是核心内容载体，文字负责解释和逻辑串联。"
            "公式、表格、图表可密集排布但必须保持标注清晰、编号规范和视觉层级。"
            "核心原则：评委/听众能从每页准确提取一个研究发现并理解其支撑证据。"
        ),
        text_visual_ratio=(
            "图表主导型。内容页建议配比：约 35% 文字 + 55% 图表/原图/公式/表格 + 10% 留白。"
            "结果页绝对以图表为中心，文字仅作标注和关键解读。"
            "鼓励使用流程图、示意图展示研究架构、方法流程和系统设计。"
            "避免纯文字页（除研究背景概述页外）。"
        ),
        color_guidance=(
            "以高校校徽/VI 标准色为主色——学术演示配色的最高优先级。"
            "整体追求干净、克制、专业的风格，色彩总数保持最少。"
            "推荐使用低饱和度沉稳主题色（如深蓝系），辅以中性色层级。"
            "图表配色以可区分性为首要目标，参考 Nature/Science 等学术期刊的配色方案。"
            "强调色仅用于突出关键发现、核心结论或显著性标记，克制使用。"
            "禁止：大面积正文区使用深色背景、高饱和荧光色。"
        ),
        font_guidance=(
            "标题：无衬线 Bold (如 MiSans Bold, Arial Bold)，投影环境下清晰利落。"
            "正文：无衬线 Regular，保证投影仪上的可读性。"
            "字体层级：封面标题 36-44px，页标题 26-32px，小标题 22-26px，"
            "正文分析 18-22px（内容少用22px，适中用20px，密集用18px，不可低于18px），"
            "脚注、来源标注 12-16px。"
        ),
        content_page_structure=(
            "推荐页结构：导航栏（横向或纵向）+ 页标题（描述性短语，不超过一行）"
            "+ 内容区（单栏分析 / 左图右解读 / 上图下洞察 / 双图对比 / 数据表+结论）"
            "+ 编号与引用（所有图表有标准编号，如表1、图2）"
            "+ 页脚区（脚注/文献引用 + 页码）。"
        ),
        narrative_style=(
            "论证驱动型。按经典论文结构组织：背景与问题 → 相关工作 → 方法 → "
            "实验设计 → 结果分析 → 结论与未来工作。"
            "语言风格客观严谨，使用学术语言，避免主观臆断。"
            "引用格式遵循学术标准（GB/T 7714 / APA / IEEE），每处引用必须可追溯原文。"
            "末尾必须包含参考文献专用页。"
        ),
        content_techniques=[
            "原图优先复用：学术汇报优先使用论文/报告中的原图和原表，保持数据精度和标注规范",
            "实验图表：折线图（趋势对比）、柱状图（方法对比）、散点图（相关性分析）、雷达图（多维度比较）",
            "数据表格：方法对比表（行为方法，列为指标），最佳结果用加粗或强调色突出",
            "流程图/架构图：用形状+箭头+文字展示研究方法流程或系统架构",
            "公式展示：关键公式居中独立展示，公式前后附变量说明",
            "要点列表：研究贡献、实验设置、消融研究结论等以编号列表呈现",
            "文献引用：正文引用处标注编号[1][2-4]，末尾完整参考文献页",
        ],
        decorations_forbidden=[
            "花哨的背景/纹理 → 纯白/极浅灰等纯色背景",
            "装饰性图标/插画 → 科学图和数据图表",
            "文字艺术字/文本效果 → 标准学术字体，通过字重和字号区分",
            "无标注的图表 → 完整标注：标题、轴标签、图例、单位、数据来源",
            "渐变色和阴影效果 → 平面纯色，保持学术图表规范",
            "过多视觉特效 → 干净克制，内容本身就是焦点",
        ],
        image_rules="允许信息型图片（产品照片、技术流程、品牌/人物、场景氛围、地图/区域图）；禁止纯装饰性图片（抽象纹理、无关配图、科技感光效）。",
        recommended_layouts=["cover", "section", "text_only", "text_image", "two_column", "chart", "table", "grid_cards", "summary"],
    ),

    # ──────────────────────────────────────
    # 2. 商业洞察
    # ──────────────────────────────────────
    "business": SceneProfile(
        name="business",
        label="商业洞察/行业研究",
        applicable="证券研究报告、行业研究、市场调研、竞争分析、战略咨询",
        style_anchor="麦肯锡/BCG/Bain 顶级咨询公司报告 + 中金/华泰/民生证券研究报告",
        design_philosophy=(
            "结论先行（金字塔原理）：标题必须是完整的洞察结论句（Action Title），看标题即知结论。"
            "极致克制：零装饰——无圆角、无阴影、无渐变、无色块卡片。所有视觉元素必须携带信息。"
            "排版即层级：仅通过字号、字重、衬线/非衬线对比建立视觉层级，不使用颜色和装饰区分。"
            "高密度（最高优先级）：页面内容极度密集，通过边距和行间距维持可读性。"
            "可验证性：所有数据和结论必须标注信息来源，确保每个关键论断可以溯源。"
        ),
        info_density="extreme",
        info_density_desc=(
            "内容区填充率至少 90% 以上，严禁大面积空白。"
            "每页正文至少包含 3-5 个核心数据点（加粗数字/高亮标注）。"
            "组合 图表+文字、表格+要点 等格式，在单页上呈现多层信息。"
            "数据表格至少 4 行以上（含表头），充分利用表格的信息承载能力。"
            "图表密集排布，单页可容纳 2-3 张关联图表配合精炼文字解读。"
            "避免：单张大图表占满整页、仅 2-3 条的要点页、大面积空白区。"
        ),
        text_visual_ratio=(
            "均衡偏文型。内容页建议配比：约 60% 文字 + 30% 图表 + 10% 数据标注和来源说明。"
            "文字是核心信息载体，图表是数据可视化和证据支撑。"
            "图表必须配合文字解读或关键数据提取，图表不能孤立存在。"
            "数据标注必须完整：图表的轴标签、单位、数据标签、图例缺一不可。"
            "来源标注推荐使用超链接形式指向原报告或数据页面。"
        ),
        color_guidance=(
            "极度克制的配色策略：整体配色保持高度理性和克制，以少量核心色辅以中性色层级建立视觉秩序。"
            "允许使用多色调但单页/单图表内颜色必须收敛，每页围绕明确的主题色系。"
            "图表核心数据系列使用主题色或同色系变化表达层级，非核心数据使用中性色或低存在感辅色。"
            "关键信息强调优先通过字重、字号或位置实现，而非依赖鲜艳的颜色对比。"
            "背景和结构元素使用低存在感的中性色，保持信息为主的视觉环境。"
            "严格限制装饰性用色，整体配色服务信息表达而非装饰功能。"
        ),
        font_guidance=(
            "标题（Action Title、封面、章节）：衬线 Bold，传递专业权威感。"
            "正文、数据、页脚：无衬线（如 Arial）。"
            "中文：微软雅黑，搭配 Arial 英文数字。"
            "字号层级对比要强：封面标题 44-56px → Action Title 26-32px → "
            "正文 18-22px（内容少用22px，适中用20px，密集用18px，不可低于18px）"
            "→ 脚注/来源 12-16px。"
        ),
        content_page_structure=(
            "内容页典型构成：Action Title（结论式标题）+ 主体内容区（图表/表格/要点）"
            "+ 数据来源 + 页码。"
            "常用结构：单栏分析结构（纵向叙事）、左图右解读、上图下洞察、双图对比、数据表+结论。"
            "Action Title 是最具辨识度的视觉特征，分隔线和内容区在标题下方适配。"
            "内容区使用自由排版（图表、表格、文字等）尽可能填满。"
            "页脚区预留数据来源注释，格式统一，字号缩小，保证信息可溯源。"
        ),
        narrative_style=(
            "洞察驱动型。每页以核心洞察/结论为 Action Title 开头，以数据和案例支撑。"
            "避免纯事实罗列，强调「so what」——数据背后的含义和业务启示。"
            "内容层次：结论 → 数据/证据 → 解读/启示。"
            "证券研究风格：观点明确、逻辑严谨、表述专业但不晦涩，适度使用行业术语。"
        ),
        content_techniques=[
            "密集专业图表：柱状图、折线图、饼图、面积图、组合图等数据可视化；鼓励对比图、趋势图、同比/环比分析图",
            "结构化表达：有序/无序列表配合主题句；每个要点组至少 2-3 条，每条含具体数据",
            "大数字突出：核心指标以大数字 + 单位 + 简要说明呈现（如营收、增速、市占率）",
            "表格应用：适合多维度对比（竞品对比、财务指标对比、方案对比等）；表头深底白字，数据行交替白/浅灰",
            "强调标注：关键数据和核心结论加粗（不使用彩色文字）",
            "数据来源标注：图表和关键数据必须注明来源，格式如「来源：机构名，年份；」，10-12px 灰色文字",
            "同文档内不同页面应避免使用完全相同的布局，根据内容变化布局结构以维持阅读节奏",
        ],
        decorations_forbidden=[
            "阴影 → 完全不用阴影",
            "渐变填充 → 纯色填充",
            "装饰性图标 → 非必要不使用，让文字和数据说话",
            "无来源的数据引用 → 必须注明来源信息",
            "圆角 → 仅使用直角矩形",
            "彩色装饰色块 → 用排版层级替代",
        ],
        image_rules=(
            "允许信息型图片：产品照、技术流程、品牌/人物、场景/氛围、地图/区域图。"
            "禁止纯装饰性图片：抽象背景纹理、无关配图、科技感光效粒子背景。"
            "数据图表用 chart 元素而非图片，流程图用 shape+text 组合而非截图。"
        ),
        recommended_layouts=["cover", "section", "text_only", "chart", "table", "big_number", "two_column", "text_image", "summary"],
    ),

    # ──────────────────────────────────────
    # 3. 创意视觉
    # ──────────────────────────────────────
    "creative": SceneProfile(
        name="creative",
        label="创意视觉/品牌发布",
        applicable="品牌发布、产品展示、创意提案、艺术展览、营销活动",
        style_anchor="Apple Keynote 风格 + 奢侈品牌/艺术展览视觉",
        design_philosophy=(
            "视觉冲击力优先，以画面叙事。大胆使用色彩、构图和留白营造情感共鸣。"
            "每一页都是独立的海报级视觉作品，文字精简到极致。"
            "强调品牌调性和情绪传达，信息密度让位于视觉感受。"
        ),
        info_density="balanced",
        info_density_desc=(
            "中等密度，视觉冲击与信息量并重。每页信息点 3-4 个，留白率 25-40%。"
            "文字精简有力但不空洞，用图像和颜色配合信息传递。"
        ),
        text_visual_ratio="图像主导。约 20% 文字 + 70% 图像/色块/形状 + 10% 留白。全图背景+文字叠加为常见形式。",
        color_guidance=(
            "大胆用色，可以使用高对比度配色方案和渐变背景。"
            "以品牌色为核心建立色彩系统，可以使用丰富的辅助色和点缀色。"
            "允许深色背景+亮色文字的大胆组合，允许大面积渐变和色彩过渡。"
        ),
        font_guidance=(
            "标题：粗体大字（44-60px），可以使用文艺或设计感字体。"
            "正文精简到最少，字号 20-28px。"
            "可以混合使用多种字重营造节奏感（Thin + Bold 对比）。"
        ),
        content_page_structure="全图背景+文字叠加 / 大色块分区 / 中心聚焦式排版。图片为主角，文字做点缀。",
        narrative_style="情感共鸣型。用视觉故事引导情绪，从引发好奇→建立认同→激发行动。每页1-2句精华文案。",
        content_techniques=[
            "大图背景+半透明遮罩+精炼文字",
            "超大字号的核心数字或关键词",
            "色彩渐变过渡营造氛围",
            "动感构图和非对称布局",
        ],
        decorations_forbidden=[
            "密集要点列表 → 拆分为多页",
            "传统表格 → 用可视化图表替代",
            "保守配色 → 走出安全区，大胆用色",
            "过多文字 → 极度精简，关键词即可",
        ],
        image_rules="图片质量至上。必须使用高清、有质感的图片。品牌图、产品图、氛围图均可。禁止低质量素材和小图拼接。",
        recommended_layouts=["cover", "text_image", "image_full", "big_number", "quote", "grid_cards", "summary"],
    ),

    # ──────────────────────────────────────
    # 4. 极简
    # ──────────────────────────────────────
    "minimal": SceneProfile(
        name="minimal",
        label="极简/现代简约",
        applicable="通用演示、知识分享、TED 风格演讲、简约风格提案",
        style_anchor="TED 演讲风 + MUJI/无印良品简约美学 + 瑞士国际主义设计风格",
        design_philosophy=(
            "少即是多。去除一切不必要的元素，让核心观点清晰可见。"
            "大量留白创造呼吸感，每页只传达一个核心观点。"
            "字体层级清晰，通过字号、字重对比建立信息层级。"
        ),
        info_density="balanced",
        info_density_desc="适度留白但不空洞。每页 3-4 个信息点，留白率 35-50%。文字精炼但内容充实，用金句式短句+支撑细节传达观点。",
        text_visual_ratio="文字主导但不密集。约 50% 文字 + 20% 辅助图形/图标 + 30% 留白。",
        color_guidance=(
            "极度克制的配色。主色使用深灰或纯黑，背景纯白，可选用一个强调色做点缀。"
            "全文档颜色不超过 3 种。不使用渐变、阴影等效果。"
            "可以大量使用黑白灰层级，偶尔用强调色点睛。"
        ),
        font_guidance="无衬线字体为主。字重对比明显（Bold 标题 + Light 正文）。字号跨度大，标题 40-56px，正文 20-26px。",
        content_page_structure="居中排版 / 左对齐宽行距 / 图文大面积分离。大标题 + 简短要点 + 大量留白。",
        narrative_style="金句型。短句、有力、节奏感强。避免长段落，每页用一句话概括核心观点。",
        content_techniques=[
            "超大标题短句：一页一句话，字号很大（40-56px）",
            "单一数据突出展示：一个大数字+简短说明",
            "图片+一句话配合大量留白",
            "简洁的图标+短文字组合",
        ],
        decorations_forbidden=[
            "任何复杂装饰 → 极简无装饰",
            "多种颜色混用 → 黑白灰+1种强调色",
            "密集排版 → 大量留白",
            "阴影、渐变、圆角 → 直角、平面",
        ],
        image_rules="少量高质量的图片，大图展示为主，禁止小图拼凑。图片也需要有留白感。",
        recommended_layouts=["cover", "big_number", "quote", "text_image", "image_full", "text_only", "summary"],
    ),

    # ──────────────────────────────────────
    # 5. 科技
    # ──────────────────────────────────────
    "tech": SceneProfile(
        name="tech",
        label="科技/数字化",
        applicable="科技产品介绍、技术报告、数字化转型方案、AI/大数据主题",
        style_anchor="科技公司发布会风格（Google/微软/华为）+ 科技媒体报告",
        design_philosophy=(
            "科技感和前瞻性。使用深色或冷色调背景，通过渐变色线条和几何形状营造数字空间感。"
            "数据可视化是核心表达方式，用图表和数字说话。"
            "结构清晰，模块化排版，体现技术严谨性。"
        ),
        info_density="balanced",
        info_density_desc="适中密度，填充率 50-70%。数据图表丰富但不拥挤，每页 3-5 个信息点。技术架构图和流程图是重要内容形式。",
        text_visual_ratio="均衡偏图型。约 35% 文字 + 55% 图表/架构图/数据可视化 + 10% 装饰性科技元素。",
        color_guidance=(
            "深蓝/深灰背景 + 亮蓝/霓虹绿强调色。可以使用渐变色线条和几何装饰。"
            "技术色系：蓝、青色系为主，可以加入紫色或绿色做对比。"
            "深色背景为主时可使用浅色/白色文字，形成高对比。"
        ),
        font_guidance="无衬线字体，清晰的几何字体优先。等宽字体用于代码和技术参数。字号层级清晰，标题 32-40px，正文 18-22px。",
        content_page_structure="模块化网格排版。常用：深色全屏背景+亮色文字 / 暗色渐变+几何装饰 / 卡片式信息模块。",
        narrative_style="方案驱动型。从技术背景→方案架构→核心优势→落地路径。用架构图、流程图、数据对比展示技术竞争力。",
        content_techniques=[
            "技术架构图：用矩形、连线、箭头构建系统架构",
            "数据对比图：技术指标对比柱状图或雷达图",
            "时间线：技术演进路线或版本迭代",
            "代码/参数展示：用等宽字体突出技术参数",
            "流程图：数据流、请求链路等技术流程",
        ],
        decorations_forbidden=[
            "手绘/有机风格 → 几何、数字化风格",
            "暖色调/大地色 → 冷色调、科技色系",
            "传统商务模板 → 模块化、数字化排版",
        ],
        image_rules="技术产品图、数字界面截图、技术架构图、芯片/电路板等科技素材。避免生活化、自然类图片。",
        recommended_layouts=["cover", "section", "text_image", "chart", "big_number", "timeline", "grid_cards", "two_column", "summary"],
    ),

    # ──────────────────────────────────────
    # 6. 温暖
    # ──────────────────────────────────────
    "warm": SceneProfile(
        name="warm",
        label="温暖/人文关怀",
        applicable="教育培训、工作汇报、年终总结、企业文化、人文主题",
        style_anchor="教育培训汇报 + 公司内部管理报告 + 人文主题演讲",
        design_philosophy=(
            "温暖亲和力优先。使用暖色调、圆角形状、手绘感装饰营造友好氛围。"
            "信息组织清晰但不冰冷，通过色彩和形状传递人文关怀。"
            "适度装饰是可接受的，但要服务于内容氛围而非分散注意力。"
        ),
        info_density="balanced",
        info_density_desc="适中密度，填充率 55-70%。每页 3-5 个要点，信息量充实但不拥挤，给读者舒适的阅读节奏。适当使用图标和插图辅助理解。",
        text_visual_ratio="均衡型。约 50% 文字 + 35% 图表/插图/图标 + 15% 留白。鼓励图文配合，多用图标替代文字要点。",
        color_guidance=(
            "暖色调为主：棕色、橙色、暖黄、米色。可以用柔和的渐变。"
            "避免高对比度的尖锐配色，色调柔和过渡。"
            "可以使用暖色系搭配奶油色/米色背景，营造温馨感。"
        ),
        font_guidance=(
            "标题可以使用衬线字体增加人文气息。正文无衬线保证可读性。"
            "字号层级温和过渡：标题 32-40px → 小标题 24-28px → 正文 18-22px。"
        ),
        content_page_structure="圆角卡片 + 暖色背景 + 图标辅助。内容以卡片+图标形式组织，画面有温度和层次。",
        narrative_style="故事叙述型。用叙事线索串联，先讲故事背景→展开细节→提炼心得体会。语言风格温暖亲切但不失专业性。",
        content_techniques=[
            "卡片+图标组合：每个要点用图标+标题+简短说明",
            "大数字+温暖底色：关键数据用暖色圆角背景突出",
            "时间线/里程碑：用温暖配色展示成长历程",
            "图片+引用：温馨图片搭配金句或心得体会",
        ],
        decorations_forbidden=[
            "尖锐直角 → 优先使用圆角 (8-12pt)",
            "冷色调配色 → 暖色调为主",
            "过于密集的排版 → 保持舒适阅读节奏",
            "冰冷的商务图表 → 用温暖配色软化",
        ],
        image_rules="生活化场景、人物表情、自然光效、团队合影等人文类图片。技术素材需用暖色滤镜或遮罩调和。",
        recommended_layouts=["cover", "section", "text_only", "text_image", "grid_cards", "timeline", "big_number", "summary"],
    ),

    # ──────────────────────────────────────
    # 7. 通用
    # ──────────────────────────────────────
    "general": SceneProfile(
        name="general",
        label="通用/标准商务",
        applicable="各类通用演示、无特定场景要求的商业演示文稿",
        style_anchor="标准商务演示文稿 + 简洁专业的通用风格",
        design_philosophy=(
            "均衡中庸，适应性强。不过于激进也不过于保守，适合大多数商务场景。"
            "以清晰传达信息为第一优先级，视觉风格干净专业。"
        ),
        info_density="balanced",
        info_density_desc="标准密度，填充率 60-75%。每页 4-6 个要点，信息充实。图表和文字搭配均衡，页面不空荡。",
        text_visual_ratio="标准均衡。约 50% 文字 + 40% 图表/图片 + 10% 留白/装饰。",
        color_guidance="以蓝色系为主色（企业通用色），辅以灰色层级。可选一个强调色（橙色或绿色）做数据点缀。整体干净利落。",
        font_guidance="无衬线字体，微软雅黑 / Arial 组合。标题 32-40px，小标题 24-28px，正文 18-22px，注释 12-14px。",
        content_page_structure="标题+装饰线+要点+配图的标准结构。左对齐排版，保持视觉一致性。",
        narrative_style="标准商务叙述。概述→细节→总结的三段式。语言简洁专业，避免术语堆砌和过于口语化。",
        content_techniques=[
            "标准图表：柱状图、饼图、折线图等基础商务图表",
            "要点列表：有序/无序列表搭配简短说明",
            "图文混排：左文右图或上图下文",
            "卡片网格：适合并列介绍的多个主题",
        ],
        decorations_forbidden=[
            "过于花哨的装饰 → 保持简洁专业",
            "极端配色 → 控制在 3-4 种颜色以内",
            "过于密集的排版 → 保持舒适阅读",
        ],
        image_rules="通用商务图片：办公场景、商务人物、产品展示、抽象商务概念图。避免过于艺术化或与内容无关的图片。",
        recommended_layouts=["cover", "section", "text_only", "text_image", "chart", "table", "grid_cards", "summary"],
    ),
}


def get_profile(style_name: str) -> SceneProfile:
    """根据风格名获取场景 profile，未匹配时返回通用 profile。"""
    return PROFILES.get(style_name, PROFILES["general"])


def get_profile_prompt_section(style_name: str) -> str:
    """获取指定场景的 prompt 注入文本，用于动态增强 LLM 提示。"""
    profile = get_profile(style_name)
    return profile.to_prompt_section()
