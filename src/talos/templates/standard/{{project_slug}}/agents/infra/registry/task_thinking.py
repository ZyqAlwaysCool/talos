"""思维链解析器注册表。"""

from __future__ import annotations

from typing import Protocol

from agents.infra.schemas.task_thinking import TaskThinkingSnapshot
from core.task.prefix_match import resolve_prefixed_mapping


class TaskThinkingResolver(Protocol):
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
        if not task_id:
            return None
        tid = task_id.strip().lower()
        _, resolver = resolve_prefixed_mapping(
            tid, self._resolvers, first_segment_fallback=True
        )
        return resolver


resolver_registry = TaskThinkingResolverRegistry()
