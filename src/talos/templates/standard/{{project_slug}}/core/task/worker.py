"""Worker 任务处理函数 — 通用任务调度，支持自动发现任务模块。"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
import time
from typing import Any

from loguru import logger

from core.logging import reset_task_id, set_task_id
from core.task.models.task_models import TaskResult, TaskStatus
from core.task.registry import task_registry

_loaded_modules: set[str] = set()


def _discover_and_import_modules(
    root_package: str = "agents.biz",
    submodule: str = "workflow.task_entry",
) -> list[str]:
    """扫描 root_package 下每个子包，导入其 workflow.task_entry 触发注册。"""
    try:
        root = importlib.import_module(root_package)
    except ImportError:
        logger.warning("[Discovery] Root package not found: {}", root_package)
        return []

    root_path = getattr(root, "__path__", [])
    if not root_path:
        return []

    imported: list[str] = []
    for _, name, is_pkg in pkgutil.iter_modules(root_path):
        if not is_pkg:
            continue
        target = f"{root_package}.{name}.{submodule}"
        try:
            importlib.import_module(target)
            imported.append(target)
            logger.info("[Discovery] Task module loaded: {}", target)
        except ImportError:
            logger.debug("[Discovery] Skipped (no task_entry): {}", target)

    if not imported:
        logger.warning("[Discovery] No task modules found, root_package={}", root_package)
    return imported


def load_task_modules(module_paths: list[str] | None = None) -> None:
    """加载任务模块：显式路径或自动发现。须在 setup_logger() 之后调用。"""
    if module_paths:
        for module_path in module_paths:
            if module_path and module_path not in _loaded_modules:
                importlib.import_module(module_path)
                _loaded_modules.add(module_path)
                logger.info("[TaskModules] Explicit load: {}", module_path)
    else:
        logger.info("[TaskModules] task_modules not configured, using auto-discovery...")
        discovered = _discover_and_import_modules("agents.biz", "workflow.task_entry")
        logger.info("[TaskModules] Auto-discovery complete, {} modules loaded", len(discovered))
        _loaded_modules.update(discovered)


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
    """通用任务处理函数 — 队列 Worker 的统一入口。"""
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
            task_id=task_id, status=TaskStatus.COMPLETED,
            result_data=result, execution_time=execution_time,
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
                task_id, execution_time, str(e), job_try, ctx.get("max_tries", 1),
            )
            raise TaskRetryRequested() from e
        logger.error(
            "Task failed: {} after {:.2f}s - {} | no retry",
            task_id, execution_time, str(e),
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
