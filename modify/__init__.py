"""modify — 对话修改文档模块。

职责：基于现有大纲（从 Java 获取），通过 LLM 对话修改大纲，
然后重建文件并上传。不跑 QA（用户主观修改不应被拦截）。

按 §三 设计：
- api.py     → FastAPI Router: POST /ai/chat/modify, /ai/chat/discuss
- schemas.py → Pydantic 模型
- chain.py   → LLM 对话修改 Prompt + 结构化输出
- graph.py   → LangGraph 状态图（无 QA）
- client.py  → 调用 Java 内部 API
- parser.py  → 文档逆向解析（降级兜底）
- service.py → 业务编排
"""
