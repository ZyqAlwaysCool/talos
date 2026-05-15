"""text_processor 业务 schemas。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TextProcessorCreateRequest(BaseModel):
    """创建文本处理任务请求。"""
    text: str = Field(..., description="待处理的文本")
    options: dict = Field(default_factory=dict, description="可选的额外参数")


class TextProcessorQueryResponseData(BaseModel):
    """查询文本处理任务响应数据。"""
    task_id: str = Field(..., description="任务ID")
    task_status: str = Field(..., description="任务状态")
    failed_reason: str = Field(default="", description="失败原因")
    result: dict = Field(default_factory=dict, description="任务结果")
