"""Redis 队列后端 — 支持多队列路由."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger

from core.task.base.queue_backend import QueueBackend
from core.task.models.task_models import BaseTask, TaskResult, TaskStatus
from core.task.redis_queue import (
    RedisClient,
    build_queue_keys,
    create_redis_client,
    dump_queue_payload,
    load_queue_payload,
    utc_timestamp,
)


class RedisTaskBackend(QueueBackend):
    """Redis queue backend — 通过 worker_group 实现多队列路由."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.default_queue_name = str(self.config.get("default_queue", "talos:queue"))
        # queue_map: worker_group → queue_name
        self.queue_map: dict[str, str] = self.config.get("queue_map", {})
        if "default" not in self.queue_map:
            self.queue_map["default"] = self.default_queue_name
        # 收集所有唯一的 queue name
        self.queue_names = list(dict.fromkeys(
            [self.default_queue_name] + list(self.queue_map.values())
        ))
        self.queue_keys = build_queue_keys(self.default_queue_name)
        self.keep_result = int(self.config.get("keep_result", 86400))
        self.route_key_prefix = "talos:task-route"
        self.redis_client: RedisClient | None = None

        # Redis 连接参数
        self.redis_mode = str(self.config.get("redis_mode", "standalone"))
        self.redis_host = str(self.config.get("redis_host", "127.0.0.1"))
        self.redis_port = int(self.config.get("redis_port", 6379))
        self.redis_db = int(self.config.get("redis_db", 0))
        self.redis_password: str | None = self.config.get("redis_password")
        self.redis_max_connections = int(self.config.get("max_connections", 10))
        self.redis_cluster_nodes: list[str] = self.config.get(
            "redis_cluster_nodes", []
        )

        logger.info(
            "Redis queue backend initialized. default_queue={} queue_map={}",
            self.default_queue_name,
            self.queue_map,
        )

    async def _ensure_connection(self) -> RedisClient:
        if self.redis_client is None:
            self.redis_client = create_redis_client(
                mode=self.redis_mode,
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                max_connections=self.redis_max_connections,
                cluster_nodes=self.redis_cluster_nodes if self.redis_cluster_nodes else None,
            )
        return self.redis_client

    async def enqueue_task(
        self, task: BaseTask, func: Callable, *args: Any, **kwargs: Any
    ) -> str:
        try:
            redis_client = await self._ensure_connection()
            queue_task_id = task.task_id
            route_queue_name = self._resolve_route_queue_name(task)
            route_queue_keys = build_queue_keys(route_queue_name)
            payload = {
                "queue_task_id": queue_task_id,
                "task": task.model_dump(mode="json"),
                "func_name": func.__name__ if hasattr(func, "__name__") else "anonymous",
                "args": list(args),
                "kwargs": kwargs,
                "status": TaskStatus.PENDING.value,
                "attempt": 0,
                "error": None,
                "result": None,
                "enqueued_at": utc_timestamp(),
                "started_at": None,
                "completed_at": None,
            }
            await redis_client.set(
                route_queue_keys.job_key(queue_task_id), dump_queue_payload(payload)
            )
            await redis_client.set(self._route_key(queue_task_id), route_queue_name)
            await redis_client.expire(self._route_key(queue_task_id), self.keep_result)
            await redis_client.lpush(route_queue_keys.pending_queue, queue_task_id)
            logger.info(
                "Task enqueued to Redis queue: {} queue={}",
                queue_task_id,
                route_queue_name,
            )
            return queue_task_id
        except Exception as exc:
            logger.opt(exception=exc).error(
                "Redis backend enqueue failed | task_id={}", task.task_id
            )
            raise

    async def get_task_status(self, queue_task_id: str) -> dict[str, Any]:
        record = await self._get_job_record(queue_task_id)
        if record is None:
            return {
                "queue_task_id": queue_task_id,
                "execution_status": TaskStatus.FAILED,
                "queue_type": "redis",
                "error": "queue task not found",
            }
        return {
            "queue_task_id": queue_task_id,
            "execution_status": record.get("status", TaskStatus.PENDING.value),
            "queue_type": "redis",
            "attempt": record.get("attempt", 0),
            "error": record.get("error"),
        }

    async def get_task_result(self, queue_task_id: str) -> TaskResult | None:
        record = await self._get_job_record(queue_task_id)
        if record is None or record.get("status") != TaskStatus.COMPLETED.value:
            return None
        result_payload = record.get("result")
        result_data = None
        metadata: dict[str, Any] = {}
        execution_time = None
        if isinstance(result_payload, dict):
            result_data = result_payload.get("result_data")
            metadata = result_payload.get("metadata", {})
            execution_time = result_payload.get("execution_time")
        return TaskResult(
            task_id=queue_task_id,
            status=TaskStatus.COMPLETED,
            result_data=result_data,
            metadata=metadata,
            execution_time=execution_time,
        )

    async def cancel_task(self, queue_task_id: str) -> bool:
        record = await self._get_job_record(queue_task_id)
        if record is None or record.get("status") != TaskStatus.PENDING.value:
            return False
        record["status"] = TaskStatus.CANCELLED.value
        record["completed_at"] = utc_timestamp()
        await self._save_job_record(queue_task_id, record, expire_seconds=self.keep_result)
        logger.info("Task marked as cancelled: {}", queue_task_id)
        return True

    async def get_queue_length(self, queue_name: str = "default") -> int:
        redis_client = await self._ensure_connection()
        target_queue = (
            self.queue_keys.pending_queue
            if queue_name == "default"
            else build_queue_keys(queue_name).pending_queue
        )
        return int(await redis_client.llen(target_queue))

    async def get_failed_tasks(self, limit: int = 10) -> list[dict[str, Any]]:
        redis_client = await self._ensure_connection()
        job_ids = await redis_client.zrevrange(
            self.queue_keys.failed_jobs, 0, max(limit - 1, 0)
        )
        results: list[dict[str, Any]] = []
        for job_id in job_ids:
            record = await self._get_job_record(job_id)
            if record is None:
                continue
            results.append({
                "job_id": job_id,
                "failed_at": record.get("completed_at"),
                "error": record.get("error"),
            })
        return results

    async def retry_failed_task(self, queue_task_id: str) -> bool:
        redis_client = await self._ensure_connection()
        record = await self._get_job_record(queue_task_id)
        if record is None or record.get("status") != TaskStatus.FAILED.value:
            return False
        queue_keys = await self._resolve_queue_keys(queue_task_id)
        record["status"] = TaskStatus.PENDING.value
        record["error"] = None
        record["completed_at"] = None
        record["started_at"] = None
        record["result"] = None
        await self._save_job_record(queue_task_id, record)
        await redis_client.zrem(queue_keys.failed_jobs, queue_task_id)
        await redis_client.lpush(queue_keys.pending_queue, queue_task_id)
        logger.info("Task requeued from failed state: {}", queue_task_id)
        return True

    async def clear_failed_tasks(self) -> int:
        redis_client = await self._ensure_connection()
        cleared = 0
        for queue_name in self.queue_names:
            queue_keys = build_queue_keys(queue_name)
            job_ids = await redis_client.zrange(queue_keys.failed_jobs, 0, -1)
            for job_id in job_ids:
                deleted = await redis_client.delete(queue_keys.job_key(job_id))
                if deleted:
                    cleared += 1
                await redis_client.zrem(queue_keys.failed_jobs, job_id)
        return cleared

    async def health_check(self) -> bool:
        try:
            redis_client = await self._ensure_connection()
            await redis_client.ping()
            return True
        except Exception as exc:
            logger.error("Redis queue health check failed: {}", str(exc))
            return False

    async def close(self) -> None:
        if self.redis_client is not None:
            await self.redis_client.aclose()
            self.redis_client = None

    # ── internal helpers ──────────────────────────────────────────────

    async def _get_job_record(self, queue_task_id: str) -> dict[str, Any] | None:
        redis_client = await self._ensure_connection()
        queue_keys = await self._resolve_queue_keys(queue_task_id)
        payload = await redis_client.get(queue_keys.job_key(queue_task_id))
        return load_queue_payload(payload)

    async def _save_job_record(
        self,
        queue_task_id: str,
        record: dict[str, Any],
        *,
        expire_seconds: int | None = None,
    ) -> None:
        redis_client = await self._ensure_connection()
        queue_keys = await self._resolve_queue_keys(queue_task_id)
        job_key = queue_keys.job_key(queue_task_id)
        await redis_client.set(job_key, dump_queue_payload(record))
        if expire_seconds is not None:
            await redis_client.expire(job_key, expire_seconds)

    def _route_key(self, queue_task_id: str) -> str:
        return f"{self.route_key_prefix}:{queue_task_id}"

    async def _resolve_queue_keys(self, queue_task_id: str):
        redis_client = await self._ensure_connection()
        routed_queue_name = await redis_client.get(self._route_key(queue_task_id))
        if routed_queue_name:
            return build_queue_keys(routed_queue_name)
        for queue_name in self.queue_names:
            queue_keys = build_queue_keys(queue_name)
            payload = await redis_client.get(queue_keys.job_key(queue_task_id))
            if payload is not None:
                await redis_client.set(self._route_key(queue_task_id), queue_name)
                await redis_client.expire(self._route_key(queue_task_id), self.keep_result)
                return queue_keys
        return self.queue_keys

    def _resolve_route_queue_name(self, task: BaseTask) -> str:
        """基于 metadata.worker_group 路由到指定队列."""
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        worker_group = str(metadata.get("worker_group", "default")).strip()
        return self.queue_map.get(worker_group, self.default_queue_name)
