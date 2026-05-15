"""API 路由聚合。"""

import app.register_handlers  # noqa: F401  # 触发全部 handler 注册
from agents.router.task_create import task_create_router
from agents.router.task_query import task_query_router
from agents.router.task_thinking import thinking_sse_router
from fastapi import APIRouter

api_router = APIRouter()
api_router.include_router(task_create_router)
api_router.include_router(task_query_router)
api_router.include_router(thinking_sse_router)
