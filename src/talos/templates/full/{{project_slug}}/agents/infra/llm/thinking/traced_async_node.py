'''
Description: 
Author: zyq
Date: 2026-04-16 17:52:15
LastEditors: zyq
LastEditTime: 2026-04-22 18:12:02
'''
from __future__ import annotations

from typing import Any

from agents.infra.llm.thinking.runtime import (
    THINKING_TRACE_RUNTIME_SHARED_KEY,
    ThinkingTraceRuntime,
)
from loguru import logger
from pocketflow import AsyncNode


class TracedAsyncNode(AsyncNode):
    TRACE_NODE_DISPLAY_NAME: str = ""

    def __init__(self, *, node_display_name: str = "") -> None:
        super().__init__()
        self._node_display_name = node_display_name

    def get_trace_node_display_name(self, shared: dict[str, Any]) -> str:
        _ = shared
        if self._node_display_name:
            return self._node_display_name
        class_display_name = getattr(self.__class__, "TRACE_NODE_DISPLAY_NAME", "")
        return str(class_display_name or "")

    async def _run_async(self, shared: dict[str, Any]) -> Any:
        runtime = shared.get(THINKING_TRACE_RUNTIME_SHARED_KEY)
        if runtime is None or not isinstance(runtime, ThinkingTraceRuntime):
            return await super()._run_async(shared)

        # workflow节点也发start/end/error，前端可重建完整业务树。
        parent_node_exec_id = runtime.get_flow_parent_node_exec_id()
        node_context = runtime.build_node_context(
            node_name=self.__class__.__name__,
            node_display_name=self.get_trace_node_display_name(shared), # 预留的动态设置节点名称的入口. 子类可覆盖写, self.get_trace_node_display_name(shared)会调用子类覆盖的方法
            node_type="workflow",
            parent_node_exec_id=parent_node_exec_id,
        )
        # 把当前workflow节点设为后续节点的父节点，实现执行链式层级。
        runtime.set_flow_parent_node_exec_id(node_context.node_exec_id)
        sink_available = await runtime.safe_sink_call("on_node_start", node_context)
        token = runtime.bind_workflow_node_context(node_context)

        logger.info(f"start node. node={node_context.node_display_name}")
        try:
            prep_res = await self.prep_async(shared)
            exec_res = await self._exec(prep_res)
            post_res = await self.post_async(shared, prep_res, exec_res)
        except Exception as exc:
            if sink_available:
                await runtime.safe_sink_call(
                    "on_node_error",
                    node_context,
                    str(exc),
                )
            raise
        finally:
            runtime.reset_workflow_node_context(token)

        if sink_available:
            await runtime.safe_sink_call("on_node_end", node_context)
        return post_res
