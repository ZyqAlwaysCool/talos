from __future__ import annotations

import inspect
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from agents.infra.llm.context import ThinkingContext
from agents.infra.llm.thinking.composite_sink import CompositeThinkingSink
from agents.infra.llm.thinking.redis_stream_sink import RedisStreamThinkingSink
from agents.infra.workflow_archive.collector import WorkflowArchiveCollector
from agents.infra.workflow_archive.mapper import (
    build_workflow_nodes_view,
    load_workflow_archive,
)
from core.config.config_center import AppConfig
from core.task.base.repository import BaseTaskRepository
from core.task.redis_queue import RedisClient, create_redis_client
from loguru import logger


@dataclass(slots=True)
class ThinkingArchiveRuntime:
    """thinking 实时流与归档的运行时装配器。

    该对象由 task entry 在任务开始时构建，并在任务结束时负责：
    1) 向 sink 发送 done 终态事件；
    2) 将归档快照持久化到任务 metadata；
    3) 释放底层连接资源（Redis）。
    """

    enabled: bool
    thinking_sink: Any | None
    thinking_context: ThinkingContext | None
    archive_collector: WorkflowArchiveCollector | None
    redis_client: RedisClient | None
    run_id: str = ""
    attempt: int = 1

    @classmethod
    async def build(
        cls,
        *,
        repository: BaseTaskRepository,
        config: AppConfig,
        task_id: str,
        trace_id: str,
        request_enable: bool,
        task_retry_context: dict[str, Any] | None,
        agent_name: str,
        workflow_name: str,
    ) -> ThinkingArchiveRuntime:
        """构建运行时依赖，并返回可直接注入 workflow 的 runtime。

        开关策略：仅当「请求开启」且「全局开启」同时满足时才启用。
        启用后会组装组合 sink：实时流 Redis sink + 归档 collector。
        """
        enabled = bool(request_enable and config.thinking_stream_enabled)
        if not enabled:
            return cls(
                enabled=False,
                thinking_sink=None,
                thinking_context=None,
                archive_collector=None,
                redis_client=None,
            )

        redis_client = create_redis_client(config)
        try:
            redis_stream_sink = RedisStreamThinkingSink(
                redis_client=redis_client,
                stream_prefix=config.thinking_channel_prefix,
            )
            existing_task = await repository.get_task(task_id)
            existing_archive = None
            if existing_task and isinstance(existing_task.metadata, dict):
                existing_archive = existing_task.metadata.get("workflow_archive")

            # run_id 按"任务 + attempt + 随机后缀"生成，用于区分整任务重放轮次。
            attempt = cls._resolve_retry_attempt(task_retry_context)
            run_id = f"{task_id}:attempt:{attempt}:{uuid4().hex[:8]}"
            thinking_context = ThinkingContext(
                task_id=task_id,
                agent_name=agent_name,
                workflow_name=workflow_name,
                trace_id=trace_id,
                run_id=run_id,
                attempt=attempt,
                parent_node_exec_id=f"{run_id}:root",
            )
            archive_collector = WorkflowArchiveCollector(
                archive=load_workflow_archive(
                    existing_archive,
                    task_id=task_id,
                    agent_name=agent_name,
                    workflow_name=workflow_name,
                )
            )
            # 所有节点事件只上报一次，再由组合sink统一分发到实时流与归档。
            thinking_sink = CompositeThinkingSink([redis_stream_sink, archive_collector])
            return cls(
                enabled=True,
                thinking_sink=thinking_sink,
                thinking_context=thinking_context,
                archive_collector=archive_collector,
                redis_client=redis_client,
                run_id=run_id,
                attempt=attempt,
            )
        except Exception:
            await redis_client.aclose()
            raise

    async def emit_done(self, *, task_status: str, failed_reason: str = "") -> None:
        """向 sink 广播任务终态事件。

        该方法是"任务级收口"入口：用于通知实时流结束并触发归档 run 收尾。
        """
        if not self.enabled or self.thinking_sink is None or self.thinking_context is None:
            return
        emit_done = getattr(self.thinking_sink, "emit_done", None)
        if not callable(emit_done):
            return
        emit_done_result = emit_done(
            self.thinking_context,
            task_status=task_status,
            failed_reason=failed_reason,
        )
        if not inspect.isawaitable(emit_done_result):
            return
        await cast(Awaitable[Any], emit_done_result)

    async def finalize_retry_failure(
        self,
        *,
        failed_reason: str,
        final_task_status: str,
    ) -> None:
        """在"将被队列重试"的失败场景下，先收口当前 run 的归档。

        这里不写任务终态 failed，而是保留任务整体状态为 processing，
        以便下一轮重放继续复用同一 task_id 的历史归档。
        """
        if not self.enabled or self.archive_collector is None or self.thinking_context is None:
            return
        await self.archive_collector.finalize_run(
            context=self.thinking_context,
            run_status="failed",
            failed_reason=failed_reason,
            final_task_status=final_task_status,
        )

    async def persist_archive(
        self,
        *,
        repository: BaseTaskRepository,
        task_id: str,
    ) -> None:
        """持久化 workflow_archive 与 workflow_nodes 视图到任务 metadata。"""
        if not self.enabled or self.archive_collector is None:
            return
        archive = self.archive_collector.snapshot()
        run_count = len(archive.runs)
        node_count = sum(len(run.nodes) for run in archive.runs)
        logger.info(
            "Persist workflow archive begin. task_id={} run_id={} latest_run_id={} runs={} nodes={} final_task_status={}",
            task_id,
            self.run_id,
            archive.latest_run_id,
            run_count,
            node_count,
            archive.final_task_status,
        )
        # 强校验：thinking 开启后，归档不应为空；否则说明事件链路未完整落到归档侧。
        if run_count <= 0:
            raise RuntimeError(
                f"Empty workflow archive before persist. task_id={task_id} run_id={self.run_id}"
            )
        workflow_nodes = build_workflow_nodes_view(archive)
        updated = await repository.update_metadata_fields(
            task_id,
            fields={
                "workflow_archive": archive.model_dump(mode="json"),
                "workflow_nodes": [node.model_dump(mode="json") for node in workflow_nodes],
            },
        )
        # 强校验：写库失败时必须显式失败，避免业务成功但查询端拿到空归档。
        if not updated:
            raise RuntimeError(
                f"Persist workflow archive failed. task_id={task_id} run_id={self.run_id}"
            )
        logger.info(
            "Persist workflow archive success. task_id={} run_id={} workflow_nodes={}",
            task_id,
            self.run_id,
            len(workflow_nodes),
        )

    async def aclose(self) -> None:
        """释放 runtime 持有的外部资源（当前为 Redis 连接）。"""
        if self.redis_client is None:
            return
        await self.redis_client.aclose()

    @staticmethod
    def _resolve_retry_attempt(task_retry_context: dict[str, Any] | None) -> int:
        """从队列重试上下文解析 attempt，兜底为 1。"""
        if not task_retry_context:
            return 1
        try:
            return max(1, int(task_retry_context.get("job_try", 1)))
        except (TypeError, ValueError):
            logger.warning(
                "Invalid retry context job_try, fallback to 1. task_retry_context={}",
                task_retry_context,
            )
            return 1
