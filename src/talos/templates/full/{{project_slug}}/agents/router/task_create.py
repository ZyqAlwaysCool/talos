"""HTTP 路由：统一任务创建（JSON + 文件上传范式）。"""

from __future__ import annotations

from pathlib import Path

from agents.infra.orchestrator.task_create import TaskCreateOrchestrator
from agents.infra.registry import app_registries
from agents.infra.schemas.task_create import UnifiedTaskCreateRequest
from core.auth.dependencies import require_auth
from core.exceptions import generate_trace_id
from core.schemas import BaseResponse
from fastapi import APIRouter, Depends, Request
from loguru import logger

task_create_router = APIRouter(
    prefix="/agents/task",
    tags=["agents-task"],
    dependencies=[Depends(require_auth)],
)
_orchestrator = TaskCreateOrchestrator(app_registries.create)

_ROOT_DIR = Path(__file__).resolve().parents[2]
_DEFAULT_UPLOAD_DIR = str(_ROOT_DIR / "data" / "uploads")


@task_create_router.post(
    "/create",
    summary="创建任务（JSON 范式）",
    description="适用于入参为纯 JSON 结构的任务类型",
    response_model=BaseResponse,
)
async def create_task(request: Request, payload: UnifiedTaskCreateRequest) -> BaseResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info("Unified task create - TraceID: {} | task_type: {}", trace_id, payload.task_type)
    try:
        task_id = await _orchestrator.create(payload.task_type, payload.metadata, trace_id)
    except Exception as exc:
        from core.exceptions.exceptions import BaseBusinessException
        if isinstance(exc, BaseBusinessException):
            return BaseResponse(code=exc.code, msg=exc.message, trace_id=trace_id)
        raise
    return BaseResponse.success(data={"task_id": task_id}, trace_id=trace_id)
