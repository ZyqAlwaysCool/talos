from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from agents.infra.sse.registry import resolver_registry
from agents.infra.sse.service import ThinkingSSEService
from core.auth.dependencies import require_auth
from core.exceptions import generate_trace_id

thinking_sse_router = APIRouter(
    prefix="/agents",
    tags=["agents-thinking"],
    dependencies=[Depends(require_auth)],
)
thinking_sse_service = ThinkingSSEService(resolver_registry=resolver_registry)


@thinking_sse_router.get(
    "/thinking/stream",
    summary="订阅任务思维链流（通用）",
    description="按任务ID实时订阅各业务agent的LLM思维链事件",
)
async def stream_task_thinking(
    request: Request,
    task_id: Annotated[str, Query(..., description="Task id")],
) -> StreamingResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info(
        "Generic thinking stream request - TraceID: {} | task_id: {}",
        trace_id,
        task_id,
    )
    event_generator = thinking_sse_service.stream_task_thinking(
        task_id=task_id, trace_id=trace_id
    )
    return StreamingResponse(
        event_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
