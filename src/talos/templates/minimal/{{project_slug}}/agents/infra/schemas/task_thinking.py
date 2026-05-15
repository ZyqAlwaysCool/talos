from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class TaskThinkingSnapshot:
    task_id: str
    exists: bool
    status: str = ""
    failed_reason: str = ""
    thinking_stream_enabled: bool = True
