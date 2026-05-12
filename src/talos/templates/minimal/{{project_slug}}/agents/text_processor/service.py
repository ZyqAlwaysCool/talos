"""text_processor Agent 业务编排."""

from __future__ import annotations

from loguru import logger

from agents.text_processor.constants import TEXT_PROCESSOR_COLLECTION, TEXT_PROCESSOR_TASK_PREFIX
from agents.text_processor.repository.task_repository import TextProcessorTaskRepository
from agents.text_processor.schemas import TextProcessorQueryResponseData
from agents.text_processor.workflow.task_entry import run_text_processor_task
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus, generate_task_id


class TextProcessorService:
    """文本处理服务 — 负责创建任务、入队、查询."""

    def __init__(self):
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        self.queue_backend = queue_backend
        self.repository = TextProcessorTaskRepository(storage_backend)

    async def create_task(self, request, trace_id: str = "") -> str:
        task_id = generate_task_id(prefix=TEXT_PROCESSOR_TASK_PREFIX)
        metadata = {
            "text": request.text,
            "options": request.options,
            "collection_type": TEXT_PROCESSOR_COLLECTION,
        }
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
                task,
                run_text_processor_task,
                text=request.text,
                options=request.options,
            )
        except Exception as exc:
            logger.error(
                "text_processor 任务入队失败: {} | {}", task_id, str(exc)
            )
            try:
                await self.repository.update_status(
                    task_id,
                    TaskStatus.FAILED,
                    error_message=f"入队失败: {str(exc)}",
                )
            except Exception:
                pass
            raise

        await self.repository.update_status(
            task_id, TaskStatus.PENDING, queue_task_id=queue_task_id
        )
        logger.info(f"text_processor task created: {task_id}")
        return task_id

    async def query_task(
        self, task_id: str
    ) -> tuple[int, str, TextProcessorQueryResponseData]:
        task = await self.repository.get_task(task_id)
        if not task:
            return (
                10001,
                "task not found",
                TextProcessorQueryResponseData(
                    task_id=task_id,
                    task_status=TaskStatus.FAILED.value,
                    failed_reason="task not found",
                ),
            )

        metadata = task.metadata or {}
        task_status = (
            task.status if isinstance(task.status, str) else task.status.value
        )
        failed_reason = metadata.get("failed_reason", "") or task.error_message or ""
        result = metadata.get("result", {})
        if task.result_data:
            result = task.result_data

        return 0, "ok", TextProcessorQueryResponseData(
            task_id=task.task_id,
            task_status=task_status,
            failed_reason=failed_reason,
            result=result,
        )
