"""text_processor 域：查询任务 handler。"""

from __future__ import annotations

from typing import Any

from agents.biz.text_processor.repository.task_repository import (
    TextProcessorTaskRepository,
)
from agents.biz.text_processor.schemas import TextProcessorQueryResponseData
from agents.infra.query.result import (
    normalize_task_status,
    task_query_err,
    task_query_ok,
)
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus

TEXT_PROCESSOR_TASK = "text_processor"
TASK_NOT_FOUND = 10001


class TextProcessorTaskQueryHandler:
    def __init__(self) -> None:
        storage_backend = TaskManagerFactory.create_mongo_storage()
        self.repository = TextProcessorTaskRepository(storage_backend)

    async def __call__(self, task_id: str) -> tuple[int, str, dict[str, Any]]:
        task = await self.repository.get_task(task_id)
        if not task:
            return task_query_err(
                code=TASK_NOT_FOUND, msg="task not found",
                detail=TextProcessorQueryResponseData(
                    task_id=task_id,
                    task_status=TaskStatus.FAILED.value,
                    failed_reason="task not found",
                ).model_dump(),
            )

        metadata = task.metadata or {}
        failed_reason = metadata.get("failed_reason", "") or task.error_message or ""
        result = metadata.get("result", {})
        if task.result_data:
            result = task.result_data

        data = TextProcessorQueryResponseData(
            task_id=task.task_id,
            task_status=normalize_task_status(task),
            failed_reason=failed_reason,
            result=result,
        )
        return task_query_ok(data.model_dump())
