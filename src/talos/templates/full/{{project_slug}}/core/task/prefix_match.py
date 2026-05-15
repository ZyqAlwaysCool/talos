"""task_id 字符串的最长前缀匹配。"""

from __future__ import annotations

from typing import Mapping, TypeVar

T = TypeVar("T")


def match_longest_task_id_prefix(
    task_id: str, prefix_to_value: Mapping[str, T]
) -> tuple[str | None, T | None]:
    """将 task_id 与已注册前缀做最长匹配。"""
    if not task_id:
        return None, None

    best_prefix: str | None = None
    best_value: T | None = None
    best_len = -1

    for registered_prefix, value in prefix_to_value.items():
        if task_id == registered_prefix:
            candidate_len = len(registered_prefix)
        elif task_id.startswith(f"{registered_prefix}_"):
            candidate_len = len(registered_prefix)
        else:
            continue
        if candidate_len > best_len:
            best_len = candidate_len
            best_prefix = registered_prefix
            best_value = value

    if best_prefix is not None:
        return best_prefix, best_value
    return None, None


def resolve_prefixed_mapping(
    task_id: str,
    prefix_to_value: Mapping[str, T],
    *,
    first_segment_fallback: bool = True,
) -> tuple[str | None, T | None]:
    """先最长前缀匹配；可选再按首段回退。"""
    matched_prefix, value = match_longest_task_id_prefix(task_id, prefix_to_value)
    if matched_prefix is not None:
        return matched_prefix, value

    if not first_segment_fallback or "_" not in task_id:
        return None, None

    first = task_id.split("_", 1)[0]
    v = prefix_to_value.get(first)
    if v is not None:
        return first, v
    return None, None
