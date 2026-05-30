"""RabbitMQ 消费者 — 异步消费文档生成任务。

启动后连接 RabbitMQ，声明拓扑，逐条消费消息后交给 ReAct Agent 自主编排生成流程。
ACK/NACK / 重试 / 进度通知均按 RABBITMQ_ASYNC_PROTOCOL.md v1.0 执行。
"""

from __future__ import annotations

import asyncio
import json
import time as _time_mod
from pathlib import Path
from typing import Any

import aio_pika
from loguru import logger

from config import settings
from broker.schemas import (
    TaskMessage,
    TaskCallback,
    TaskProgress,
    SUPPORTED_VERSIONS,
    VALID_DOC_TYPES,
)

MAX_RETRIES = 3

# ── 可重试异常 → 协议错误码 ──
_RETRYABLE_ERROR_CODE = {
    "LLMCallError": 6001,       # LLM 服务错误
    "FileUploadError": 5007,    # 文件上传失败
}

# ── BirdHelp 异常 → 协议错误码 (非重试) ──
_NON_RETRYABLE_ERROR_CODE = {
    "ValidationError": 1005,            # 字段值不合法
    "QuotaInsufficientError": 2001,     # 额度不足
    "LLMParseError": 5001,              # 大纲生成失败
    "FileGenerationError": 5003,        # 文件构建失败
    "MaterialIngestionError": 6004,     # RAG 检索失败
    "InternalError": 9999,              # 未知
}


class GenerationConsumer:
    """RabbitMQ 文档生成消费者。"""

    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._queue: aio_pika.RobustQueue | None = None
        self._consume_tag: str | None = None
        self._running = False

    # ── 公开方法 ──

    async def start(self) -> None:
        """建立连接、声明拓扑、开始消费。"""
        self._running = True
        url = (
            f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}"
            f"@{settings.rabbitmq_host}:{settings.rabbitmq_port}"
            f"/{settings.rabbitmq_vhost.lstrip('/')}"
        )
        logger.info(f"Connecting to RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")

        self._connection = await aio_pika.connect_robust(url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=settings.rabbitmq_prefetch)

        # 声明交换机和队列（幂等，Java 端可能已创建）
        exchange = await self._channel.declare_exchange(
            settings.rabbitmq_exchange, aio_pika.ExchangeType.TOPIC, durable=True,
        )
        self._exchange = exchange

        # 死信交换机
        dlx = await self._channel.declare_exchange(
            "birdhelp.doc.generation.dlx", aio_pika.ExchangeType.TOPIC, durable=True,
        )
        dlq = await self._channel.declare_queue(
            "birdhelp.doc.generation.dlq", durable=True,
        )
        await dlq.bind(dlx, "doc.generate.dlq")

        # 主队列
        queue = await self._channel.declare_queue(
            settings.rabbitmq_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": "birdhelp.doc.generation.dlx",
                "x-dead-letter-routing-key": "doc.generate.dlq",
                "x-message-ttl": 600000,
                "x-max-priority": 10,
            },
        )
        for rk in ("doc.generate.ppt", "doc.generate.word", "doc.generate.pdf"):
            await queue.bind(exchange, rk)

        self._queue = queue
        self._consume_tag = await queue.consume(self._on_message)

        logger.info(f"RabbitMQ consumer ready, queue={settings.rabbitmq_queue}, prefetch={settings.rabbitmq_prefetch}")

    async def stop(self) -> None:
        """优雅关闭：取消消费 → 关闭通道 → 关闭连接。"""
        self._running = False
        logger.info("Stopping RabbitMQ consumer ...")
        try:
            if self._queue and self._consume_tag:
                await self._queue.cancel(self._consume_tag)
        except Exception as exc:
            logger.warning(f"Error cancelling consumer: {exc}")
        try:
            if self._channel:
                await self._channel.close()
        except Exception as exc:
            logger.warning(f"Error closing channel: {exc}")
        try:
            if self._connection:
                await self._connection.close()
        except Exception as exc:
            logger.warning(f"Error closing connection: {exc}")
        logger.info("RabbitMQ consumer stopped")

    # ── 消息处理 ──

    async def _on_message(self, message: aio_pika.IncomingMessage) -> None:
        """消息入口，回调在 RabbitMQ channel 的 asyncio 上下文中执行。"""
        try:
            await self._process_message(message)
        except Exception:
            logger.exception("Unhandled exception in message processing, NACK to DLQ")
            try:
                await message.nack(requeue=False)
            except Exception:
                pass

    async def _process_message(self, message: aio_pika.IncomingMessage) -> None:
        """消息处理主逻辑，按协议分阶段执行。"""
        task_msg: TaskMessage | None = None
        start_ms = int(_time_mod.monotonic() * 1000)

        try:
            # ── 阶段 1: 解析与校验 ──
            task_msg = self._parse_and_validate(message)
        except _NonRetryableError as exc:
            logger.error(f"[{task_msg.task_id if task_msg else '?'}] Parse/validate failed: {exc}")
            await self._send_failure_callback(task_msg, exc.code, exc.message, start_ms)
            await message.nack(requeue=False)
            return

        logger.info(f"[{task_msg.task_id}] Received: docType={task_msg.doc_type} topic={task_msg.topic[:40]}")

        # ── 阶段 2: 扣减额度 ──
        try:
            await self._consume_quota(task_msg)
        except _NonRetryableError as exc:
            logger.warning(f"[{task_msg.task_id}] Quota error: [{exc.code}] {exc.message}")
            await self._send_failure_callback(task_msg, exc.code, exc.message, start_ms)
            await message.ack()  # 额度问题不重试
            return

        # ── 阶段 3: 生成文档 ──
        file_path = ""
        graph_result: dict[str, Any] = {}
        try:
            file_path, graph_result = await self._run_generation(task_msg, message)
        except _RetryableError as exc:
            retry_count = self._get_retry_count(message)
            if retry_count >= MAX_RETRIES:
                logger.error(f"[{task_msg.task_id}] Max retries ({MAX_RETRIES}) reached: {exc}")
                await self._send_failure_callback(task_msg, exc.code, exc.message, start_ms)
                await message.nack(requeue=False)
            else:
                logger.info(f"[{task_msg.task_id}] Retryable error (retry={retry_count+1}/{MAX_RETRIES}): {exc}")
                await self._re_enqueue(message, retry_count + 1)
            return
        except _NonRetryableError as exc:
            logger.error(f"[{task_msg.task_id}] Generation failed: [{exc.code}] {exc.message}")
            await self._refund_quota(task_msg)
            await self._send_failure_callback(task_msg, exc.code, exc.message, start_ms)
            await message.ack()
            return

        # ── 阶段 4: 上传文件到 Java ──
        await self._send_progress(task_msg, "uploading_file", 98, "正在上传文件...")
        try:
            upload_result = await self._upload_file(file_path, task_msg)
        except _RetryableError as exc:
            retry_count = self._get_retry_count(message)
            if retry_count >= MAX_RETRIES:
                logger.error(f"[{task_msg.task_id}] Upload max retries reached")
                await self._send_failure_callback(task_msg, exc.code, exc.message, start_ms)
                await message.nack(requeue=False)
            else:
                logger.info(f"[{task_msg.task_id}] Upload retryable (retry={retry_count+1}/{MAX_RETRIES})")
                await self._re_enqueue(message, retry_count + 1)
            self._cleanup_file(file_path)
            return
        except _NonRetryableError as exc:
            logger.error(f"[{task_msg.task_id}] Upload non-retryable: {exc}")
            await self._send_failure_callback(task_msg, exc.code, exc.message, start_ms)
            await message.ack()
            self._cleanup_file(file_path)
            return

        # ── 阶段 5: 回调成功 ──
        try:
            await self._send_success_callback(task_msg, upload_result, graph_result, start_ms)
        except Exception as exc:
            logger.error(f"[{task_msg.task_id}] Success callback failed (non-fatal): {exc}")

        self._cleanup_file(file_path)
        await message.ack()
        logger.info(f"[{task_msg.task_id}] Completed successfully")

    # ── 解析与校验 ──

    @staticmethod
    def _parse_and_validate(message: aio_pika.IncomingMessage) -> TaskMessage:
        """解析 JSON 并校验必填字段。失败抛出 _NonRetryableError。"""
        # JSON 解析
        try:
            body = json.loads(message.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise _NonRetryableError(1001, f"消息 JSON 解析失败: {exc}") from exc

        # Pydantic 校验
        try:
            task_msg = TaskMessage.model_validate(body)
        except Exception as exc:
            raise _NonRetryableError(1002, f"消息字段校验失败: {exc}") from exc

        # 版本校验
        if task_msg.version not in SUPPORTED_VERSIONS:
            raise _NonRetryableError(1003, f"不支持的协议版本: {task_msg.version}")

        # docType 校验
        if task_msg.doc_type not in VALID_DOC_TYPES:
            raise _NonRetryableError(1004, f"不支持的文档类型: {task_msg.doc_type}")

        # 枚举值校验
        if task_msg.style not in {"academic", "business", "creative", "minimal", "tech", "warm"}:
            raise _NonRetryableError(1005, f"不支持的风格: {task_msg.style}")
        if task_msg.language not in {"zh", "en"}:
            raise _NonRetryableError(1005, f"不支持的语言: {task_msg.language}")

        return task_msg

    # ── 额度 ──

    @staticmethod
    async def _consume_quota(task_msg: TaskMessage) -> None:
        """扣减用户额度。失败抛出 _NonRetryableError。"""
        from client.quota import consume_quota
        try:
            result = await consume_quota(int(task_msg.user_id), task_msg.callback_id)
        except Exception as exc:
            raise _NonRetryableError(2002, f"额度扣减接口异常: {exc}") from exc
        if result.get("code") != 0:
            raise _NonRetryableError(2001, result.get("message", "额度不足"))

    @staticmethod
    async def _refund_quota(task_msg: TaskMessage) -> None:
        """退还额度，失败仅记日志。"""
        from client.quota import refund_quota
        try:
            await refund_quota(int(task_msg.user_id), task_msg.callback_id)
            logger.info(f"[{task_msg.task_id}] Quota refunded")
        except Exception as exc:
            logger.error(f"[{task_msg.task_id}] Quota refund failed: {exc}")

    # ── 生成 ──

    async def _run_generation(
        self, task_msg: TaskMessage, message: aio_pika.IncomingMessage,
    ) -> tuple[str, dict[str, Any]]:
        """执行 Agent 驱动的文档生成。Agent 通过 ReAct 模式自主编排工具调用。

        使用 graph.agent.AgentOrchestrator（ReAct Agent）替代原有的固定 StateGraph：
        Agent 拥有 6 个工具（retrieve_knowledge / generate_outline / render_charts /
        fetch_images / evaluate_quality / build_document），自主决定调用顺序和重试。
        进度通过 AgentProgressCallback 在工具调用开始时推送。
        """
        from graph.agent import get_agent_orchestrator
        from utils.file import ensure_temp_dir

        ensure_temp_dir()

        state = {
            "user_id": task_msg.user_id,
            "project_id": task_msg.project_id,
            "topic": task_msg.topic,
            "language": task_msg.language,
            "extra_prompt": task_msg.extra_prompt or "",
            "rag_enabled": task_msg.rag_enabled,
            "material_ids": task_msg.material_ids or [],
            "doc_type": task_msg.doc_type,
            "doc_subtype": task_msg.doc_subtype,
            "style": task_msg.style,
            "slide_count": task_msg.slide_count,
            "word_count": task_msg.word_count,
            "enable_images": task_msg.enable_images,
            # LLM 配置由 Java 端注入，透传到 Agent → Tools → Chain → create_chat_model()
            "llm_config": {
                "api_key": task_msg.api_key,
                "base_url": task_msg.base_url,
                "model_name": task_msg.model_name,
            },
        }

        try:
            orchestrator = get_agent_orchestrator(
                progress_sender=self._send_progress,
            )
            graph_result = await orchestrator.run(state, task_msg=task_msg)
        except Exception as exc:
            raise _map_exception(exc)

        if graph_result.get("error"):
            raise _NonRetryableError(5002, f"大纲验证失败: {graph_result['error']}")

        file_path = graph_result.get("file_path", "")
        if not file_path:
            raise _NonRetryableError(5003, "生成的文件路径为空")

        return file_path, graph_result

    # ── 上传 ──

    @staticmethod
    async def _upload_file(file_path: str, task_msg: TaskMessage) -> dict:
        """上传生成文件到 Java 后端。失败抛出 _RetryableError。"""
        from client.file import upload
        try:
            user_id = int(task_msg.user_id)
            project_id = int(task_msg.project_id)
            doc_type = task_msg.doc_type
            ext_map = {"ppt": ".pptx", "word": ".docx", "pdf": ".pdf"}
            ext = ext_map.get(doc_type, ".pptx")
            file_name = f"{task_msg.topic}{ext}"
            result = await upload(file_path, user_id, project_id, file_name)
            return result
        except Exception as exc:
            raise _RetryableError(5007, f"文件上传失败: {exc}") from exc

    # ── 进度推送 ──

    @staticmethod
    async def _send_progress(
        task_msg: TaskMessage, stage: str, progress: int, message: str,
    ) -> None:
        """推送任务进度到 Java。失败仅记日志，不阻塞主流程。"""
        from client.task import progress as send_progress
        from broker.schemas import TaskProgress

        prog = TaskProgress(
            task_id=task_msg.task_id,
            callback_id=task_msg.callback_id,
            stage=stage,
            progress=progress,
            message=message,
        )
        try:
            await send_progress(prog)
            logger.debug(f"[{task_msg.task_id}] Progress: {stage} ({progress}%) - {message}")
        except Exception as exc:
            logger.warning(f"[{task_msg.task_id}] Progress push failed ({stage}): {exc}")

    # ── 回调 ──

    @staticmethod
    async def _send_success_callback(
        task_msg: TaskMessage,
        upload_result: dict,
        graph_result: dict[str, Any],
        start_ms: int,
    ) -> None:
        """发送完成回调到 Java。"""
        from client.task import callback as send_callback

        data = upload_result.get("data", {}) if isinstance(upload_result, dict) else {}
        file_id = data.get("id")
        file_url = data.get("file_url") or data.get("fileUrl") or ""

        qa_info = GenerationConsumer._extract_qa_info(graph_result)

        elapsed = int(_time_mod.monotonic() * 1000) - start_ms
        cb = TaskCallback(
            task_id=task_msg.task_id,
            callback_id=task_msg.callback_id,
            user_id=int(task_msg.user_id),
            project_id=int(task_msg.project_id),
            status="completed",
            file_id=file_id,
            file_url=file_url,
            file_name=data.get("fileName", ""),
            qa_lowest_score=qa_info.get("lowest"),
            qa_passed_count=qa_info.get("passed"),
            qa_total_count=qa_info.get("total"),
            generation_time_ms=elapsed,
            error_code=0,
            error_message="",
        )
        await send_callback(cb)
        logger.info(f"[{task_msg.task_id}] Success callback sent, fileId={file_id}, elapsed={elapsed}ms")

    @staticmethod
    async def _send_failure_callback(
        task_msg: TaskMessage | None,
        error_code: int,
        error_message: str,
        start_ms: int,
    ) -> None:
        """发送失败回调到 Java。task_msg 为 None 时仅记日志。"""
        if task_msg is None:
            logger.error(f"Cannot send failure callback: task_msg is None ({error_code}: {error_message})")
            return

        from client.task import callback as send_callback

        elapsed = int(_time_mod.monotonic() * 1000) - start_ms
        cb = TaskCallback(
            task_id=task_msg.task_id,
            callback_id=task_msg.callback_id,
            user_id=int(task_msg.user_id),
            project_id=int(task_msg.project_id),
            status="failed",
            generation_time_ms=elapsed,
            error_code=error_code,
            error_message=error_message,
        )
        try:
            await send_callback(cb)
            logger.info(f"[{task_msg.task_id}] Failure callback sent, code={error_code}")
        except Exception as exc:
            logger.error(f"[{task_msg.task_id}] Failure callback itself failed: {exc}")

    # ── 重试 ──

    @staticmethod
    def _get_retry_count(message: aio_pika.IncomingMessage) -> int:
        """从消息 header 读取 x-retry-count。"""
        if message.headers:
            return message.headers.get("x-retry-count", 0)
        return 0

    async def _re_enqueue(self, message: aio_pika.IncomingMessage, new_count: int) -> None:
        """重新发布消息到原队列并 ACK 原始消息，实现延迟重试。"""
        headers = dict(message.headers) if message.headers else {}
        headers["x-retry-count"] = new_count

        new_msg = aio_pika.Message(
            body=message.body,
            headers=headers,
            content_type=message.content_type or "application/json",
            delivery_mode=message.delivery_mode or aio_pika.DeliveryMode.PERSISTENT,
            priority=message.priority or 0,
            message_id=message.message_id,
        )
        await self._exchange.publish(
            new_msg, routing_key=message.routing_key,
        )
        await message.ack()

    # ── QA 信息提取 ──

    @staticmethod
    def _extract_qa_info(graph_result: dict[str, Any]) -> dict[str, int | None]:
        """从 graph_result 提取 QA 评分摘要。"""
        reports = graph_result.get("qa_reports", [])
        if not reports:
            return {"lowest": None, "passed": None, "total": None}

        scores = []
        for r in reports:
            score = r.get("score", 0)
            if score is not None:
                scores.append(score)

        if not scores:
            return {"lowest": None, "passed": None, "total": None}

        passed = sum(1 for s in scores if s >= settings.ppt_qa_score_threshold)
        return {
            "lowest": min(scores),
            "passed": passed,
            "total": len(scores),
        }

    # ── 文件清理 ──

    @staticmethod
    def _cleanup_file(file_path: str) -> None:
        """删除临时生成文件。"""
        if not file_path:
            return
        try:
            p = Path(file_path)
            if p.exists():
                p.unlink()
        except Exception as exc:
            logger.warning(f"Failed to cleanup temp file {file_path}: {exc}")


# ── 异常类型 ──

class _RetryableError(Exception):
    """可重试错误（需要 NACK requeue=true）。"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class _NonRetryableError(Exception):
    """不可重试错误（直接 ACK 或 NACK requeue=false）。"""
    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _map_exception(exc: Exception) -> Exception:
    """将 BirdHelpError 子类映射为 _RetryableError 或 _NonRetryableError。"""
    class_name = exc.__class__.__name__

    if class_name == "LLMCallError":
        return _RetryableError(6001, str(exc))
    if class_name == "FileUploadError":
        return _RetryableError(5007, str(exc))

    code = _NON_RETRYABLE_ERROR_CODE.get(class_name, 9999)
    return _NonRetryableError(code, str(exc))
