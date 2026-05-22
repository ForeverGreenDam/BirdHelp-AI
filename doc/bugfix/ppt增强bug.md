# PPT 图片显示 Bug 修复记录

**日期**：2026-05-22 ~ 2026-05-23  
**涉及文件**：13 个  
**修复 Bug 数**：6 个

---

## Bug 1：QA 质量评估完全失效（严重）

**现象**：生成日志中所有 10 页 QA 均报错 `Invalid format specifier in f-string template. Nested replacement fields are not allowed.`，QA 静默跳过，全部页面得默认 70 分，排版质量检查形同虚设。

**根因**：`chains/qa_chain.py` 和 `chains/word_qa_chain.py` 的 system prompt 中 JSON 示例使用了单花括号 `{"score": 85}`，LangChain 的 `ChatPromptTemplate` 将其解析为模板变量，格式化时崩溃。

**修复**：将 prompt 中 JSON 示例的 `{` `}` 全部改为 `{{` `}}`（LangChain 模板转义语法），与 `chains/ppt_chain.py` 保持一致。

**修改文件**：
- `chains/qa_chain.py`
- `chains/word_qa_chain.py`

---

## Bug 2：图片 key 不匹配 → 图片下载后无法找到（严重）

**现象**：图片下载成功（日志显示 `Image downloaded: doc_img_00-xxx.jpg`），但 PPT 中所有配图位置显示 `[配图区域]` 占位符。

**根因**：`graph/generation_graph.py:_fetch_images()` 存储图片时使用 key `img_00`、`img_01`（基于枚举序号），而 `generator/ppt/generator.py` 查找图片时使用 key `slide_01`、`slide_02`（基于 page_number）。前缀不同 + 索引方式不同（0-based vs 1-based），导致全部查找失败。

**修复**：统一 `_fetch_images()` 中的 key 为 `slide_{page_number:02d}` 格式，直接从 slide 数据的 `page_number` 字段取值，与生成器的查找逻辑完全对齐。

**修改文件**：
- `graph/generation_graph.py`

---

## Bug 3：QA 修复环节篡改 page_number

**现象**：Bug 2 修复后图片 key 对齐了，但部分 slide 仍显示占位符。日志显示图片下载了但 `images_map` 中 key 不全。

**根因**：`chains/qa_chain.py:_repair_slide()` 有两处缺陷：
1. 将 slide dict 通过 f-string 传给 LLM（`f"{slide}"`），输出为 Python repr 格式（单引号），而非合法 JSON
2. 修复后仅用 `setdefault("page_number", ...)` 保留页码，若 LLM 输出中显式写入了错误的 `page_number`，则 `setdefault` 不生效

**修复**：
- 改用 `json.dumps(slide)` 输出合法 JSON
- `setdefault` 改为 `repaired["page_number"] = ...` 强制覆盖
- prompt 中添加“page_number 必须保持为 N，不可修改”约束

**修改文件**：
- `chains/qa_chain.py`

---

## Bug 4：strategy 字段双重过滤导致图片被跳过

**现象**：Bug 3 修复后，部分 slide 有 `image_query` 但 `images_map` 中仍无对应 key，最终显示占位符。

**根因**：LLM 在某些 slide 上同时设置了 `visual_plan.strategy = "BASIC_GRAPHICS_ONLY"` 和有效的 `image_query`，数据自相矛盾。代码在两个地方以 strategy 为权威过滤掉了 image_query：

1. `graph/generation_graph.py:_fetch_images()`：`if strategy == "BASIC_GRAPHICS_ONLY": continue`
2. `generator/ppt/generator.py` 兜底占位图生成：`if strategy != "BASIC_GRAPHICS_ONLY": skip`

slide 被双重过滤，图片既不下载也不生成兜底占位图。

**修复**：移除两处 strategy 过滤，改为仅以 `image_query` 是否非空为准。规则从"strategy 决定一切"改为"LLM 给了 image_query 就一定有图"。

**修改文件**：
- `graph/generation_graph.py`
- `generator/ppt/generator.py`

---

## Bug 5：add_image() 静默失败（核心渲染 Bug）

**现象**：Bug 1-4 全部修复后，图片下载成功、key 匹配成功、`images=1` 传入渲染器，但图片仍不显示，只有 `[配图区域]` 占位符。

**根因**：`generator/ppt/shapes.py:add_image()` 的原生 `slide.shapes.add_picture()` 调用在 Docker 环境中返回异常后，PIL 裁剪路径的数据被 python-pptx 拒绝。异常被渲染器的 `except Exception: pass` 静默吞掉，直接绘制 `[配图区域]` 占位符。错误信息从未记录。

**修复**：
- 翻转 `add_image()` 的处理策略：先尝试 `slide.shapes.add_picture()` 原生 API（兼容性最好），失败再走 PIL 裁剪路径
- 两端均添加 `logger.warning` 记录失败原因
- 所有渲染器的 `except Exception: pass` 全部改为 `except Exception as exc: logger.warning(...)`

**修改文件**：
- `generator/ppt/shapes.py`
- `generator/ppt/layouts/text_image.py`

---

## Bug 6：6 个布局中仅 2 个支持图片（覆盖率不足）

**现象**：Bug 5 修复后，`text_image` 和 `two_column` 布局的图片正常显示，但 `grid_cards`、`timeline`、`image_full` 等其他布局的图片仍然丢失。

**根因**：以下渲染器接收 `images` 参数但完全忽略，不执行任何图片插入操作：
- `render_text_only`（以及回退到它的 `image_full` / `timeline` / `toc` / `quote`）
- `render_grid_cards`
- `render_cover`
- `render_section_header`
- `render_summary`

**修复**：为上述 5 个渲染器全部添加图片支持：

| 渲染器 | 图片放置策略 |
|--------|------------|
| `render_text_only` | 文字区收窄至 7 英寸，右侧 3.8 英寸插入配图 |
| `render_grid_cards` | 卡片行数 ≤ 2 时底部添加配图 |
| `render_cover`（3 变体） | gradient: 右侧配图 / split: 右半区上图下文 / minimal: 底部居中横幅 |
| `render_section_header`（3 变体）| left_bar: 右侧配图 / dark: 底部横幅 / numbered: 右侧配图 |
| `render_summary` | 标题上移，底部居中横幅配图 |

**修改文件**：
- `generator/ppt/layouts/text_only.py`
- `generator/ppt/layouts/grid_cards.py`
- `generator/ppt/layouts/cover.py`
- `generator/ppt/layouts/section_header.py`
- `generator/ppt/layouts/summary.py`
- `generator/ppt/layouts/two_column.py`

---

## 附带修复

### 双栏布局内容全在左栏
- **文件**：`generator/ppt/layouts/two_column.py`
- **根因**：渲染器将 `body` 数组按数量对半切分为左右两栏，LLM 不遵守此约定，常将左右内容合并为一个字符串
- **修复**：当 `body` 恰好 2 个元素时，视为 `[左栏内容, 右栏内容]`，每项按换行符拆分为要点

### PPT Chain prompt 增强
- **文件**：`chains/ppt_chain.py`
- 新增 two_column 双栏格式说明（body 必须 2 元素 + left_label/right_label）
- 新增图片覆盖率约束（至少 40% 内容页使用配图布局，纯文字页不超过 30%）

### QA 开关支持
- **文件**：`graph/generation_graph.py`
- 在 `_run_qa` 开头添加 `ppt_qa_enabled` 配置检查，设为 `False` 时跳过 QA（方便调试）

---

## 修改文件总览

| 文件 | 修改内容 |
|------|---------|
| `chains/qa_chain.py` | f-string 双花括号转义 + JSON 格式化 + page_number 强制覆盖 |
| `chains/word_qa_chain.py` | f-string 双花括号转义 |
| `chains/ppt_chain.py` | 双栏格式说明 + 图片覆盖率约束 |
| `graph/generation_graph.py` | 图片 key 对齐 + strategy 过滤移除 + QA 开关 + LLM 耗时日志 |
| `generator/ppt/generator.py` | strategy 过滤移除 + 兜底占位图生成 |
| `generator/ppt/shapes.py` | add_image 策略翻转 + 错误日志 |
| `generator/ppt/layouts/text_image.py` | 异常日志 |
| `generator/ppt/layouts/text_only.py` | 图片支持（右侧配图） |
| `generator/ppt/layouts/grid_cards.py` | 图片支持（底部配图） |
| `generator/ppt/layouts/cover.py` | 图片支持（三变体各自适配） |
| `generator/ppt/layouts/section_header.py` | 图片支持（三变体各自适配） |
| `generator/ppt/layouts/summary.py` | 图片支持（底部横幅） |
| `generator/ppt/layouts/two_column.py` | 双栏 body 格式修复 + 图片支持 |
