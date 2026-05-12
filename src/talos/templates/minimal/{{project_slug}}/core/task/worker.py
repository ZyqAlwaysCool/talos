"""Worker 任务处理函数 — 通用任务调度."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import time
from typing import Any

from loguru import logger

from core.logging import reset_task_id, set_task_id
from core.task.models.task_models import TaskResult, TaskStatus
from core.task.registry import task_registry

_loaded_modules: set[str] = set()


def load_task_modules(module_paths: list[str]) -> None:
    """惰性加载 task 模块 — 由 Worker 启动时显式调用."""
    for module_path in module_paths:
        if module_path and module_path not in _loaded_modules:
            importlib.import_module(module_path)
            _loaded_modules.add(module_path)
            logger.info(f"Loaded task module: {module_path}")


class TaskRetryRequested(Exception):
    """Signal the queue worker to retry the current task."""


def _supports_inject_kwarg(func: Any, kwarg_name: str) -> bool:
    signature = inspect.signature(func)
    if kwarg_name in signature.parameters:
        return True
    return any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in signature.parameters.values()
    )


async def process_task(
    ctx,
    task_dict: dict[str, Any],
    func_name: str,
    args: tuple,
    kwargs: dict[str, Any],
    **worker_kwargs,
) -> TaskResult:
    """通用任务处理函数 — 队列 Worker 的统一入口."""
    start_time = time.time()
    _ = worker_kwargs
    task_id = task_dict.get("task_id", "unknown")
    job_try = ctx.get("job_try", 1) if isinstance(ctx, dict) else 1
    task_token = set_task_id(str(task_id))

    try:
        logger.info(f"Processing task: {task_id} | Function: {func_name}")
        func = _get_business_function(func_name)
        kwargs["task_id"] = task_id
        if _supports_inject_kwarg(func, "task_retry_context"):
            kwargs["task_retry_context"] = {
                "job_try": job_try,
                "max_tries": ctx.get("max_tries", 1) if isinstance(ctx, dict) else 1,
                "retry_jobs": ctx.get("retry_jobs", False) if isinstance(ctx, dict) else False,
            }
        if asyncio.iscoroutinefunction(func):
            result = await func(*args, **kwargs)
        else:
            result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        logger.info(f"Task completed: {task_id} in {execution_time:.2f}s")
        return TaskResult(
            task_id=task_id,
            status=TaskStatus.COMPLETED,
            result_data=result,
            execution_time=execution_time,
        )
    except Exception as e:
        execution_time = time.time() - start_time
        should_retry = (
            isinstance(ctx, dict)
            and ctx.get("retry_jobs", False)
            and job_try < ctx.get("max_tries", 1)
        )
        if should_retry:
            logger.warning(
                "Task failed: {} after {:.2f}s - {} | retrying ({}/{})",
                task_id,
                execution_time,
                str(e),
                job_try,
                ctx.get("max_tries", 1),
            )
            raise TaskRetryRequested() from e
        logger.error(
            "Task failed: {} after {:.2f}s - {} | no retry",
            task_id,
            execution_time,
            str(e),
        )
        raise
    finally:
        reset_task_id(task_token)


def _get_business_function(func_name: str):
    try:
        return task_registry.get(func_name)
    except ValueError as e:
        logger.error(
            f"Task function not found: {func_name}. "
            f"Available: {list(task_registry._functions.keys())}"
        )
        raise e
