"""格式化工具 — LLM JSON 输出安全解析。"""

import json
import re


def safe_json_parse(raw: str) -> dict:
    """多策略解析 LLM 输出的 JSON。

    依次尝试: 直接解析 → 提取 ```json 代码块 → 提取裸 JSON 对象。
    所有策略失败时抛出 ValueError。
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 尝试匹配 ```json ... ``` 或裸 {...}
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        return json.loads(m.group(0))
    raise ValueError("无法从 LLM 输出中提取有效 JSON")
