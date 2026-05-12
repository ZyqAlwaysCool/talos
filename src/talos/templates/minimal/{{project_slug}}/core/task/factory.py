"""任务管理器工厂 — 创建队列和存储后端."""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.task.backends.redis_backend import RedisTaskBackend
from core.task.backends.mongo_task_storage import MongoTaskStorage
from core.task.base.queue_backend import QueueBackend
from core.task.base.storage_backend import StorageBackend
from core.config.config_center import get_app_config, get_worker_config


class TaskManagerFactory:
    """任务管理器工厂类."""

    @classmethod
    def create_queue_backend(
        cls, config: dict[str, Any] | None = None
    ) -> RedisTaskBackend:
        app_config = get_app_config()
        worker_config = get_worker_config()

        # 构建 queue_map: worker_group → queue_name
        queue_map: dict[str, str] = {}
        for group_name, queue_name in app_config.queue_names.items():
            queue_map[group_name] = queue_name

        final_config: dict[str, Any] = {
            "default_queue": worker_config.queue_name,
            "queue_map": queue_map,
            "job_timeout": worker_config.job_timeout,
            "keep_result": worker_config.keep_result,
            "redis_mode": app_config.redis_mode,
            "redis_host": app_config.redis_host,
            "redis_port": app_config.redis_port,
            "redis_db": app_config.redis_db,
            "redis_cluster_nodes": app_config.redis_cluster_nodes,
            "redis_password": app_config.redis_password,
            "max_connections": app_config.redis_max_connections,
        }
        if config:
            final_config.update(config)

        masked = final_config.copy()
        if masked.get("redis_password"):
            masked["redis_password"] = "***"
        logger.info(f"Creating Redis backend with config: {masked}")
        return RedisTaskBackend(final_config)

    @classmethod
    def create_mongo_storage(
        cls, config: dict[str, Any] | None = None
    ) -> MongoTaskStorage:
        app_config = get_app_config()
        final_config: dict[str, Any] = {
            "db_name": app_config.mongo_db_name,
        }
        if config:
            final_config.update(config)
        logger.info(f"Creating MongoDB storage with config: {final_config}")
        return MongoTaskStorage(final_config)

    @classmethod
    def create_default_backends(
        cls,
        queue_config: dict[str, Any] | None = None,
        mongo_config: dict[str, Any] | None = None,
    ) -> tuple[QueueBackend, StorageBackend]:
        queue_backend = cls.create_queue_backend(queue_config)
        storage_backend = cls.create_mongo_storage(mongo_config)
        return queue_backend, storage_backend

    @classmethod
    async def health_check_backends(
        cls, queue_backend: QueueBackend, storage_backend: StorageBackend
    ) -> dict[str, bool]:
        result: dict[str, bool] = {"queue": False, "storage": False, "overall": False}
        try:
            result["queue"] = await queue_backend.health_check()
        except Exception as e:
            logger.error(f"Queue health check failed: {str(e)}")
        try:
            from core.task.models.task_models import TaskQuery
            test_query = TaskQuery(limit=1)
            await storage_backend.query_tasks(test_query)
            result["storage"] = True
        except Exception as e:
            logger.error(f"Storage health check failed: {str(e)}")
        result["overall"] = result["queue"] and result["storage"]
        return result
