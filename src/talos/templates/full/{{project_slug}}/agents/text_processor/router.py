"""text_processor Agent 路由."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from loguru import logger

from agents.text_processor.schemas import (
    TextProcessorCreateRequest,
    TextProcessorQueryResponseData,
)
from agents.text_processor.service import TextProcessorService
from core.exceptions import generate_trace_id
from core.schemas import BaseResponse

text_processor_router = APIRouter(
    prefix="/text_processor",
    tags=["text_processor"],
)
text_processor_service = TextProcessorService()


@text_processor_router.post(
    "/create",
    summary="创建文本处理任务",
    description="提交文本处理请求，异步返回处理结果",
    response_model=BaseResponse,
)
async def create_text_processor_task(
    request: Request, payload: TextProcessorCreateRequest
) -> BaseResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info(f"TextProcessor create request - TraceID: {trace_id}")
    task_id = await text_processor_service.create_task(payload, trace_id=trace_id)
    return BaseResponse.success(data={"task_id": task_id}, trace_id=trace_id)


@text_processor_router.get(
    "/query",
    summary="查询文本处理任务",
    description="根据 task_id 查询任务执行状态和结果",
    response_model=BaseResponse,
)
async def query_text_processor_task(
    request: Request,
    task_id: Annotated[str, Query(..., description="Text processor task id")],
) -> BaseResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info(f"TextProcessor query request - TraceID: {trace_id} | task_id: {task_id}")
    code, msg, data = await text_processor_service.query_task(task_id)
    return BaseResponse(code=code, msg=msg, data=data.model_dump(), trace_id=trace_id)
