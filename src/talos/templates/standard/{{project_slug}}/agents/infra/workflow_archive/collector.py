from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

from agents.infra.llm.context import ThinkingContext
from agents.infra.workflow_archive.schemas import (
    WorkflowArchive,
    WorkflowArchiveNode,
    WorkflowArchiveRun,
)

RunStatus = Literal["processing", "completed", "failed", "cancelled"]
TaskStatus = Literal["pending", "processing", "completed", "failed", "cancelled"]
NodeType = Literal["workflow", "llm"]


class WorkflowArchiveCollector:
    """内存态归档收集器：把离散 thinking 事件汇聚为可持久化的 workflow 结构。"""

    def __init__(self, archive: WorkflowArchive):
        """初始化 collector，并从已有归档重建索引。

        说明：
        - 同一 task 可能多次重放（多 run），因此需要 run/node 双层索引。
        - 使用异步锁保证并发节点写入时的数据一致性。
        """
        self.archive = archive
        self._lock = asyncio.Lock()
        self._runs_by_id: dict[str, WorkflowArchiveRun] = {}
        self._nodes_by_run: dict[str, dict[str, WorkflowArchiveNode]] = {}
        self._rebuild_index()

    async def on_node_start(self, context: ThinkingContext) -> None:
        """处理节点开始事件：确保 run/node 存在并标记为 processing。"""
        async with self._lock:
            run = self._get_or_create_run(context)
            node = self._get_or_create_node(run, context)
            node.node_status = "process"
            if not node.started_at:
                node.started_at = self._utc_now_iso()

    async def on_node_delta(self, context: ThinkingContext, delta: str) -> None:
        """处理 thinking 增量：按 node 维度持续追加内容。"""
        if not delta:
            return
        async with self._lock:
            run = self._get_or_create_run(context)
            node = self._get_or_create_node(run, context)
            node.node_content += delta

    async def on_node_end(self, context: ThinkingContext) -> None:
        """处理节点结束事件：非失败节点收口为 completed。"""
        async with self._lock:
            run = self._get_or_create_run(context)
            node = self._get_or_create_node(run, context)
            if node.node_status != "failed":
                node.node_status = "completed"
            if not node.ended_at:
                node.ended_at = self._utc_now_iso()

    async def on_node_error(self, context: ThinkingContext, error_message: str) -> None:
        """处理节点异常事件：记录失败原因并写入结束时间。"""
        async with self._lock:
            run = self._get_or_create_run(context)
            node = self._get_or_create_node(run, context)
            node.node_status = "failed"
            node.error_message = str(error_message or "")
            if not node.ended_at:
                node.ended_at = self._utc_now_iso()

    async def emit_done(
        self,
        context: ThinkingContext,
        task_status: str,
        failed_reason: str = "",
    ) -> None:
        """兼容 sink 协议的任务级 done 入口，内部统一转 finalize_run。"""
        await self.finalize_run(
            context=context,
            run_status=task_status,
            failed_reason=failed_reason,
            final_task_status=task_status,
        )

    async def finalize_run(
        self,
        *,
        context: ThinkingContext,
        run_status: str,
        failed_reason: str = "",
        final_task_status: str = "",
    ) -> None:
        """收口一次 run，并更新 archive 的任务级最新状态指针。"""
        async with self._lock:
            run = self._get_or_create_run(context)
            normalized_run_status = self._normalize_run_status(run_status)
            run.run_status = normalized_run_status
            run.failed_reason = str(failed_reason or "")
            if not run.ended_at:
                run.ended_at = self._utc_now_iso()

            normalized_task_status = self._normalize_task_status(
                final_task_status or run_status
            )
            self.archive.final_task_status = normalized_task_status
            self.archive.latest_run_id = run.run_id
            if normalized_run_status == "completed":
                self.archive.latest_success_run_id = run.run_id

    def snapshot(self) -> WorkflowArchive:
        """返回归档快照副本，避免调用方意外修改内部状态。"""
        return WorkflowArchive(**self.archive.model_dump())

    def _rebuild_index(self) -> None:
        """基于 archive.runs 重建 run/node 快速索引。"""
        self._runs_by_id.clear()
        self._nodes_by_run.clear()
        for run in self.archive.runs:
            self._runs_by_id[run.run_id] = run
            self._nodes_by_run[run.run_id] = {node.node_id: node for node in run.nodes}

    def _get_or_create_run(self, context: ThinkingContext) -> WorkflowArchiveRun:
        """按 context.run_id 获取或创建 run。"""
        run_id = context.run_id or f"{self.archive.task_id}:run"
        existing_run = self._runs_by_id.get(run_id)
        if existing_run is not None:
            return existing_run

        now = self._utc_now_iso()
        attempt = max(1, int(context.attempt))
        run_root_id = context.parent_node_exec_id or f"{run_id}:root"
        run = WorkflowArchiveRun(
            run_id=run_id,
            attempt=attempt,
            run_status="processing",
            run_root_id=run_root_id,
            started_at=now,
        )
        self.archive.runs.append(run)
        self._runs_by_id[run_id] = run
        self._nodes_by_run[run_id] = {}
        self.archive.latest_run_id = run_id
        if not self.archive.agent_name and context.agent_name:
            self.archive.agent_name = context.agent_name
        if not self.archive.workflow_name and context.workflow_name:
            self.archive.workflow_name = context.workflow_name
        return run

    def _get_or_create_node(
        self,
        run: WorkflowArchiveRun,
        context: ThinkingContext,
    ) -> WorkflowArchiveNode:
        """按 context.node_exec_id 获取或创建节点，并维护父子关系字段。"""
        node_id = context.node_exec_id or f"{run.run_id}:node:unknown"
        nodes = self._nodes_by_run.setdefault(run.run_id, {})
        existing_node = nodes.get(node_id)
        if existing_node is not None:
            # 关键逻辑：同一节点可能收到多次事件，保持同一对象累积thinking，避免覆盖。
            if not existing_node.node_name and context.node_name:
                existing_node.node_name = context.node_name
            if not existing_node.node_display_name:
                existing_node.node_display_name = (
                    context.node_display_name
                    or context.node_name
                    or context.prompt_name
                )
            if not existing_node.prompt_name and context.prompt_name:
                existing_node.prompt_name = context.prompt_name
            return existing_node

        parent_node_id = context.parent_node_exec_id or run.run_root_id
        node = WorkflowArchiveNode(
            node_id=node_id,
            parent_node_id=parent_node_id,
            node_name=context.node_name or context.prompt_name,
            # 展示名优先取显式字段，缺失时回退到技术名，保证历史数据兼容展示。
            node_display_name=(
                context.node_display_name or context.node_name or context.prompt_name
            ),
            prompt_name=context.prompt_name,
            node_type=self._normalize_node_type(context.node_type),
            node_status="pending",
            node_seq=max(0, int(context.node_seq)),
        )
        run.nodes.append(node)
        nodes[node_id] = node
        return node

    @staticmethod
    def _normalize_node_type(node_type: str) -> NodeType:
        """标准化节点类型，当前仅保留 workflow / llm 两类。"""
        if node_type == "llm":
            return "llm"
        return "workflow"

    @staticmethod
    def _normalize_run_status(run_status: str) -> RunStatus:
        """标准化 run 状态，未知值回退为 processing。"""
        normalized = str(run_status or "").strip().lower()
        if normalized == "completed":
            return "completed"
        if normalized == "failed":
            return "failed"
        if normalized == "cancelled":
            return "cancelled"
        if normalized == "processing":
            return "processing"
        if normalized in {"pending", "process"}:
            return "processing"
        return "processing"

    @staticmethod
    def _normalize_task_status(task_status: str) -> TaskStatus:
        """标准化任务状态，确保写库状态枚举一致。"""
        normalized = str(task_status or "").strip().lower()
        if normalized == "pending":
            return "pending"
        if normalized == "processing":
            return "processing"
        if normalized == "completed":
            return "completed"
        if normalized == "failed":
            return "failed"
        if normalized == "cancelled":
            return "cancelled"
        if normalized == "process":
            return "processing"
        return "processing"

    @staticmethod
    def _utc_now_iso() -> str:
        """返回 UTC ISO 时间字符串，作为归档时间基准。"""
        return datetime.now(timezone.utc).isoformat()
