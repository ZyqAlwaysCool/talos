"""统一创建：按 task_type 分发到已注册 handler。"""

from __future__ import annotations

from typing import Any

from agents.infra.registry.task_create import TaskCreateRegistry
from core.config.error_codes import (
    COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR,
    get_error_message,
)
from core.exceptions.exceptions import BaseBusinessException


class TaskCreateOrchestrator:
    def __init__(self, registry: TaskCreateRegistry) -> None:
        self._registry = registry

    async def create(self, task_type: str, metadata: dict[str, Any], trace_id: str) -> str:
        handler = self._registry.resolve(task_type)
        if handler is None:
            raise BaseBusinessException(
                code=COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR,
                message=get_error_message(COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR)
                + f"：未注册的 task_type: {task_type}",
            )
        payload = {**metadata, "task_type": task_type}
        return await handler.create(payload, trace_id=trace_id)
