# PPT 生成功能设计文档

> v2.1 | 2026-05-22 | Phase 3 完成版（设计系统 + 布局渲染器 + 图片 + QA）

---

## 一、整体架构

```
POST /ai/ppt/generate (PptGenerateRequest)
  │
  ▼
api/ppt.py              ← FastAPI 路由，参数由 Pydantic 校验
  │
  ▼
services/generation.py  ← 业务编排：扣额度 → 调图 → 上传 / 退款
  │
  ▼
graph/generation_graph.py ← LangGraph 状态图：RAG → Chain → 校验 → 重试 (≤3)
  │                           PPT 额外: → 图片获取 → Q&A评分 → 修复循环
  │
  ├─ chains/ppt_chain.py    ← PptChain（视觉描述生成）
  ├─ chains/qa_chain.py     ← 质量评估 + 修复循环
  │
  ▼
generator/ppt/generator.py ← PptGenerator（分发到各布局渲染器）
  │
  ├─ generator/_design.py          ← 公共 ColorPalette（PPT/Word/PDF 共用）
├─ generator/ppt/theme.py      ← PPT ColorTheme（从 _design 派生）
  ├─ generator/ppt/layout.py     ← 11 种布局类型 + DesignDNA
  ├─ generator/ppt/shapes.py     ← 声明式绘图工具包
  ├─ generator/ppt/layouts/      ← 每种布局的渲染器
  │   ├─ cover.py                (封面，3 种变体)
  │   ├─ section_header.py       (章节分隔，3 种变体)
  │   ├─ text_only.py            (纯文字 + 装饰)
  │   ├─ text_image.py           (图文混排：左右/上下)
  │   ├─ two_column.py           (双栏对比)
  │   ├─ grid_cards.py           (卡片网格)
  │   └─ summary.py              (总结/致谢)
  └─ generator/ppt/image_provider.py ← 图片搜索/下载/降级
  │
  ▼
client/file.py           ← RSA-SHA256 签名上传到 Java 后端存储
```

分层职责：

| 层 | 文件 | 职责 |
|----|------|------|
| API | `api/ppt.py` | HTTP 端点，接收 `PptGenerateRequest`，返回 `ApiResponse` |
| 服务 | `services/generation.py` | 业务编排：额度 `consume` / `refund`、图调用、文件上传 |
| 图 | `graph/generation_graph.py` | LangGraph 状态图，编排 RAG → Chain → 校验 → 图片 → QA → 构建 |
| Chain | `chains/ppt_chain.py` | PptChain，Prompt + LLM + JSON 视觉描述 |
| Chain | `chains/qa_chain.py` | 质量评估，逐页打分 + 修复循环 |
| 设计系统 | `generator/ppt/theme.py` | 6 套 ColorTheme |
| 设计系统 | `generator/ppt/layout.py` | 11 种 LayoutType + DesignDNA |
| 设计系统 | `generator/ppt/shapes.py` | 声明式形状/文本框/图片/背景操作 |
| 渲染器 | `generator/ppt/layouts/*.py` | 每种布局类型的独立渲染实现 |
| 图片 | `generator/ppt/image_provider.py` | Unsplash→Pexels→占位图 三级降级 |
| 生成器 | `generator/ppt/generator.py` | PptGenerator，分发到各布局渲染器 |

---

## 二、生成模式

LLM 输出含 `layout_type` / `visual_plan` / `image_query` / `decorations` 的丰富 JSON，
Generator 通过设计系统 + 布局渲染器生成视觉丰富的幻灯片。

**核心能力**:
- 7 种布局渲染器（cover / section / text_only / text_image / two_column / grid_cards / summary）
- 每页可指定装饰元素（强调条、圆形装饰、分割线）
- 自动图片搜索与插入（Unsplash/Pexels）
- 逐页质量评分 + 修复循环（最多 3 轮）
- 6 套预设颜色主题

---

## 三、LangChain Chain 设计

### 3.1 `chains/ppt_chain.py` — PptChain

**Prompt 特点**:
- 布局类型选择指南（11 种类型，何时用哪种）
- 视觉策略说明（MEDIA_REQUIRED / BASIC_GRAPHICS_ONLY / AUTO）
- image_query 编写规范（英文关键词 3-6 词）
- 装饰元素使用规范（accent_bar / circle / line 等）
- 风格适配指导（6 种风格各不同视觉语言）
- 反占位符约束

**输出 JSON Schema**:
```json
{
  "title": "演示文稿主标题",
  "design_note": "整体设计方向的一句话概括",
  "slides": [
    {
      "page_number": 1,
      "layout_type": "cover",
      "title": "标题",
      "subtitle": "副标题",
      "body": ["附加信息"],
      "visual_plan": {
        "strategy": "MEDIA_REQUIRED",
        "bg_treatment": "gradient",
        "decorations": [
          {"type": "accent_bar", "position": "left", "color": "accent"},
          {"type": "circle", "position": "bottom_right", "size": "large"}
        ]
      },
      "image_query": "search keywords in English",
      "image_position": "right",
      "notes": "演讲备注"
    }
  ]
}
```

### 3.2 `chains/qa_chain.py` — PptQAChain

**QA 检查维度**:

| 维度 | 检查内容 | 严重级别 |
|------|---------|---------|
| 占位符 | 是否有 "[图片]"、"TODO" 等占位文字 | 阻塞 |
| 图片策略 | MEDIA_REQUIRED 时 image_query 是否非空 | 阻塞 |
| 标题质量 | 是否简洁有力（非空泛表述） | 高风险 |
| 要点数量 | body/content 是否在 2-6 条 | 警告 |
| 信息密度 | 每条是否传达具体信息 | 警告 |
| 布局匹配 | layout_type 与内容是否匹配 | 警告 |
| 装饰合理 | decorations 数量是否合理 | 警告 |
| image_query | 是否可搜索的英文关键词 | 高风险 |

**修复循环**:
```
每页评估 → score ≥ 70 → 通过
          → score < 70 → LLM 修复（带具体问题列表）→ 重新评估（最多 3 轮）
```

---

## 四、设计系统

### 4.1 颜色主题 (`generator/ppt/theme.py`)

6 套 ColorTheme，每套包含 8 种语义色 + 2 种字体:

| 主题 | 调性 | 主色 |
|------|------|------|
| academic | 严谨正式 | 深蓝 #1A3C6E |
| business | 专业简洁 | 深蓝 #1B3A5C |
| creative | 活泼视觉 | 暖红 #E04A36 |
| minimal | 极简留白 | 深灰 #2D2D2D |
| tech | 科技感 | 蓝色 #0D47A1 |
| warm | 温暖柔和 | 棕色 #8B451E |

### 4.2 设计 DNA (`generator/ppt/layout.py`)

基于 `topic + style` 的 SHA256 哈希做确定性选择，字段:

| 字段 | 可选值 | 影响 |
|------|--------|------|
| shape_style | sharp / rounded / pill | 矩形圆角风格 |
| density | sparse / balanced / dense | 字号和间距 |
| decoration_level | minimal / moderate / rich | 装饰元素密度 |
| cover_variant | 0 / 1 / 2 | 封面布局变体 |
| section_variant | 0 / 1 / 2 | 章节页变体 |

### 4.3 形状工具包 (`generator/ppt/shapes.py`)

封装常用 python-pptx 操作:
- `add_rect()` / `add_circle()` / `add_accent_bar()` / `add_line()` — 形状
- `add_text_box()` / `add_multiline_text_box()` — 文字
- `add_image()` — 图片（自动等比缩放居中裁剪）
- `set_slide_bg()` / `add_page_number()` / `clear_placeholders()` — 页面

### 4.4 布局渲染器 (`generator/ppt/layouts/`)

| 渲染器 | 布局类型 | 变体数 | 说明 |
|--------|---------|--------|------|
| cover.py | cover | 3 | 渐变+强调条 / 色块分区 / 居中极简 |
| section_header.py | section | 3 | 左侧强调条 / 深色全幅 / 编号式 |
| text_only.py | text_only | 1 | 标题+要点+装饰 |
| text_image.py | text_image | 2 | 左右图文 / 上图下文 |
| two_column.py | two_column | 1 | 双栏对比（含标签头） |
| grid_cards.py | grid_cards | 1 | 3-4卡片网格 |
| summary.py | summary | 1 | 居中致谢+装饰 |

---

## 五、图片集成

### 5.1 来源与降级

```
1. Unsplash API → 搜索 → 下载（优先）
2. Pexels API  → 搜索 → 下载（备选）
3. 纯色占位图（PIL 生成带文字标签的 PNG）→ 最终降级
```

### 5.2 流程

```
1. 解析 LLM 输出 → 收集 image_query (strategy=MEDIA_REQUIRED 的页面)
2. 并发搜索下载（最多 4 路，含缓存避免重复）
3. 图片路径回传到 Generator
4. 布局渲染器调用 add_image() 插入
5. 无图时绘制带提示文字的占位色块
```

---

## 六、LangGraph 状态图设计

### 6.1 状态 (`GenerationState`)

PPT 特有字段:
- `enable_images: bool` — 是否启用图片搜索
- `images_map: dict` — slide_key → 本地图片路径列表
- `qa_reports: list[dict]` — 逐页 QA 评分结果

### 6.2 节点

| 节点 | 适用文档 | 职责 |
|------|---------|------|
| `retrieve_context` | 全部 | RAG 检索 |
| `generate_outline` | 全部 | Chain 调用（PPT 用 PptChain） |
| `validate_outline` | 全部 | 校验 JSON 结构 |
| `fetch_images` | PPT | 图片搜索与下载 |
| `run_qa` | PPT | 逐页 Q&A + 修复循环 |
| `build_document` | 全部 | Generator 构建文件 |
| `handle_error` | 全部 | 错误记录 |

### 6.3 路由

```
PPT: START → retrieve → generate → validate → fetch_images → run_qa → build → END
Word/PDF: START → retrieve → generate → validate → build → END
```

---

## 七、API 接口

### 7.1 端点

```
POST /ai/ppt/generate
Content-Type: application/json
X-Timestamp / X-Nonce / X-Signature (RSA-SHA256)
```

**请求体** (`PptGenerateRequest` 继承 `GenerateRequest`)：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `user_id` | str | 是 | — | 用户 ID |
| `project_id` | str | 是 | — | 项目 ID |
| `topic` | str | 是 | — | 文档主题 |
| `language` | str | 否 | zh | zh / en |
| `extra_prompt` | str | 否 | — | 用户补充指令 |
| `material_ids` | list[str] | 否 | — | RAG 素材 ID 列表 |
| `rag_enabled` | bool | 否 | false | 是否启用 RAG |
| `callback_id` | str | 是 | — | 关联 Java 后端请求 ID |
| `style` | str | 否 | academic | academic/business/creative/minimal/tech/warm |
| `slide_count` | int | 否 | 10 | 1–50 |
| `enable_images` | bool | 否 | true | 是否自动搜索配图（Unsplash→Pexels→占位图降级） |

**响应** (`ApiResponse`)：

```json
{
  "code": 0,
  "message": "success",
  "data": { "file_id": "...", "file_url": "..." }
}
```

---

## 八、配置项

`config.py` 新增:

| 配置项 | 默认值 | 说明 |
|------|--------|------|
| ppt_qa_enabled | True | 是否启用 Q&A |
| ppt_qa_score_threshold | 70 | Q&A 通过阈值 |
| ppt_max_repair_rounds | 3 | 单页最大修复轮数 |
| ppt_image_enabled | True | 是否启用图片搜索 |
| ppt_image_source | unsplash | unsplash / pexels |
| ppt_unsplash_access_key | "" | Unsplash API Key |
| ppt_pexels_api_key | "" | Pexels API Key |
| ppt_max_concurrent_slides | 4 | 并发图片下载数 |

---

## 九、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `generator/ppt/theme.py` | **新建** | 6 套颜色主题 ColorTheme |
| `generator/ppt/shapes.py` | **新建** | 声明式形状/文本框/图片工具包 |
| `generator/ppt/layout.py` | **新建** | LayoutType 枚举 + DesignDNA |
| `generator/ppt/layouts/` | **新建** | 7 种布局渲染器 |
| `generator/ppt/image_provider.py` | **新建** | 图片搜索/下载/降级 |
| `generator/ppt/generator.py` | **重构** | PptGenerator（设计系统 + 布局分发） |
| `chains/ppt_chain.py` | **重构** | 完整视觉描述 Prompt + PptChain |
| `chains/qa_chain.py` | **新建** | 质量评估 + 修复循环 |
| `graph/generation_graph.py` | **重构** | 新增 fetch_images / run_qa 节点 |
| `config.py` | **修改** | 新增 PPT 相关配置项 |
| `core/schemas.py` | **修改** | PptGenerateRequest 新增 enable_images |
| `services/generation.py` | **修改** | 传递新参数到 Graph |
| `tests/test_ppt_complex.py` | **新建** | 完整测试套件 (7 项) |
