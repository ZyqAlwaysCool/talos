'''
Description: 查找、注册任务状态解析器
Author: zyq
Date: 2026-04-10 12:02:58
LastEditors: zyq
LastEditTime: 2026-04-13 10:18:06
'''
from __future__ import annotations

from typing import Protocol

from agents.infra.sse.models import TaskThinkingSnapshot


class TaskThinkingResolver(Protocol): # 接口定义, 类似于go中的interface, 无需显式继承
    async def resolve(self, task_id: str) -> TaskThinkingSnapshot:
        ...


class TaskThinkingResolverRegistry:
    def __init__(self) -> None:
        self._resolvers: dict[str, TaskThinkingResolver] = {}

    def register(self, task_prefix: str, resolver: TaskThinkingResolver) -> None:
        normalized_prefix = task_prefix.strip().lower()
        if not normalized_prefix:
            raise ValueError("task_prefix must not be empty")
        self._resolvers[normalized_prefix] = resolver

    def get_resolver(self, task_id: str) -> TaskThinkingResolver | None:
        task_prefix = task_id.split("_", 1)[0].strip().lower() if task_id else ""
        if not task_prefix:
            return None
        return self._resolvers.get(task_prefix)


resolver_registry = TaskThinkingResolverRegistry()
