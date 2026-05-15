"""统一任务查询响应信封。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UnifiedTaskQueryData(BaseModel):
    task_id: str = Field(..., description="请求的任务 ID")
    task_type: str = Field(..., description="命中的 task_id 前缀键（最长前缀优先）")
    detail: dict[str, Any] = Field(
        default_factory=dict,
        description="业务域 query_task 返回字段",
    )
