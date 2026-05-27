"""ChatModel 工厂，统一创建 LLM 客户端实例。"""

from typing import Any

from langchain_openai import ChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler
from loguru import logger

from config import settings

# 用于区分不同 LLM 调用的计数器
_call_counter: int = 0


class _LlmLoggingHandler(BaseCallbackHandler):
    """LangChain 回调处理器：记录每次 LLM 调用的 prompt 和响应。"""

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        global _call_counter
        _call_counter += 1
        call_id = _call_counter
        for i, prompt in enumerate(prompts):
            prompt_len = len(prompt)
            preview = prompt[:800] if prompt_len > 800 else prompt
            suffix = "..." if prompt_len > 800 else ""
            logger.info(
                f"[LLM #{call_id}] Prompt #{i+1}/{len(prompts)} "
                f"(length={prompt_len}):\n{preview}{suffix}"
            )

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        call_id = _call_counter
        try:
            generations = response.generations
            for gen_idx, gen_list in enumerate(generations):
                for msg_idx, gen in enumerate(gen_list):
                    text = gen.text if hasattr(gen, "text") else str(gen.message.content) if hasattr(gen, "message") else str(gen)
                    text_len = len(text) if text else 0
                    logger.info(
                        f"[LLM #{call_id}] Response gen[{gen_idx}][{msg_idx}] "
                        f"(length={text_len}):\n{text}"
                    )
        except Exception:
            logger.info(f"[LLM #{call_id}] Response (raw): {response}")

        # 记录 token 用量
        try:
            llm_output = response.llm_output
            if llm_output and "token_usage" in llm_output:
                usage = llm_output["token_usage"]
                logger.info(
                    f"[LLM #{call_id}] Token usage: "
                    f"prompt={usage.get('prompt_tokens', '?')}, "
                    f"completion={usage.get('completion_tokens', '?')}, "
                    f"total={usage.get('total_tokens', '?')}"
                )
        except Exception:
            pass

    def on_llm_error(self, error: Exception, **kwargs: Any) -> None:
        logger.error(f"[LLM #{_call_counter}] Error: {error}")


def create_chat_model() -> ChatOpenAI:
    """基于全局配置创建 ChatOpenAI 实例。

    兼容 DeepSeek/通义千问/GPT-4o 等 OpenAI 兼容 API。
    内置 LLM 日志回调，记录每次调用的 prompt 与响应。
    """
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
        timeout=settings.llm_timeout,
        callbacks=[_LlmLoggingHandler()],
    )
