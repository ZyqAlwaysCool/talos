"""任务ID上下文透传."""

from __future__ import annotations

from contextvars import ContextVar, Token

DEFAULT_TASK_ID = "-"
_TASK_ID_CTX: ContextVar[str] = ContextVar("task_id", default=DEFAULT_TASK_ID)


def get_task_id() -> str:
    return _TASK_ID_CTX.get()


def set_task_id(task_id: str | None) -> Token:
    value = (task_id or "").strip() or DEFAULT_TASK_ID
    return _TASK_ID_CTX.set(value)


def reset_task_id(token: Token) -> None:
    _TASK_ID_CTX.reset(token)
