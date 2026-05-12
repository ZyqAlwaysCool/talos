from __future__ import annotations

import asyncio
import inspect
import json
from time import monotonic
from typing import Any, AsyncGenerator, Awaitable, cast

from loguru import logger

from agents.infra.llm.thinking.redis_stream_sink import RedisStreamThinkingSink
from agents.infra.sse.models import TaskThinkingSnapshot
from agents.infra.sse.registry import TaskThinkingResolverRegistry
from core.config.config_center import get_app_config
from core.task.models.task_models import TaskStatus
from core.task.redis_queue import create_redis_client


class ThinkingSSEService:
    _THINKING_SSE_CHUNK_SIZE = 128
    # 兜底状态轮询不需要高频，降低频率可减少对业务查询接口的资源竞争。
    _THINKING_STATUS_POLL_INTERVAL_SECONDS = 10.0
    _TERMINAL_TASK_STATUSES = {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }

    def __init__(self, resolver_registry: TaskThinkingResolverRegistry):
        self.resolver_registry = resolver_registry

    async def stream_task_thinking(
        self,
        task_id: str,
        trace_id: str,
    ) -> AsyncGenerator[str, None]:
        config = get_app_config()
        if not config.thinking_stream_enabled:
            yield self._format_sse_event(
                "error",
                {
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "message": "Thinking stream is disabled by service config.",
                },
            )
            return

        resolver = self.resolver_registry.get_resolver(task_id)
        if resolver is None:
            yield self._format_sse_event(
                "error",
                {
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "message": "No thinking resolver registered for this task prefix.",
                },
            )
            return

        initial_snapshot = await self._safe_resolve_task_snapshot(resolver, task_id)
        if initial_snapshot is None:
            yield self._format_sse_event(
                "error",
                {
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "message": "Failed to resolve task status.",
                },
            )
            return
        if not initial_snapshot.exists:
            yield self._format_sse_event(
                "error",
                {
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "message": "Task not found.",
                },
            )
            return
        if not initial_snapshot.thinking_stream_enabled:
            yield self._format_sse_event(
                "warning",
                {
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "message": "Thinking stream is not enabled for this task.",
                },
            )

        redis_client = create_redis_client(config)
        stream_key = RedisStreamThinkingSink.build_stream_key(
            task_id=task_id,
            stream_prefix=config.thinking_channel_prefix,
        )
        logger.info(
            "Thinking stream reader started. task_id={} stream_key={} trace_id={}",
            task_id,
            stream_key,
            trace_id,
        )

        yield self._format_sse_event(
            "ready",
            {
                "task_id": task_id,
                "trace_id": trace_id,
                "stream_key": stream_key,
            },
        )
        last_ping_time = monotonic()
        last_status_poll_time = 0.0
        last_event_id = "0-0"

        try:
            while True:
                entries = await self._xread_stream_entries(
                    redis_client=redis_client,
                    stream_key=stream_key,
                    last_event_id=last_event_id,
                    count=100,
                    block_ms=3000,
                )
                if entries:
                    for event_id, payload in entries:
                        last_event_id = event_id
                        event_name = payload.get("event", "node_thinking_delta")
                        for event_payload in self._split_sse_thinking_payload(
                            event_name=event_name,
                            payload=payload,
                            chunk_size=self._THINKING_SSE_CHUNK_SIZE,
                        ):
                            yield self._format_sse_event(event_name, event_payload)
                        if event_name == "task_done":
                            return
                else:
                    now = monotonic()
                    if (
                        now - last_status_poll_time
                        >= self._THINKING_STATUS_POLL_INTERVAL_SECONDS
                    ):
                        last_status_poll_time = now
                        terminal_done_payload = await self._build_terminal_done_payload(
                            resolver=resolver,
                            task_id=task_id,
                        )
                        if terminal_done_payload is not None:
                            logger.warning(
                                "Thinking stream fallback task_done emitted. task_id={} trace_id={} payload={}",
                                task_id,
                                trace_id,
                                terminal_done_payload,
                            )
                            yield self._format_sse_event("task_done", terminal_done_payload)
                            return
                    if now - last_ping_time >= 5:
                        yield self._format_sse_event(
                            "ping",
                            {
                                "task_id": task_id,
                                "trace_id": trace_id,
                                "last_event_id": last_event_id,
                            },
                        )
                        last_ping_time = now
                    await asyncio.sleep(0.05)
        except Exception as exc:
            logger.exception(
                "Thinking stream failed. task_id={} trace_id={} error={}",
                task_id,
                trace_id,
                str(exc),
            )
            yield self._format_sse_event(
                "error",
                {
                    "task_id": task_id,
                    "trace_id": trace_id,
                    "message": str(exc),
                },
            )
        finally:
            await redis_client.aclose()
            logger.info(
                "Thinking stream reader closed. task_id={} stream_key={} trace_id={}",
                task_id,
                stream_key,
                trace_id,
            )

    async def _build_terminal_done_payload(
        self,
        *,
        resolver: Any,
        task_id: str,
    ) -> dict[str, Any] | None:
        snapshot = await self._safe_resolve_task_snapshot(resolver, task_id)
        if snapshot is None:
            return None
        return self._build_done_payload_from_snapshot(snapshot)

    async def _safe_resolve_task_snapshot(
        self,
        resolver: Any,
        task_id: str,
    ) -> TaskThinkingSnapshot | None:
        try:
            return await resolver.resolve(task_id)
        except Exception as exc:
            logger.warning(
                "Thinking stream status resolve failed. task_id={} error={}",
                task_id,
                str(exc),
            )
            return None

    @classmethod
    def _build_done_payload_from_snapshot(
        cls, snapshot: TaskThinkingSnapshot
    ) -> dict[str, Any] | None:
        if not snapshot.exists:
            return None
        task_status = cls._normalize_task_status(snapshot.status)
        if task_status not in cls._TERMINAL_TASK_STATUSES:
            return None
        failed_reason = snapshot.failed_reason if task_status == TaskStatus.FAILED.value else ""
        return {
            "task_status": task_status,
            "failed_reason": str(failed_reason or ""),
        }

    @staticmethod
    def _normalize_task_status(raw_status: Any) -> str:
        status_value = getattr(raw_status, "value", raw_status)
        if status_value is None:
            return ""
        return str(status_value).strip().lower()

    @staticmethod
    def _format_sse_event(event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    async def _xread_stream_entries(
        redis_client: Any,
        stream_key: str,
        last_event_id: str,
        *,
        count: int,
        block_ms: int,
    ) -> list[tuple[str, dict[str, Any]]]:
        xread_fn = getattr(redis_client, "xread", None)
        if callable(xread_fn):
            xread_result = xread_fn(
                {stream_key: last_event_id},
                count=count,
                block=block_ms,
            )
            if not inspect.isawaitable(xread_result):
                raise TypeError("Redis xread returned non-awaitable result")
            raw_data = await cast(Awaitable[Any], xread_result)
        else:
            raw_data = await redis_client.execute_command(
                "XREAD",
                "COUNT",
                str(count),
                "BLOCK",
                str(block_ms),
                "STREAMS",
                stream_key,
                last_event_id,
            )
        return ThinkingSSEService._normalize_xread_response(raw_data)

    @staticmethod
    def _normalize_xread_response(raw_data: Any) -> list[tuple[str, dict[str, Any]]]:
        if not raw_data:
            return []
        normalized: list[tuple[str, dict[str, Any]]] = []
        for stream_item in raw_data:
            if not isinstance(stream_item, (list, tuple)) or len(stream_item) < 2:
                continue
            entries = stream_item[1] or []
            for entry in entries:
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                event_id = ThinkingSSEService._decode_text(entry[0]) or ""
                fields = ThinkingSSEService._normalize_stream_fields(entry[1])
                raw_payload = fields.get("data", "")
                payload = ThinkingSSEService._parse_json_payload(raw_payload)
                if event_id:
                    normalized.append((event_id, payload))
        return normalized

    @staticmethod
    def _normalize_stream_fields(raw_fields: Any) -> dict[str, str]:
        if isinstance(raw_fields, dict):
            return {
                ThinkingSSEService._decode_text(key): ThinkingSSEService._decode_text(
                    value
                )
                for key, value in raw_fields.items()
            }
        if isinstance(raw_fields, (list, tuple)):
            fields: dict[str, str] = {}
            for index in range(0, len(raw_fields), 2):
                if index + 1 >= len(raw_fields):
                    break
                key = ThinkingSSEService._decode_text(raw_fields[index])
                value = ThinkingSSEService._decode_text(raw_fields[index + 1])
                fields[key] = value
            return fields
        return {}

    @staticmethod
    def _parse_json_payload(raw_payload: str) -> dict[str, Any]:
        if not raw_payload:
            return {}
        try:
            parsed = json.loads(raw_payload)
        except (TypeError, ValueError):
            return {"event": "node_thinking_delta", "payload": {"raw": str(raw_payload)}}
        if isinstance(parsed, dict):
            return parsed
        return {"event": "node_thinking_delta", "payload": {"raw": parsed}}

    @staticmethod
    def _decode_text(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        if value is None:
            return ""
        return str(value)

    @staticmethod
    def _split_sse_thinking_payload(
        *,
        event_name: str,
        payload: dict[str, Any],
        chunk_size: int,
    ) -> list[dict[str, Any]]:
        # 仅对增量思维事件做拆分，节点边界事件必须保持单条原子语义。
        if event_name != "node_thinking_delta":
            return [payload]
        event_payload = payload.get("payload")
        if not isinstance(event_payload, dict):
            return [payload]
        delta = event_payload.get("delta")
        if not isinstance(delta, str) or not delta:
            return [payload]

        normalized_chunk_size = max(1, int(chunk_size))
        if len(delta) <= normalized_chunk_size:
            return [payload]

        chunks = [
            delta[index:index + normalized_chunk_size]
            for index in range(0, len(delta), normalized_chunk_size)
        ]
        total_chunks = len(chunks)
        split_payloads: list[dict[str, Any]] = []
        for chunk_index, chunk in enumerate(chunks, start=1):
            split_event_payload = dict(event_payload)
            split_event_payload["delta"] = chunk
            split_event_payload["chunk_index"] = chunk_index
            split_event_payload["chunk_total"] = total_chunks
            split_payload = dict(payload)
            split_payload["payload"] = split_event_payload
            split_payloads.append(split_payload)
        return split_payloads
