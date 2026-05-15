from __future__ import annotations

from agents.infra.workflow_archive.integration import ThinkingArchiveRuntime
from core.task.base.repository import BaseTaskRepository
from core.task.models.task_models import TaskStatus
from loguru import logger


async def emit_done_and_persist_archive(
    *,
    runtime: ThinkingArchiveRuntime | None,
    repository: BaseTaskRepository,
    task_id: str,
    task_status: str,
    failed_reason: str,
) -> None:
    if runtime is None or not runtime.enabled:
        return
    # 先持久化归档，再发送 done 事件。
    # 这样可以保证客户端一旦收到 done，查询接口已经可以读取到完整归档。
    await runtime.persist_archive(repository=repository, task_id=task_id)
    try:
        # 任务到达终态后，统一发送done事件通知流式消费者结束读取。
        await runtime.emit_done(task_status=task_status, failed_reason=failed_reason)
    except Exception as exc:
        logger.warning(
            "Failed to emit task done for thinking sink. task_id={} task_status={} error={}",
            task_id,
            task_status,
            str(exc),
        )


async def finalize_retry_failure_and_persist_archive(
    *,
    runtime: ThinkingArchiveRuntime | None,
    repository: BaseTaskRepository,
    task_id: str,
    failed_reason: str,
) -> None:
    if runtime is None or not runtime.enabled:
        return
    # 可重试失败场景先把当前run标记为failed并落库，避免历史轮次丢失。
    await runtime.finalize_retry_failure(
        failed_reason=failed_reason,
        final_task_status=TaskStatus.PROCESSING.value,
    )
    await runtime.persist_archive(repository=repository, task_id=task_id)
