"""异常体系和全局异常处理."""

from __future__ import annotations

import traceback
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger

from core.config.error_codes import COMMON_ERROR_INTERNAL_ERROR, get_error_message


def generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


class BaseBusinessException(Exception):
    """业务异常基类."""

    def __init__(self, code: int, message: str = "", data: Any = None):
        self.code = code
        self.message = message or get_error_message(code)
        self.data = data
        super().__init__(self.message)


class FileProcessException(BaseBusinessException):
    """文件处理异常."""


class WorkflowException(BaseBusinessException):
    """工作流异常."""


class DatabaseException(BaseBusinessException):
    """数据库异常."""


class ValidationException(BaseBusinessException):
    """参数验证异常."""


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())

    if isinstance(exc, BaseBusinessException):
        logger.error(
            f"Business exception - trace_id={trace_id} code={exc.code} message={exc.message}"
        )
        return JSONResponse(
            status_code=200,
            content={
                "code": exc.code,
                "msg": exc.message,
                "data": exc.data,
                "trace_id": trace_id,
            },
        )

    logger.error(
        f"Unhandled exception - trace_id={trace_id} {type(exc).__name__}: {str(exc)}\n"
        f"{traceback.format_exc()}"
    )
    return JSONResponse(
        status_code=200,
        content={
            "code": COMMON_ERROR_INTERNAL_ERROR,
            "msg": get_error_message(COMMON_ERROR_INTERNAL_ERROR),
            "data": None,
            "trace_id": trace_id,
        },
    )
