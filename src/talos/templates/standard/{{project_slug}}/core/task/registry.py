"""任务函数注册表 + Collection 映射注册表."""

from __future__ import annotations

from typing import Callable

from loguru import logger


class TaskFunctionRegistry:
    """任务函数注册表 — 函数名 → 可调用对象."""

    def __init__(self):
        self._functions: dict[str, Callable] = {}

    def register(self, func_name: str, func: Callable) -> None:
        if func_name in self._functions:
            logger.warning(f"Function {func_name} already registered, overriding")
        self._functions[func_name] = func
        logger.info(f"Registered task function: {func_name}")

    def get(self, func_name: str) -> Callable:
        if func_name not in self._functions:
            raise ValueError(f"Task function '{func_name}' is not registered")
        return self._functions[func_name]

    def list_functions(self) -> dict[str, str]:
        return {name: str(func) for name, func in self._functions.items()}


class TaskCollectionRegistry:
    """任务 Collection 映射注册表 — task key → MongoDB collection 名称."""

    def __init__(self):
        self._mappings: dict[str, str] = {"default": "talos_tasks"}
        self._prefix_mappings: dict[str, str] = {}

    def register(
        self,
        task_type_key: str,
        collection_name: str,
        task_id_prefix: str | None = None,
    ) -> None:
        if task_type_key in self._mappings and task_type_key != "default":
            logger.warning(f"Task type {task_type_key} already registered, overriding")
        self._mappings[task_type_key] = collection_name
        if task_id_prefix:
            self._prefix_mappings[task_id_prefix] = task_type_key
            logger.info(
                f"Registered task mapping: {task_type_key} -> {collection_name} "
                f"(prefix: {task_id_prefix})"
            )
        else:
            logger.info(
                f"Registered task collection mapping: {task_type_key} -> {collection_name}"
            )

    def get_mappings(self) -> dict[str, str]:
        return self._mappings.copy()

    def get_collection(self, task_type_key: str) -> str:
        return self._mappings.get(task_type_key, self._mappings["default"])

    def get_collection_by_task_id(self, task_id: str) -> str:
        if not task_id:
            return "default"
        best_type_key: str | None = None
        best_prefix_len = -1
        for registered_prefix, task_type_key in self._prefix_mappings.items():
            if task_id == registered_prefix:
                candidate_len = len(registered_prefix)
            elif task_id.startswith(f"{registered_prefix}_"):
                candidate_len = len(registered_prefix)
            else:
                continue
            if candidate_len > best_prefix_len:
                best_prefix_len = candidate_len
                best_type_key = task_type_key
        if best_type_key is not None:
            return best_type_key
        if "_" not in task_id:
            return "default"
        prefix = task_id.split("_", 1)[0]
        return self._prefix_mappings.get(prefix, "default")


# 全局注册表实例
task_registry = TaskFunctionRegistry()
collection_registry = TaskCollectionRegistry()
