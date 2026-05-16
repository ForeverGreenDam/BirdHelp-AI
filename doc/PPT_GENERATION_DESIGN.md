# PPT 生成功能设计文档

> v1.0 | 2026-05-14 | Phase 3

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
  │
  ├─ chains/ppt_chain.py  ← Prompt 模板 + LLM 调用 + JSON 解析
  │
  ▼
generator/ppt.py         ← python-pptx 构建 .pptx 文件
  │
  ▼
client/file.py           ← RSA-SHA256 签名上传到 Java 后端存储
```

分层职责：

| 层 | 文件 | 职责 |
|----|------|------|
| API | `api/ppt.py` | HTTP 端点，接收 `PptGenerateRequest`，返回 `ApiResponse` |
| 服务 | `services/generation.py` | 业务编排：额度 `consume` / `refund`、图调用、文件上传 |
| 图 | `graph/generation_graph.py` | LangGraph 状态图，编排 RAG → Chain → 校验 → 重试 |
| Chain | `chains/ppt_chain.py` | Prompt 模板 + ChatOpenAI 调用 + JSON 结构化输出 |
| 生成器 | `generator/ppt.py` | python-pptx 构建，继承 `BaseGenerator` |

---

## 二、LangChain Chain 设计

### 2.1 `chains/ppt_chain.py` — PptChain

**类结构：**

```python
class PptChain:
    prompt: ChatPromptTemplate   # 懒加载
    chain: Runnable              # prompt | ChatOpenAI | StrOutputParser
    async ainvoke(inputs) -> dict  # 返回解析后的结构化大纲
```

**Prompt 设计：**

- **System Prompt**：专业演示文稿设计专家角色 + JSON 输出格式约束 + 布局枚举定义 + 风格指南（academic/business/creative）
- **Human Message**：注入 `{topic}`、`{slide_count}`、`{language}`、`{style}`、`{context}`（RAG 参考）、`{extra_prompt}`（用户补充指令）

**输出 JSON Schema：**

```json
{
  "title": "演示文稿主标题",
  "slides": [
    {
      "title": "页面标题",
      "subtitle": "副标题（可选）",
      "content": ["要点1", "要点2"],
      "layout": "title_and_content",
      "notes": "演讲备注（可选）"
    }
  ]
}
```

**layout 枚举 → python-pptx SlideLayout 映射：**

| layout 值 | 说明 | 布局索引 |
|-----------|------|---------|
| `title_slide` | 标题页 | 0 |
| `title_and_content` | 标题 + 内容（默认） | 1 |
| `section_header` | 章节过渡页 | 2 |
| `two_content` | 左右双栏 | 3 |
| `blank` | 空白页（用于结束页） | 6 |

**解析策略**：复用 `utils/format.py` 中的 `safe_json_parse()`（直接解析 → 代码块提取 → 裸 JSON 正则）

---

## 三、LangGraph 状态图设计

### 3.1 状态 (`GenerationState`)

```python
class GenerationState(dict):
    user_id: str
    project_id: str
    topic: str
    style: str
    slide_count: int
    language: str
    extra_prompt: str
    rag_enabled: bool
    material_ids: list[str]
    context: str           # RAG 检索结果
    chain_output: str      # LLM 原始输出
    parsed_outline: dict   # 解析后大纲
    attempt: int           # 当前重试次数
    file_path: str         # 生成的文件路径
    error: str             # 错误信息
```

### 3.2 节点

| 节点 | 职责 |
|------|------|
| `retrieve_context` | 若 `rag_enabled=True`，调用 `retrieve_formatted()` 获取格式化参考文本 |
| `generate_outline` | 创建 `PptChain`，调用 `chain.ainvoke()` 生成 + 解析大纲 |
| `validate_outline` | 校验 `parsed_outline` 含 `title` + `slides` ≥ 2 页；失败则递增 `attempt` |
| `build_pptx` | `PptGenerator.generate(outline, temp_path)` 构建 .pptx |
| `handle_error` | 记录最终错误信息 |

### 3.3 条件路由

```
START → retrieve_context → generate_outline → validate_outline
                                                   │
                                     ┌─ 通过 ──→ build_pptx → END
                                     ├─ 失败 + attempt < 3 ──→ generate_outline
                                     └─ 失败 + attempt ≥ 3 ──→ handle_error → END
```

路由函数 `_route_after_validate()` 返回 `"build"` / `"retry"` / `"error"`。

---

## 四、文件生成器设计

### 4.1 `generator/ppt.py` — PptGenerator

继承 `BaseGenerator`，覆写 `output_extension = ".pptx"` 和 `generate()`。

**生成流程：**

1. 解析输入 JSON 大纲
2. 创建 `Presentation()` 对象（16:9）
3. 遍历 `slides`：
   - 根据 `layout` 选择 `prs.slide_layouts[index]`
   - 设置标题（`slide.shapes.title`）、副标题（独立 textbox）、正文（项目符号段落）
   - `two_content` 布局自动分流到左右两个 textbox
   - 写入演讲备注 (`slide.notes_slide`)
   - 添加页码（`index / total`）
4. 根据 `style` 应用配色/字体（见下表）
5. `prs.save(output_path)`

**风格配色：**

| style | 标题色 | 正文字体 | 风格描述 |
|-------|--------|---------|---------|
| `academic` | 深蓝 #1A3C6E | 黑体/宋体 | 严谨正式、结构清晰 |
| `business` | 深蓝 #1B3A5C | 微软雅黑 | 专业简洁、数据驱动 |
| `creative` | 暖红 #E04A36 | 微软雅黑 | 活泼视觉化、故事性强 |

---

## 五、业务编排设计

### 5.1 `services/generation.py` — generate_ppt()

**流程：**

```
1. int(user_id), int(callback_id) → 类型转换
2. consume_quota(user_id_int, related_id)      ← 扣额度
3. graph.ainvoke(initial_state)                ← 运行 LangGraph
4. check result["error"]                       ← 检查是否失败
5. upload_file(file_path, ...)                 ← 上传到 Java
6. return upload_result                        ← 返回 file_id/url
   ── 任何异常:
      refund_quota(user_id_int, related_id)    ← 退额度
      raise FileGenerationError
   ── finally:
      unlink(temp_file)                        ← 清理临时文件
```

---

## 六、API 设计

### 6.1 端点

```
POST /ai/ppt/generate
Content-Type: application/json
X-Timestamp / X-Nonce / X-Signature (RSA-SHA256)
```

**请求体** (`PptGenerateRequest` 继承 `GenerateRequest`)：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_id` | str | 是 | 用户 ID |
| `project_id` | str | 是 | 项目 ID |
| `topic` | str | 是 | 文档主题 |
| `language` | str | 否 | zh/en，默认 zh |
| `extra_prompt` | str | 否 | 用户补充指令 |
| `material_ids` | list[str] | 否 | RAG 素材 ID 列表 |
| `rag_enabled` | bool | 否 | 是否启用 RAG，默认 false |
| `callback_id` | str | 是 | 关联 Java 后端请求 ID |
| `style` | str | 否 | academic/business/creative，默认 academic |
| `slide_count` | int | 否 | 1–50，默认 10 |

**响应** (`ApiResponse`)：

```json
{
  "code": 0,
  "message": "success",
  "data": { "file_id": ..., "file_url": "..." }
}
```

---

## 七、配额管理

```
开始
  │
  ▼
consume_quota(user_id, related_id=callback_id)
  │
  ├─ 生成成功 → 上传文件 → 返回（额度不退还）
  │
  └─ 生成失败 → refund_quota(user_id, related_id) → 抛出异常
```

注意：`consume_quota` / `refund_quota` 的 `user_id` 参数为 `int`，需从请求的 `str` 转换。

---

## 八、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `generator/ppt.py` | 新建 | python-pptx 构建器，继承 `BaseGenerator` |
| `chains/ppt_chain.py` | 新建 | Prompt + LLM + JSON 解析 |
| `graph/generation_graph.py` | 新建 | LangGraph 状态图 |
| `services/generation.py` | 新建 | 业务编排 |
| `api/ppt.py` | 新建 | `POST /ai/ppt/generate` |
| `api/router.py` | 修改 | 注册 `ppt_router` |
| `doc/PPT_GENERATION_DESIGN.md` | 新建 | 本文档 |
