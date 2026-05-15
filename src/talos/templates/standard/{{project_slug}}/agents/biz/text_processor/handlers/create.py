"""text_processor 域：创建任务 handler。"""

from __future__ import annotations

from typing import Any

from agents.biz.text_processor.repository.task_repository import (
    TextProcessorTaskRepository,
)
from agents.biz.text_processor.schemas import TextProcessorCreateRequest
from agents.biz.text_processor.workflow.task_entry import run_text_processor_task
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus, generate_task_id
from loguru import logger

TEXT_PROCESSOR_TASK = "text_processor"
TEXT_PROCESSOR_COLLECTION = "text_processor_tasks"


class TextProcessorTaskCreateHandler:
    def __init__(self) -> None:
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        self.queue_backend = queue_backend
        self.repository = TextProcessorTaskRepository(storage_backend)

    async def create(self, payload: dict[str, Any], trace_id: str = "") -> str:
        body = {k: v for k, v in payload.items() if k != "task_type"}
        request = TextProcessorCreateRequest(**body)
        task_id = generate_task_id(prefix=TEXT_PROCESSOR_TASK)

        metadata = request.model_dump()
        metadata["collection_type"] = TEXT_PROCESSOR_COLLECTION
        if trace_id:
            metadata["trace_id"] = trace_id

        created = await self.repository.create_task(task_id, metadata)
        if not created:
            raise Exception("Failed to create text_processor task")

        task = await self.repository.get_task(task_id)
        if task is None:
            raise Exception(f"Task not found after create: {task_id}")

        try:
            queue_task_id = await self.queue_backend.enqueue_task(
                task, run_text_processor_task,
                text=request.text, options=request.options,
            )
        except Exception as exc:
            logger.error("text_processor task enqueue failed, task orphaned: {} | {}", task_id, str(exc))
            try:
                await self.repository.update_status(
                    task_id, TaskStatus.FAILED, error_message=f"Enqueue failed: {str(exc)}"
                )
            except Exception as comp_exc:
                logger.error("Enqueue failure compensation also failed: {} | {}", task_id, str(comp_exc))
            raise

        await self.repository.update_status(task_id, TaskStatus.PENDING, queue_task_id=queue_task_id)
        logger.info("text_processor task created: {}", task_id)
        return task_id
