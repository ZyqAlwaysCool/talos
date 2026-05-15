"""HTTP 路由：统一任务查询。"""

from __future__ import annotations

from typing import Annotated

from agents.infra.orchestrator.task_query import task_query_service
from core.auth.dependencies import require_auth
from core.exceptions import generate_trace_id
from core.schemas import BaseResponse
from fastapi import APIRouter, Depends, Query, Request
from loguru import logger

task_query_router = APIRouter(
    prefix="/agents/task",
    tags=["agents-task"],
    dependencies=[Depends(require_auth)],
)


@task_query_router.get(
    "/query",
    summary="统一查询任务详情",
    description="按 task_id 最长前缀匹配分发到对应业务域的 query_task",
    response_model=BaseResponse,
)
async def query_task_unified(
    request: Request,
    task_id: Annotated[str, Query(..., description="任务 ID")],
) -> BaseResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info("Unified task query - TraceID: {} | task_id: {}", trace_id, task_id)
    code, msg, data = await task_query_service.query(task_id)
    return BaseResponse(code=code, msg=msg, data=data, trace_id=trace_id)
