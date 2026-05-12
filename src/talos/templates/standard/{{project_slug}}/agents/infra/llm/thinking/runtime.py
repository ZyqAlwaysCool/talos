from __future__ import annotations

import asyncio
import inspect
import itertools
from contextvars import ContextVar, Token
from typing import Any, Awaitable, cast

from loguru import logger

from agents.infra.llm.context import ThinkingContext
from agents.infra.llm.thinking.base import ThinkingSink

THINKING_TRACE_RUNTIME_SHARED_KEY = "__thinking_trace_runtime"

_CURRENT_WORKFLOW_NODE_CONTEXT: ContextVar[ThinkingContext | None] = ContextVar(
    "current_workflow_node_context",
    default=None,
)
_CURRENT_FLOW_PARENT_NODE_EXEC_ID: ContextVar[str] = ContextVar(
    "current_flow_parent_node_exec_id",
    default="",
)


def get_current_workflow_node_context() -> ThinkingContext | None:
    """获取当前协程上下文中的 workflow 节点上下文。"""
    return _CURRENT_WORKFLOW_NODE_CONTEXT.get()


class ThinkingTraceRuntime:
    """thinking 事件的运行时上下文管理器。

    核心职责：
    1) 为每个节点生成稳定的 node_exec_id / parent_node_exec_id / node_seq；
    2) 通过 ContextVar 维护当前执行链路的父子关系；
    3) 对 sink 调用做超时与异常隔离，避免拖慢业务主链路。
    """

    _SINK_TIMEOUT_SECONDS = 2.0

    def __init__(
        self,
        *,
        sink: ThinkingSink | None,
        base_context: ThinkingContext,
    ) -> None:
        """初始化 runtime。

        - sink: thinking 事件下发目标（可为空）
        - base_context: 当前任务级基础上下文（task/run/attempt 等）
        """
        self.sink = sink
        self.base_context = base_context
        # 单轮 run 内的节点序号计数器，用于前端稳定排序。
        self._node_seq_counter = itertools.count(start=1)

    def next_node_seq(self) -> int:
        """生成下一个节点序号（同一 run 内递增）。"""
        return next(self._node_seq_counter)

    def build_node_context(
        self,
        *,
        node_name: str,
        node_display_name: str = "",
        prompt_name: str = "",
        node_type: str,
        parent_node_exec_id: str = "",
    ) -> ThinkingContext:
        """构建节点级上下文。

        父节点解析优先级：
        1) 显式传入 parent_node_exec_id；
        2) 当前协程绑定的 workflow 节点（ContextVar）；
        3) base_context.parent_node_exec_id；
        4) run 根节点 {run_id}:root。
        """
        run_id = self.base_context.run_id or self.base_context.task_id or "run"
        node_seq = self.next_node_seq()
        node_exec_id = f"{run_id}:node:{node_seq}"
        resolved_parent_node_exec_id = (
            parent_node_exec_id
            or self._resolve_parent_node_exec_id(run_id=run_id)
        )
        return ThinkingContext(
            task_id=self.base_context.task_id,
            agent_name=self.base_context.agent_name,
            workflow_name=self.base_context.workflow_name,
            node_name=node_name,
            node_display_name=node_display_name,
            prompt_name=prompt_name,
            trace_id=self.base_context.trace_id,
            run_id=run_id,
            attempt=max(1, int(self.base_context.attempt)),
            node_exec_id=node_exec_id,
            parent_node_exec_id=resolved_parent_node_exec_id,
            node_seq=node_seq,
            node_type=node_type,
        )

    def get_root_node_exec_id(self) -> str:
        """返回当前 run 的根节点 ID。"""
        run_id = self.base_context.run_id or self.base_context.task_id or "run"
        if self.base_context.parent_node_exec_id:
            return self.base_context.parent_node_exec_id
        return f"{run_id}:root"

    def get_flow_parent_node_exec_id(self) -> str:
        """读取当前 flow 级父节点 ID（ContextVar）。"""
        return _CURRENT_FLOW_PARENT_NODE_EXEC_ID.get()

    def set_flow_parent_node_exec_id(self, node_exec_id: str) -> None:
        """直接写入当前 flow 级父节点 ID。"""
        _CURRENT_FLOW_PARENT_NODE_EXEC_ID.set(node_exec_id)

    def bind_flow_parent_node_exec_id(self, node_exec_id: str) -> Token:
        """绑定 flow 父节点并返回 token，供后续 reset 恢复。"""
        return _CURRENT_FLOW_PARENT_NODE_EXEC_ID.set(node_exec_id)

    @staticmethod
    def reset_flow_parent_node_exec_id(token: Token) -> None:
        """恢复 flow 父节点 ContextVar 到绑定前状态。"""
        _CURRENT_FLOW_PARENT_NODE_EXEC_ID.reset(token)

    def bind_workflow_node_context(self, context: ThinkingContext) -> Token:
        """绑定当前 workflow 节点上下文，供子节点自动继承父子关系。"""
        return _CURRENT_WORKFLOW_NODE_CONTEXT.set(context)

    @staticmethod
    def reset_workflow_node_context(token: Token) -> None:
        """恢复 workflow 节点上下文 ContextVar 到绑定前状态。"""
        _CURRENT_WORKFLOW_NODE_CONTEXT.reset(token)

    def _resolve_parent_node_exec_id(self, *, run_id: str) -> str:
        """解析父节点 ID，用于保证节点树层级关系可重建。"""
        active_context = get_current_workflow_node_context()
        if active_context is not None and active_context.node_exec_id:
            # 若当前已在某workflow节点内运行，子节点自动挂在该节点下。
            return active_context.node_exec_id
        if self.base_context.parent_node_exec_id:
            return self.base_context.parent_node_exec_id
        return f"{run_id}:root"

    async def safe_sink_call(
        self,
        call_name: str,
        context: ThinkingContext,
        *args: Any,
    ) -> bool:
        """安全调用 sink 方法。

        - 返回 True: sink 方法调用成功；
        - 返回 False: sink 不可用/方法不存在/调用失败/超时。
        """
        if self.sink is None:
            return False
        sink_call = getattr(self.sink, call_name, None)
        if not callable(sink_call):
            return False
        try:
            sink_result = sink_call(context, *args)
            if not inspect.isawaitable(sink_result):
                return False
            await asyncio.wait_for(
                cast(Awaitable[Any], sink_result),
                timeout=self._SINK_TIMEOUT_SECONDS,
            )
            return True
        except Exception as exc:
            logger.warning(
                "Trace runtime sink call failed. call={} task_id={} run_id={} node_exec_id={} error={}",
                call_name,
                context.task_id,
                context.run_id,
                context.node_exec_id,
                str(exc),
            )
            return False
