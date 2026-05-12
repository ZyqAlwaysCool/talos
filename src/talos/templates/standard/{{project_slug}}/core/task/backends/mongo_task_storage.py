"""MongoDB 任务存储后端 — 支持多 collection 动态路由."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from core.task.base.storage_backend import StorageBackend
from core.task.models.task_models import (
    BaseTask,
    BatchTask,
    SubTaskResult,
    TaskQuery,
    TaskResult,
    TaskStatus,
    TaskType,
)
from core.storage.mongo_storage import MongoStorage
from core.task.registry import collection_registry


class MongoTaskStorage(StorageBackend):
    """MongoDB 任务存储后端."""

    _storage_instances: dict[str, MongoStorage] = {}

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.db_name = str(self.config.get("db_name", "talos_agents"))
        self.mongo_host = str(self.config.get("mongo_host", "127.0.0.1"))
        self.mongo_port = int(self.config.get("mongo_port", 27017))
        self.mongo_user = self.config.get("mongo_user")
        self.mongo_password = self.config.get("mongo_password")
        logger.info(
            "MongoDB task storage initialized. db={} host={}:{}",
            self.db_name,
            self.mongo_host,
            self.mongo_port,
        )

    def _get_current_collection_mapping(self) -> dict[str, str]:
        return collection_registry.get_mappings()

    def get_storage_instance(self, task_type: str | None = None) -> MongoStorage:
        current_mapping = self._get_current_collection_mapping()
        collection_name = current_mapping.get(
            task_type or "default", current_mapping["default"]
        )
        _cache = type(self)._storage_instances
        if collection_name not in _cache:
            _cache[collection_name] = MongoStorage(
                self.db_name,
                collection_name,
                host=self.mongo_host,
                port=self.mongo_port,
                username=self.mongo_user,
                password=self.mongo_password,
            )
        return _cache[collection_name]

    def _extract_task_type_key(self, task: BaseTask) -> str:
        if hasattr(task, "metadata") and task.metadata:
            if "collection_type" in task.metadata:
                return str(task.metadata["collection_type"])
        return "default"

    def _extract_task_type_key_from_id(self, task_id: str) -> str:
        return collection_registry.get_collection_by_task_id(task_id)

    def _task_to_dict(self, task: BaseTask) -> dict[str, Any]:
        task_dict = task.model_dump()
        for field in ["created_at", "started_at", "completed_at"]:
            if field in task_dict and task_dict[field]:
                if isinstance(task_dict[field], datetime):
                    task_dict[field] = task_dict[field].isoformat()
        if "sub_results" in task_dict:
            for sr in task_dict["sub_results"]:
                if isinstance(sr.get("created_at"), datetime):
                    sr["created_at"] = sr["created_at"].isoformat()
        return task_dict

    def _dict_to_task(self, task_dict: dict[str, Any]) -> BaseTask:
        for field in ["created_at", "started_at", "completed_at"]:
            if field in task_dict and task_dict[field]:
                if isinstance(task_dict[field], str):
                    task_dict[field] = datetime.fromisoformat(task_dict[field])
        if "sub_results" in task_dict:
            for sr in task_dict["sub_results"]:
                if isinstance(sr.get("created_at"), str):
                    sr["created_at"] = datetime.fromisoformat(sr["created_at"])
        task_type = task_dict.get("task_type")
        if task_type == TaskType.BATCH_PROCESSING:
            return BatchTask(**task_dict)
        return BaseTask(**task_dict)

    async def create_task(self, task: BaseTask) -> bool:
        try:
            task_type_key = self._extract_task_type_key(task)
            storage = self.get_storage_instance(task_type_key)
            task_dict = self._task_to_dict(task)
            await storage.create_record(task_dict)
            logger.info(f"Task created: {task.task_id} -> {storage.col.name}")
            return True
        except Exception as e:
            logger.opt(exception=e).error(f"Failed to create task {task.task_id}")
            return False

    async def get_task(self, task_id: str) -> BaseTask | None:
        try:
            task_type_key = self._extract_task_type_key_from_id(task_id)
            storage = self.get_storage_instance(task_type_key)
            records = await storage.find_record({"task_id": task_id})
            if records:
                task_dict = records[0]
                task_dict.pop("_id", None)
                return self._dict_to_task(task_dict)
            # fallback: 遍历所有 collection
            for fallback_key in self._get_current_collection_mapping().keys():
                if fallback_key == task_type_key:
                    continue
                other_storage = self.get_storage_instance(fallback_key)
                records = await other_storage.find_record({"task_id": task_id})
                if records:
                    task_dict = records[0]
                    task_dict.pop("_id", None)
                    return self._dict_to_task(task_dict)
            return None
        except Exception as e:
            logger.opt(exception=e).error(f"Failed to get task {task_id}")
            return None

    async def update_task_status(
        self, task_id: str, status: TaskStatus, **kwargs: Any
    ) -> bool:
        try:
            update_data: dict[str, Any] = {"status": status.value}
            if status == TaskStatus.PROCESSING:
                update_data["started_at"] = datetime.now().isoformat()
            elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                update_data["completed_at"] = datetime.now().isoformat()
            for key, value in kwargs.items():
                if value is not None:
                    update_data[key] = (
                        value.isoformat() if isinstance(value, datetime) else value
                    )
            task_type_key = self._extract_task_type_key_from_id(task_id)
            storage = self.get_storage_instance(task_type_key)
            await storage.update_record({"task_id": task_id}, update_data)
            return True
        except Exception as e:
            logger.opt(exception=e).error(f"Failed to update task status {task_id}")
            return False

    async def query_tasks(self, query: TaskQuery) -> list[BaseTask]:
        try:
            all_tasks: list[BaseTask] = []
            for task_type_key in self._get_current_collection_mapping().keys():
                storage = self.get_storage_instance(task_type_key)
                filter_dict: dict[str, Any] = {}
                if query.task_id:
                    filter_dict["task_id"] = query.task_id
                if query.task_type:
                    filter_dict["task_type"] = query.task_type.value
                if query.status:
                    filter_dict["status"] = query.status.value
                if query.created_after or query.created_before:
                    cf: dict[str, str] = {}
                    if query.created_after:
                        cf["$gte"] = query.created_after.isoformat()
                    if query.created_before:
                        cf["$lte"] = query.created_before.isoformat()
                    filter_dict["created_at"] = cf
                try:
                    records = await storage.find_record(filter_dict)
                    for record in records:
                        record.pop("_id", None)
                        try:
                            all_tasks.append(self._dict_to_task(record))
                        except Exception:
                            continue
                except Exception:
                    continue
            all_tasks.sort(key=lambda x: x.created_at, reverse=True)
            return all_tasks[query.offset : query.offset + query.limit]
        except Exception as e:
            logger.error(f"Failed to query tasks: {str(e)}")
            return []

    async def delete_task(self, task_id: str) -> bool:
        try:
            for task_type_key in self._get_current_collection_mapping().keys():
                storage = self.get_storage_instance(task_type_key)
                try:
                    await storage.delete_record({"task_id": task_id})
                    return True
                except Exception:
                    continue
            return False
        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {str(e)}")
            return False

    async def save_task_result(self, task_id: str, result: TaskResult) -> bool:
        try:
            result_dict = result.dict()
            update_data = {
                "result_data": result_dict.get("result_data"),
                "result_metadata": result_dict.get("metadata", {}),
                "execution_time": result_dict.get("execution_time"),
            }
            for task_type_key in self._get_current_collection_mapping().keys():
                storage = self.get_storage_instance(task_type_key)
                try:
                    await storage.update_record({"task_id": task_id}, update_data)
                    return True
                except Exception:
                    continue
            return False
        except Exception as e:
            logger.error(f"Failed to save task result {task_id}: {str(e)}")
            return False

    async def add_sub_task_result(
        self,
        task_id: str,
        sub_task_id: str,
        status: TaskStatus,
        result: Any = None,
        error_message: str | None = None,
        processing_time: float | None = None,
    ) -> bool:
        try:
            sub_result = SubTaskResult(
                sub_task_id=sub_task_id,
                status=status,
                result=result,
                error_message=error_message,
                processing_time=processing_time,
            )
            task = await self.get_task(task_id)
            if not task or not isinstance(task, BatchTask):
                return False
            task.sub_results.append(sub_result)
            task_type_key = self._extract_task_type_key(task)
            storage = self.get_storage_instance(task_type_key)
            sub_results_dict = [sr.dict() for sr in task.sub_results]
            await storage.update_record(
                {"task_id": task_id}, {"sub_results": sub_results_dict}
            )
            return True
        except Exception as e:
            logger.error(f"Failed to add sub task result {task_id}/{sub_task_id}: {str(e)}")
            return False

    async def cleanup_expired_tasks(self, days: int = 30) -> int:
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            total_cleaned = 0
            for task_type_key in self._get_current_collection_mapping().keys():
                storage = self.get_storage_instance(task_type_key)
                try:
                    expired_filter = {
                        "created_at": {"$lt": cutoff_date.isoformat()},
                        "status": {
                            "$in": [
                                TaskStatus.COMPLETED.value,
                                TaskStatus.FAILED.value,
                                TaskStatus.CANCELLED.value,
                            ]
                        },
                    }
                    expired_records = await storage.find_record(expired_filter)
                    for record in expired_records:
                        await storage.delete_record({"_id": record["_id"]})
                        total_cleaned += 1
                except Exception:
                    continue
            logger.info(f"Cleaned up {total_cleaned} expired tasks")
            return total_cleaned
        except Exception as e:
            logger.error(f"Failed to cleanup expired tasks: {str(e)}")
            return 0

    def close(self) -> None:
        instances = type(self)._storage_instances
        for collection_name, storage in instances.items():
            try:
                storage.close_client()
                logger.info("MongoDB connection closed: {}", collection_name)
            except Exception as e:
                logger.warning(
                    "Failed to close MongoDB connection: {} | {}", collection_name, str(e)
                )
        instances.clear()
