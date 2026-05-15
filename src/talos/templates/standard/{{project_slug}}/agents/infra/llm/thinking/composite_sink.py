from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from agents.infra.llm.context import ThinkingContext
from loguru import logger


class CompositeThinkingSink:
    """组合 sink：将同一事件扇出到多个下游 sink。"""

    def __init__(self, sinks: Iterable[Any]):
        """初始化 fanout 目标集合，自动过滤空 sink。"""
        self._sinks = [sink for sink in sinks if sink is not None]

    async def on_node_start(self, context: ThinkingContext) -> None:
        """转发节点开始事件。"""
        await self._fan_out("on_node_start", context)

    async def on_node_delta(self, context: ThinkingContext, delta: str) -> None:
        """转发节点增量事件（thinking delta）。"""
        await self._fan_out("on_node_delta", context, delta)

    async def on_node_end(self, context: ThinkingContext) -> None:
        """转发节点结束事件。"""
        await self._fan_out("on_node_end", context)

    async def on_node_error(self, context: ThinkingContext, error_message: str) -> None:
        """转发节点异常事件。"""
        await self._fan_out("on_node_error", context, error_message)

    async def emit_done(
        self,
        context: ThinkingContext,
        task_status: str,
        failed_reason: str = "",
    ) -> None:
        """转发任务级 done 事件。"""
        await self._fan_out(
            "emit_done",
            context,
            task_status,
            failed_reason,
        )

    async def _fan_out(self, call_name: str, *args: Any) -> None:
        """并发扇出调用：同一事件同时下发至所有实现该方法的 sink。"""
        coroutines: list[Any] = []
        for sink in self._sinks:
            sink_call = getattr(sink, call_name, None)
            if callable(sink_call):
                coroutines.append(self._safe_call(sink_call, call_name, *args))
        if not coroutines:
            return
        await asyncio.gather(*coroutines)

    async def _safe_call(self, sink_call: Any, call_name: str, *args: Any) -> None:
        """单下游容错调用：某个 sink 失败不影响其他 sink。"""
        try:
            await sink_call(*args)
        except Exception as exc:
            logger.warning(
                "Composite sink call failed. call={} error={}",
                call_name,
                str(exc),
            )
