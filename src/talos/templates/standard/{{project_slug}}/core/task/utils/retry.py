"""重试工具函数."""

from __future__ import annotations

from typing import Any


def is_retryable_failure(retry_context: dict[str, Any] | None) -> bool:
    if not retry_context:
        return False
    job_try = int(retry_context.get("job_try", 1))
    max_tries = int(retry_context.get("max_tries", 1))
    retry_enabled = bool(retry_context.get("retry_jobs", False))
    return retry_enabled and job_try < max_tries


def build_retry_log_fields(retry_context: dict[str, Any] | None) -> tuple[int, int]:
    if not retry_context:
        return 1, 1
    return int(retry_context.get("job_try", 1)), int(retry_context.get("max_tries", 1))
