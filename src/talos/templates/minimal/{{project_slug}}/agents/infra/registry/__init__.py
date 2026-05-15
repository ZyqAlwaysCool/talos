"""基础设施注册表聚合与全局单例。"""

from __future__ import annotations

from dataclasses import dataclass

from agents.infra.registry.task_create import TaskCreateRegistry
from agents.infra.registry.task_query import TaskQueryRegistry, task_query_registry
from agents.infra.registry.task_thinking import (
    TaskThinkingResolverRegistry,
    resolver_registry,
)


@dataclass
class AppRegistries:
    create: TaskCreateRegistry
    query: TaskQueryRegistry
    thinking: TaskThinkingResolverRegistry


app_registries = AppRegistries(
    create=TaskCreateRegistry(),
    query=task_query_registry,
    thinking=resolver_registry,
)
