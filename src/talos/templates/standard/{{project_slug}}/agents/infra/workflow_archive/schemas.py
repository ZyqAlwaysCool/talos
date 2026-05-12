from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowArchiveNode(BaseModel):
    node_id: str = Field(..., description="节点执行唯一ID，对应node_exec_id")
    parent_node_id: str = Field(
        default="", description="父节点执行ID，根节点的父ID通常为run_root_id"
    )
    node_name: str = Field(default="", description="节点名称（workflow节点名或提示词名）")
    node_display_name: str = Field(default="", description="节点展示名称（用于前端展示）")
    prompt_name: str = Field(default="", description="LLM提示词名称，非LLM节点为空")
    node_type: Literal["workflow", "llm"] = Field(
        ..., description="节点类型：workflow或llm"
    )
    node_status: Literal["pending", "process", "completed", "failed"] = Field(
        default="pending", description="节点状态"
    )
    node_content: str = Field(default="", description="节点内容（通常为thinking聚合文本）")
    error_message: str = Field(default="", description="节点失败原因")
    started_at: str = Field(default="", description="节点开始时间（ISO8601）")
    ended_at: str = Field(default="", description="节点结束时间（ISO8601）")
    node_seq: int = Field(default=0, description="节点序号（同一run内递增）")
    extra: dict[str, Any] = Field(default_factory=dict, description="节点扩展信息")


class WorkflowArchiveRun(BaseModel):
    run_id: str = Field(..., description="执行轮次ID（一次队列执行）")
    attempt: int = Field(default=1, description="执行轮次编号（来自队列重试计数）")
    run_status: Literal["processing", "completed", "failed", "cancelled"] = Field(
        default="processing", description="本轮执行状态"
    )
    failed_reason: str = Field(default="", description="本轮失败原因")
    run_root_id: str = Field(default="", description="本轮根节点ID，通常为{run_id}:root")
    started_at: str = Field(default="", description="本轮开始时间（ISO8601）")
    ended_at: str = Field(default="", description="本轮结束时间（ISO8601）")
    nodes: list[WorkflowArchiveNode] = Field(
        default_factory=list, description="本轮全部节点列表"
    )


class WorkflowArchive(BaseModel):
    schema_version: str = Field(default="1.0", description="归档结构版本号")
    task_id: str = Field(..., description="任务ID")
    agent_name: str = Field(default="", description="业务Agent名称")
    workflow_name: str = Field(default="", description="工作流名称")
    final_task_status: Literal[
        "pending",
        "processing",
        "completed",
        "failed",
        "cancelled",
    ] = Field(default="pending", description="任务最终状态")
    latest_run_id: str = Field(default="", description="最后一次执行轮次ID（无论成功失败）")
    latest_success_run_id: str = Field(default="", description="最近一次成功执行轮次ID")
    runs: list[WorkflowArchiveRun] = Field(
        default_factory=list, description="任务全部执行轮次历史"
    )
