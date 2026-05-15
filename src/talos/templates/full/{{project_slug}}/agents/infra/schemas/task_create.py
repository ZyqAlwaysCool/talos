"""统一任务创建请求/响应 schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UnifiedTaskCreateRequest(BaseModel):
    task_type: str = Field(..., description="任务类型标识，与注册表 key 一致")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="业务域自定义元数据，由 handler 自行校验",
    )
