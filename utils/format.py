import json
import re


def safe_json_parse(raw: str) -> dict:
    """尝试解析 JSON，失败时用正则提取 JSON 块后重试。"""
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
