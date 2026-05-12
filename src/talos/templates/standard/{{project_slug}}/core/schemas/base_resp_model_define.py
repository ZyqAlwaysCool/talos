"""统一 API 响应模型."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class BaseResponse(BaseModel):
    """统一基础响应."""
    code: int = Field(0, description="状态码, 0 表示成功")
    msg: str = Field("ok", description="状态信息")
    data: Any = Field(None, description="响应数据")
    trace_id: str = Field("", description="追踪ID")

    @classmethod
    def success(cls, *, data: Any = None, trace_id: str = "", msg: str = "ok") -> BaseResponse:
        return cls(code=0, msg=msg, data=data, trace_id=trace_id)

    @classmethod
    def error(cls, *, code: int, msg: str, data: Any = None, trace_id: str = "") -> BaseResponse:
        return cls(code=code, msg=msg, data=data, trace_id=trace_id)


class BizResponse(BaseModel, Generic[T]):
    """泛型业务响应."""
    code: int = Field(0, description="状态码")
    msg: str = Field("ok", description="状态信息")
    data: T | None = Field(None, description="响应数据")
    trace_id: str = Field("", description="追踪ID")


class ApiResponse(BaseModel):
    """API 成功响应（非统一格式）."""
    success: bool = Field(True, description="是否成功")
    message: str = Field("Operation completed successfully", description="操作信息")
    data: Any = Field(None, description="响应数据")
