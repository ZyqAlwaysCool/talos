"""思维链 SSE 服务编排。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from time import monotonic

from agents.infra.llm.thinking.redis_stream_sink import RedisStreamThinkingSink
from agents.infra.registry.task_thinking import TaskThinkingResolverRegistry
from agents.infra.schemas.task_thinking import TaskThinkingSnapshot
from core.config.config_center import get_app_config
from core.task.models.task_models import TaskStatus
from core.task.redis_queue import create_redis_client
from loguru import logger


class ThinkingSSEService:
    _THINKING_SSE_CHUNK_SIZE = 128
    _THINKING_STATUS_POLL_INTERVAL_SECONDS = 10.0
    _TERMINAL_TASK_STATUSES = {
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.CANCELLED.value,
    }

    def __init__(self, resolver_registry: TaskThinkingResolverRegistry):
        self.resolver_registry = resolver_registry

    async def stream_task_thinking(
        self, task_id: str, trace_id: str,
    ) -> AsyncGenerator[str, None]:
        config = get_app_config()
        if not config.thinking_stream_enabled:
            yield self._format_sse_event("error", {
                "task_id": task_id, "trace_id": trace_id,
                "message": "Thinking stream is disabled by service config.",
            })
            return

        resolver = self.resolver_registry.get_resolver(task_id)
        if resolver is None:
            yield self._format_sse_event("error", {
                "task_id": task_id, "trace_id": trace_id,
                "message": "No thinking resolver registered for this task prefix.",
            })
            return

        initial_snapshot = await self._safe_resolve_task_snapshot(resolver, task_id)
        if initial_snapshot is None:
            yield self._format_sse_event("error", {
                "task_id": task_id, "trace_id": trace_id,
                "message": "Failed to resolve task status.",
            })
            return
        if not initial_snapshot.exists:
            yield self._format_sse_event("error", {
                "task_id": task_id, "trace_id": trace_id,
                "message": "Task not found.",
            })
            return

        redis_client = create_redis_client(config)
        stream_key = RedisStreamThinkingSink.build_stream_key(
            task_id=task_id, stream_prefix=config.thinking_channel_prefix,
        )
        yield self._format_sse_event("ready", {
            "task_id": task_id, "trace_id": trace_id, "stream_key": stream_key,
        })
        last_ping_time = monotonic()
        last_status_poll_time = 0.0
        last_event_id = "0-0"

        try:
            while True:
                entries = await self._xread_stream_entries(
                    redis_client=redis_client, stream_key=stream_key,
                    last_event_id=last_event_id, count=100, block_ms=3000,
                )
                if entries:
                    for event_id, payload in entries:
                        last_event_id = event_id
                        event_name = payload.get("event", "node_thinking_delta")
                        yield self._format_sse_event(event_name, payload)
                        if event_name == "task_done":
                            return
                else:
                    now = monotonic()
                    if now - last_status_poll_time >= self._THINKING_STATUS_POLL_INTERVAL_SECONDS:
                        last_status_poll_time = now
                        terminal_payload = await self._build_terminal_done_payload(
                            resolver=resolver, task_id=task_id,
                        )
                        if terminal_payload is not None:
                            yield self._format_sse_event("task_done", terminal_payload)
                            return
                    if now - last_ping_time >= 5:
                        yield self._format_sse_event("ping", {
                            "task_id": task_id, "trace_id": trace_id,
                            "last_event_id": last_event_id,
                        })
                        last_ping_time = now
                    await asyncio.sleep(0.05)
        except Exception as exc:
            logger.exception("Thinking stream failed. task_id={} trace_id={} error={}", task_id, trace_id, str(exc))
            yield self._format_sse_event("error", {
                "task_id": task_id, "trace_id": trace_id, "message": str(exc),
            })
        finally:
            await redis_client.aclose()

    # ... (remaining helper methods unchanged from original)

    async def _build_terminal_done_payload(self, *, resolver, task_id) -> dict | None:
        snapshot = await self._safe_resolve_task_snapshot(resolver, task_id)
        if snapshot is None:
            return None
        return self._build_done_payload_from_snapshot(snapshot)

    async def _safe_resolve_task_snapshot(self, resolver, task_id) -> TaskThinkingSnapshot | None:
        try:
            return await resolver.resolve(task_id)
        except Exception as exc:
            logger.warning("Thinking stream status resolve failed. task_id={} error={}", task_id, str(exc))
            return None

    @classmethod
    def _build_done_payload_from_snapshot(cls, snapshot: TaskThinkingSnapshot) -> dict | None:
        if not snapshot.exists:
            return None
        task_status = cls._normalize_task_status(snapshot.status)
        if task_status not in cls._TERMINAL_TASK_STATUSES:
            return None
        failed_reason = snapshot.failed_reason if task_status == TaskStatus.FAILED.value else ""
        return {"task_status": task_status, "failed_reason": str(failed_reason or "")}

    @staticmethod
    def _normalize_task_status(raw_status) -> str:
        status_value = getattr(raw_status, "value", raw_status)
        if status_value is None:
            return ""
        return str(status_value).strip().lower()

    @staticmethod
    def _format_sse_event(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    async def _xread_stream_entries(redis_client, stream_key, last_event_id, *, count, block_ms):
        raw_data = await redis_client.execute_command(
            "XREAD", "COUNT", str(count), "BLOCK", str(block_ms),
            "STREAMS", stream_key, last_event_id,
        )
        if not raw_data:
            return []
        result = []
        for stream_item in raw_data:
            if not isinstance(stream_item, (list, tuple)) or len(stream_item) < 2:
                continue
            entries = stream_item[1] or []
            for entry in entries:
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                event_id = entry[0].decode() if isinstance(entry[0], bytes) else str(entry[0])
                fields = entry[1]
                if isinstance(fields, (list, tuple)):
                    payload = {}
                    for i in range(0, len(fields), 2):
                        if i + 1 < len(fields):
                            k = fields[i].decode() if isinstance(fields[i], bytes) else str(fields[i])
                            v = fields[i+1].decode() if isinstance(fields[i+1], bytes) else str(fields[i+1])
                            payload[k] = json.loads(v) if k == "data" else v
                    if event_id:
                        data_field = payload.get("data", "{}")
                        parsed = json.loads(data_field) if isinstance(data_field, str) else data_field
                        result.append((event_id, parsed if isinstance(parsed, dict) else {}))
        return result
