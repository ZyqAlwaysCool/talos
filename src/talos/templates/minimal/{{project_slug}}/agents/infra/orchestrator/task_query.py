"""统一任务查询编排。"""

from __future__ import annotations

from typing import Any

from agents.infra.query.result import TASK_QUERY_SUCCESS_CODE, TASK_QUERY_SUCCESS_MSG
from agents.infra.registry.task_query import TaskQueryRegistry, task_query_registry
from agents.infra.schemas.task_query import UnifiedTaskQueryData
from core.config.error_codes import (
    COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR,
    get_error_message,
)
from core.exceptions.exceptions import BaseBusinessException


class TaskQueryService:
    def __init__(self, registry: TaskQueryRegistry) -> None:
        self._registry = registry

    async def query(self, task_id: str) -> tuple[int, str, dict[str, Any]]:
        matched_prefix, handler = self._registry.resolve(task_id)
        if handler is None or matched_prefix is None:
            payload = UnifiedTaskQueryData(
                task_id=task_id, task_type="", detail={},
            ).model_dump()
            return (
                COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR,
                get_error_message(COMMON_ERROR_INVALID_REQUEST_PARAM_ERROR)
                + "：不支持的 task_id 前缀",
                payload,
            )

        try:
            code, msg, detail = await handler(task_id)
        except BaseBusinessException as exc:
            payload = UnifiedTaskQueryData(
                task_id=task_id, task_type=matched_prefix, detail={},
            ).model_dump()
            return exc.code, exc.message, payload

        if code == TASK_QUERY_SUCCESS_CODE:
            msg = TASK_QUERY_SUCCESS_MSG

        envelope = UnifiedTaskQueryData(
            task_id=task_id, task_type=matched_prefix, detail=detail,
        ).model_dump()
        return code, msg, envelope


task_query_service = TaskQueryService(task_query_registry)
