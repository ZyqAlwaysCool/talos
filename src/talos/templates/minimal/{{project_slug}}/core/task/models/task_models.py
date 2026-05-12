"""任务数据模型."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    SINGLE = "single"
    BATCH_PROCESSING = "batch_processing"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


def generate_task_id(prefix: str = "task") -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{ts}_{short_uuid}"


class SubTaskResult(BaseModel):
    sub_task_id: str = Field(..., description="子任务ID")
    status: TaskStatus = Field(..., description="子任务状态")
    result: Any = Field(None, description="子任务结果")
    error_message: str | None = Field(None, description="错误信息")
    processing_time: float | None = Field(None, description="处理耗时(秒)")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BaseTask(BaseModel):
    task_id: str = Field(..., description="任务ID")
    task_type: TaskType = Field(TaskType.SINGLE, description="任务类型")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    priority: TaskPriority = Field(TaskPriority.NORMAL, description="优先级")
    metadata: dict[str, Any] = Field(default_factory=dict, description="任务元数据")
    result_data: Any = Field(None, description="任务结果")
    error_message: str | None = Field(None, description="错误信息")
    error_details: dict[str, Any] | None = Field(None, description="错误详情")
    queue_task_id: str | None = Field(None, description="队列任务ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)
    processed_items: int = Field(0, description="已处理项目数")
    successful_items: int = Field(0, description="成功项目数")
    failed_items: int = Field(0, description="失败项目数")
    execution_time: float | None = Field(None, description="执行耗时(秒)")
    result_metadata: dict[str, Any] = Field(default_factory=dict)


class BatchTask(BaseTask):
    task_type: TaskType = TaskType.BATCH_PROCESSING
    sub_results: list[SubTaskResult] = Field(default_factory=list)
    total_items: int = Field(0, description="总项目数")


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    result_data: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    execution_time: float | None = None
    memory_usage: float | None = None


class TaskQuery(BaseModel):
    task_id: str | None = None
    task_type: TaskType | None = None
    status: TaskStatus | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
