from __future__ import annotations

import json
import inspect
from time import time
from typing import Any, Awaitable, cast

from agents.infra.llm.context import ThinkingContext
from core.task.redis_queue import RedisClient


class RedisStreamThinkingSink:
    def __init__(
        self,
        redis_client: RedisClient,
        stream_prefix: str = "agents:thinking",
        stream_maxlen: int = 4000,
        delta_chunk_size: int = 128,
    ):
        self.redis_client = redis_client
        self.stream_prefix = stream_prefix
        self.stream_maxlen = max(100, int(stream_maxlen))
        # 统一在sink层做delta拆分，保证不同agent/producer复用时都能获得细粒度事件。
        self.delta_chunk_size = max(1, int(delta_chunk_size))

    @staticmethod
    def build_stream_key(task_id: str, stream_prefix: str = "agents:thinking") -> str:
        safe_task_id = task_id or "unknown"
        return f"{stream_prefix}:{{{safe_task_id}}}"

    def get_stream_key(self, task_id: str) -> str:
        return self.build_stream_key(task_id=task_id, stream_prefix=self.stream_prefix)

    async def _xadd(self, stream_key: str, message_json: str) -> None:
        xadd_fn = getattr(self.redis_client, "xadd", None)
        if callable(xadd_fn):
            xadd_result = xadd_fn(
                stream_key,
                {"data": message_json},
                maxlen=self.stream_maxlen,
                approximate=True,
            )
            if inspect.isawaitable(xadd_result):
                await cast(Awaitable[Any], xadd_result)
                return
            raise TypeError("Redis xadd returned non-awaitable result")
        await self.redis_client.execute_command(
            "XADD",
            stream_key,
            "MAXLEN",
            "~",
            str(self.stream_maxlen),
            "*",
            "data",
            message_json,
        )

    async def _publish(
        self,
        event: str,
        context: ThinkingContext,
        payload: dict[str, Any] | None = None,
    ) -> None:
        message = {
            "event": event,
            "task_id": context.task_id,
            "agent_name": context.agent_name,
            "workflow_name": context.workflow_name,
            "node_name": context.node_name,
            "node_display_name": context.node_display_name,
            "prompt_name": context.prompt_name,
            "trace_id": context.trace_id,
            "run_id": context.run_id,
            "attempt": int(context.attempt),
            "node_exec_id": context.node_exec_id,
            "parent_node_exec_id": context.parent_node_exec_id,
            "node_seq": int(context.node_seq),
            "node_type": context.node_type,
            "ts": int(time()),
            "payload": payload or {},
        }
        stream_key = self.get_stream_key(context.task_id)
        await self._xadd(stream_key, json.dumps(message, ensure_ascii=False))

    async def on_node_start(self, context: ThinkingContext) -> None:
        await self._publish(event="node_start", context=context)

    async def on_node_delta(self, context: ThinkingContext, delta: str) -> None:
        for delta_chunk in self._split_delta(delta):
            await self._publish(
                event="node_thinking_delta",
                context=context,
                payload={"delta": delta_chunk},
            )

    async def on_node_end(self, context: ThinkingContext) -> None:
        await self._publish(event="node_end", context=context)

    async def on_node_error(self, context: ThinkingContext, error_message: str) -> None:
        await self._publish(
            event="node_error",
            context=context,
            payload={"message": error_message},
        )

    async def emit_done(
        self,
        context: ThinkingContext,
        task_status: str,
        failed_reason: str = "",
    ) -> None:
        await self._publish(
            event="task_done",
            context=context,
            payload={"task_status": task_status, "failed_reason": failed_reason},
        )

    def _split_delta(self, delta: str) -> list[str]:
        if not delta:
            return []
        return [
            delta[index:index + self.delta_chunk_size]
            for index in range(0, len(delta), self.delta_chunk_size)
        ]
