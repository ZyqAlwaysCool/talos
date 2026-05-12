"""Worker 管理器 — Redis 队列轮询、并发控制、重试、优雅关闭."""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager, suppress
from typing import Any

from loguru import logger

from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus
from core.task.redis_queue import (
    build_queue_keys,
    create_redis_client,
    dump_queue_payload,
    load_queue_payload,
    utc_timestamp,
    utc_timestamp_score,
)
from core.task.redis_queue import RedisClient
from core.task.worker import TaskRetryRequested, process_task


class WorkerManager:
    """Redis queue worker manager."""

    def __init__(
        self,
        *,
        queue_name: str = "talos:queue",
        max_jobs: int = 10,
        job_timeout: int = 3600,
        keep_result: int = 86400,
        health_check_interval: int = 3600,
        retry_jobs: bool = True,
        max_tries: int = 3,
        redis_mode: str = "standalone",
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: str | None = None,
        redis_max_connections: int = 10,
        redis_cluster_nodes: list[str] | None = None,
        mongo_db_name: str = "talos_agents",
    ):
        self.worker_config = {
            "queue_name": queue_name,
            "max_jobs": max_jobs,
            "job_timeout": job_timeout,
            "keep_result": keep_result,
            "health_check_interval": health_check_interval,
            "retry_jobs": retry_jobs,
            "max_tries": max_tries,
        }
        self.redis_config = {
            "mode": redis_mode,
            "host": redis_host,
            "port": redis_port,
            "db": redis_db,
            "password": redis_password,
            "max_connections": redis_max_connections,
            "cluster_nodes": redis_cluster_nodes or [],
        }
        self.mongo_db_name = mongo_db_name
        self.queue_keys = build_queue_keys(self.worker_config["queue_name"])
        self.redis_client: RedisClient | None = None
        self.storage_backend = TaskManagerFactory.create_mongo_storage(
            {"db_name": mongo_db_name}
        )
        self.worker_task: asyncio.Task[None] | None = None
        self.running = False
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._semaphore = asyncio.Semaphore(self.worker_config["max_jobs"])
        logger.info(
            "Worker manager initialized. queue={} mode={}",
            queue_name,
            redis_mode,
        )

    async def _ensure_connection(self) -> RedisClient:
        if self.redis_client is None:
            self.redis_client = create_redis_client(
                mode=self.redis_config["mode"],
                host=self.redis_config["host"],
                port=self.redis_config["port"],
                db=self.redis_config["db"],
                password=self.redis_config["password"],
                max_connections=self.redis_config["max_connections"],
                cluster_nodes=self.redis_config["cluster_nodes"] or None,
            )
        return self.redis_client

    async def start_worker(self) -> bool:
        if self.running:
            logger.warning("Worker is already running")
            return True
        try:
            await self._ensure_connection()
            await self._recover_processing_jobs()
            self.running = True
            self.worker_task = asyncio.create_task(
                self._run_worker(), name="redis-queue-worker"
            )
            logger.info("Redis queue worker started")
            return True
        except Exception as exc:
            logger.error("Failed to start worker: {}", str(exc))
            self.running = False
            return False

    async def _run_worker(self) -> None:
        redis_client = await self._ensure_connection()
        try:
            while self.running:
                await self._semaphore.acquire()
                try:
                    job_id = await redis_client.brpoplpush(
                        self.queue_keys.pending_queue,
                        self.queue_keys.processing_queue,
                        timeout=1,
                    )
                except asyncio.CancelledError:
                    self._semaphore.release()
                    raise
                except Exception as exc:
                    self._semaphore.release()
                    logger.error("Worker pop failed: {}", str(exc))
                    await asyncio.sleep(1)
                    continue
                if job_id is None:
                    self._semaphore.release()
                    continue
                task = asyncio.create_task(self._process_job(job_id))
                self._active_tasks.add(task)
                task.add_done_callback(self._on_job_done)
        except asyncio.CancelledError:
            logger.info("Worker loop cancelled")
            raise
        finally:
            self.running = False

    def _on_job_done(self, task: asyncio.Task[None]) -> None:
        self._active_tasks.discard(task)
        self._semaphore.release()
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("Unexpected worker task error: {}", str(exc))

    async def _process_job(self, job_id: str) -> None:
        record = await self._get_job_record(job_id)
        if record is None:
            await self._ack_processing_job(job_id)
            return
        if record.get("status") == TaskStatus.CANCELLED.value:
            await self._finish_terminal_job(job_id, record)
            return
        attempt = int(record.get("attempt", 0)) + 1
        record["status"] = TaskStatus.PROCESSING.value
        record["attempt"] = attempt
        record["started_at"] = utc_timestamp()
        record["error"] = None
        await self._save_job_record(job_id, record)
        try:
            result = await asyncio.wait_for(
                process_task(
                    {
                        "job_try": attempt,
                        "retry_jobs": self.worker_config["retry_jobs"],
                        "max_tries": self.worker_config["max_tries"],
                    },
                    record["task"],
                    record["func_name"],
                    tuple(record.get("args", [])),
                    record.get("kwargs", {}),
                ),
                timeout=self.worker_config["job_timeout"],
            )
        except TaskRetryRequested as exc:
            await self._handle_retry(job_id, record, attempt, str(exc.__cause__ or exc))
        except asyncio.TimeoutError:
            await self._handle_failure(job_id, record, "job timeout")
        except Exception as exc:
            await self._handle_failure(job_id, record, str(exc))
        else:
            record["status"] = TaskStatus.COMPLETED.value
            record["result"] = result.model_dump(mode="json")
            record["completed_at"] = utc_timestamp()
            await self._save_job_record(
                job_id, record, expire_seconds=self.worker_config["keep_result"]
            )
            redis_client = await self._ensure_connection()
            await redis_client.zrem(self.queue_keys.failed_jobs, job_id)
            await redis_client.zadd(
                self.queue_keys.completed_jobs, {job_id: utc_timestamp_score()}
            )
            await self._ack_processing_job(job_id)

    async def _handle_retry(
        self, job_id: str, record: dict[str, Any], attempt: int, error_message: str
    ) -> None:
        if (
            not self.worker_config["retry_jobs"]
            or attempt >= self.worker_config["max_tries"]
        ):
            await self._handle_failure(job_id, record, error_message or "retry exhausted")
            return
        redis_client = await self._ensure_connection()
        record["status"] = TaskStatus.PENDING.value
        record["error"] = error_message or "retry requested"
        await self._save_job_record(job_id, record)
        await self._ack_processing_job(job_id)
        await redis_client.lpush(self.queue_keys.pending_queue, job_id)
        logger.warning(
            "Task scheduled for retry: {} ({}/{})",
            job_id,
            attempt,
            self.worker_config["max_tries"],
        )

    async def _handle_failure(
        self, job_id: str, record: dict[str, Any], error_message: str
    ) -> None:
        redis_client = await self._ensure_connection()
        record["status"] = TaskStatus.FAILED.value
        record["error"] = error_message
        record["completed_at"] = utc_timestamp()
        await self._save_job_record(
            job_id, record, expire_seconds=self.worker_config["keep_result"]
        )
        await redis_client.zadd(
            self.queue_keys.failed_jobs, {job_id: utc_timestamp_score()}
        )
        await self._ack_processing_job(job_id)
        await self._sync_task_failure_status(job_id, record, error_message)
        logger.error("Task failed in worker: {} | {}", job_id, error_message)

    async def _sync_task_failure_status(
        self, job_id: str, record: dict[str, Any], error_message: str
    ) -> None:
        task_payload = record.get("task", {})
        task_id = task_payload.get("task_id") or job_id
        try:
            await self.storage_backend.update_task_status(
                task_id,
                TaskStatus.FAILED,
                error_message=error_message,
                error_details={
                    "reason": error_message,
                    "queue_job_id": job_id,
                    "attempt": record.get("attempt", 0),
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to sync terminal task failure status: {} | {}",
                task_id,
                str(exc),
            )

    async def _ack_processing_job(self, job_id: str) -> None:
        redis_client = await self._ensure_connection()
        await redis_client.lrem(self.queue_keys.processing_queue, 0, job_id)

    async def _finish_terminal_job(self, job_id: str, record: dict[str, Any]) -> None:
        await self._save_job_record(
            job_id, record, expire_seconds=self.worker_config["keep_result"]
        )
        await self._ack_processing_job(job_id)

    async def _recover_processing_jobs(self) -> None:
        redis_client = await self._ensure_connection()
        processing_jobs = await redis_client.lrange(
            self.queue_keys.processing_queue, 0, -1
        )
        for job_id in processing_jobs:
            await redis_client.lrem(self.queue_keys.processing_queue, 1, job_id)
            await redis_client.rpush(self.queue_keys.pending_queue, job_id)
        if processing_jobs:
            logger.warning("Recovered {} jobs from processing queue", len(processing_jobs))

    async def stop_worker(self) -> bool:
        if not self.running and self.worker_task is None:
            return True
        self.running = False
        if self.worker_task and not self.worker_task.done():
            self.worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.worker_task
        for task in list(self._active_tasks):
            task.cancel()
        for task in list(self._active_tasks):
            with suppress(asyncio.CancelledError):
                await task
        self._active_tasks.clear()
        if self.redis_client is not None:
            await self.redis_client.aclose()
            self.redis_client = None
        try:
            self.storage_backend.close()
        except Exception as exc:
            logger.error("Failed to close MongoDB storage: {}", str(exc))
        self.worker_task = None
        logger.info("Redis queue worker stopped")
        return True

    def is_running(self) -> bool:
        return (
            self.running
            and self.worker_task is not None
            and not self.worker_task.done()
        )

    async def health_check(self) -> dict[str, Any]:
        status = {
            "worker_running": self.is_running(),
            "redis_connected": False,
            "queue_accessible": False,
        }
        try:
            redis_client = await self._ensure_connection()
            await redis_client.ping()
            status["redis_connected"] = True
            await redis_client.llen(self.queue_keys.pending_queue)
            status["queue_accessible"] = True
        except Exception as exc:
            logger.warning("Health check failed: {}", str(exc))
        return status

    async def _get_job_record(self, job_id: str) -> dict[str, Any] | None:
        redis_client = await self._ensure_connection()
        payload = await redis_client.get(self.queue_keys.job_key(job_id))
        return load_queue_payload(payload)

    async def _save_job_record(
        self,
        job_id: str,
        record: dict[str, Any],
        *,
        expire_seconds: int | None = None,
    ) -> None:
        redis_client = await self._ensure_connection()
        job_key = self.queue_keys.job_key(job_id)
        await redis_client.set(job_key, dump_queue_payload(record))
        if expire_seconds is not None:
            await redis_client.expire(job_key, expire_seconds)


_worker_manager: WorkerManager | None = None


def get_worker_manager() -> WorkerManager:
    global _worker_manager
    if _worker_manager is None:
        _worker_manager = WorkerManager()
    return _worker_manager


def set_worker_manager(manager: WorkerManager) -> None:
    global _worker_manager
    _worker_manager = manager


@asynccontextmanager
async def worker_lifespan():
    worker_manager = get_worker_manager()
    logger.info("Starting worker in lifespan context...")
    success = await worker_manager.start_worker()
    if not success:
        logger.error("Failed to start worker during startup")
    try:
        yield worker_manager
    finally:
        logger.info("Stopping worker in lifespan context...")
        await worker_manager.stop_worker()


def setup_signal_handlers(worker_manager: WorkerManager) -> None:
    def signal_handler(signum: int, _: Any) -> None:
        logger.info("Received signal {}, shutting down worker...", signum)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(worker_manager.stop_worker())
            else:
                loop.run_until_complete(worker_manager.stop_worker())
        except Exception as exc:
            logger.error("Error during signal handling: {}", str(exc))

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
