"""text_processor 域：思维链解析 handler。"""

from __future__ import annotations

from agents.biz.text_processor.repository.task_repository import (
    TextProcessorTaskRepository,
)
from agents.infra.schemas.task_thinking import TaskThinkingSnapshot
from core.task.base.storage_backend import StorageBackend
from core.task.factory import TaskManagerFactory


class TextProcessorTaskThinkingResolver:
    def __init__(self, storage: StorageBackend | None = None) -> None:
        resolved_storage = storage if storage is not None else TaskManagerFactory.create_mongo_storage()
        self.repository = TextProcessorTaskRepository(resolved_storage)

    async def resolve(self, task_id: str) -> TaskThinkingSnapshot:
        task = await self.repository.get_task(task_id)
        if task is None:
            return TaskThinkingSnapshot(task_id=task_id, exists=False)
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        task_status = getattr(task.status, "value", task.status)
        failed_reason = metadata.get("failed_reason") or task.error_message or ""
        return TaskThinkingSnapshot(
            task_id=task_id,
            exists=True,
            status=str(task_status or ""),
            failed_reason=str(failed_reason or ""),
            thinking_stream_enabled=False,
        )
