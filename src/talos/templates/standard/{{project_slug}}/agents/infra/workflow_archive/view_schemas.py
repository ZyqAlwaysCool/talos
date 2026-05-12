'''
Description:
Author: zyq
Date: 2026-04-23 09:56:04
LastEditors: zyq
LastEditTime: 2026-04-23 11:40:59
'''
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WorkflowNodeInfo(BaseModel):
    node_id: str = Field("", description="节点唯一ID")
    parent_node_id: str = Field("", description="父节点ID")
    node_name: str = Field("", description="节点名称")
    title: str = Field("", description="节点展示名称") # 前端展示用, 映射为node_display_name
    prompt_name: str = Field("", description="提示词名称，非LLM节点为空")
    node_content: str = Field("", description="节点内容（thinking聚合文本）")
    node_status: Literal["pending", "process", "completed", "failed"] = Field(
        "pending", description="节点状态"
    )
    node_type: Literal["workflow", "llm"] = Field(
        "workflow", description="节点类型：workflow或llm"
    )
    node_seq: int = Field(0, description="节点序号")
    started_at: str = Field("", description="开始时间（ISO8601）")
    ended_at: str = Field("", description="结束时间（ISO8601）")
    error_message: str = Field("", description="失败原因")


class WorkflowTreeNodeInfo(BaseModel):
    node_id: str = Field("", description="节点唯一ID")
    parent_node_id: str = Field("", description="父节点ID")
    node_name: str = Field("", description="节点名称")
    title: str = Field("", description="节点展示名称") # 前端展示用, 映射为node_display_name
    prompt_name: str = Field("", description="提示词名称，非LLM节点为空")
    node_content: str = Field("", description="节点内容（thinking聚合文本）")
    node_status: Literal["pending", "process", "completed", "failed"] = Field(
        "pending", description="节点状态"
    )
    node_type: Literal["workflow", "llm"] = Field(
        "workflow", description="节点类型：workflow或llm"
    )
    node_seq: int = Field(0, description="节点序号")
    started_at: str = Field("", description="开始时间（ISO8601）")
    ended_at: str = Field("", description="结束时间（ISO8601）")
    error_message: str = Field("", description="失败原因")
    sub_nodes: list["WorkflowTreeNodeInfo"] = Field(
        default_factory=list, description="子节点列表"
    )


WorkflowTreeNodeInfo.model_rebuild()
