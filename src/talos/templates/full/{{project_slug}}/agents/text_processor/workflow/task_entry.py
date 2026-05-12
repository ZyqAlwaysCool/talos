"""text_processor Worker 任务入口 — 注册到全局 task_registry."""

from __future__ import annotations

from typing import Any

from loguru import logger

from agents.text_processor.constants import (
    TEXT_PROCESSOR_COLLECTION,
    TEXT_PROCESSOR_TASK_PREFIX,
)
from agents.text_processor.workflow.flow import TextProcessorWorkflow
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus
from core.task.registry import collection_registry, task_registry

collection_registry.register(
    TEXT_PROCESSOR_COLLECTION,
    TEXT_PROCESSOR_COLLECTION,
    task_id_prefix=TEXT_PROCESSOR_TASK_PREFIX,
)


async def run_text_processor_task(
    text: str,
    options: dict[str, Any],
    task_id: str,
    task_retry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """text_processor 任务入口 — 由 Worker 调用."""
    storage = TaskManagerFactory.create_mongo_storage()
    await storage.update_task_status(task_id, TaskStatus.PROCESSING)
    logger.info("start text_processor task: {}", task_id)

    try:
        workflow = TextProcessorWorkflow()
        result = await workflow.run(text=text, options=options)

        await storage.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            result_data=result,
        )
        llm_status = "LLM" if result.get("used_llm") else "hardcode"
        logger.info("text_processor task completed ({}): {}", llm_status, task_id)
        return {"result": result}
    except Exception as exc:
        logger.error("text_processor task failed: {} | {}", task_id, str(exc))
        await storage.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(exc),
        )
        raise


task_registry.register("run_text_processor_task", run_text_processor_task)
