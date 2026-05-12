"""请求追踪中间件."""

from __future__ import annotations

import time
import uuid

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware


class RequestTraceMiddleware(BaseHTTPMiddleware):
    """为每个请求注入 trace_id 并记录耗时."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or uuid.uuid4().hex[:16]
        request.state.trace_id = trace_id
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        response.headers["X-Trace-ID"] = trace_id
        logger.info(
            f"Request completed - {request.method} {request.url.path} "
            f"status={response.status_code} duration={duration:.3f}s"
        )
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件."""

    async def dispatch(self, request: Request, call_next):
        logger.info(f"Request: {request.method} {request.url.path}")
        response = await call_next(request)
        return response
