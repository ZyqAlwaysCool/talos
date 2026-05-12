from __future__ import annotations

from typing import Protocol

from agents.infra.llm.context import ThinkingContext


class ThinkingSink(Protocol):
    async def on_node_start(self, context: ThinkingContext) -> None:
        ...

    async def on_node_delta(self, context: ThinkingContext, delta: str) -> None:
        ...

    async def on_node_end(self, context: ThinkingContext) -> None:
        ...

    async def on_node_error(self, context: ThinkingContext, error_message: str) -> None:
        ...
