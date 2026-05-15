"""Redis 队列工具 — client protocol, key 构建, 序列化."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, cast

from redis.asyncio import Redis
from redis.asyncio.cluster import ClusterNode, RedisCluster


class RedisClient(Protocol):
    """Redis 客户端接口协议，兼容 standalone 和 cluster 模式."""

    async def set(self, name: str, value: str) -> Any: ...
    async def get(self, name: str) -> str | None: ...
    async def lpush(self, name: str, *values: str) -> Any: ...
    async def rpush(self, name: str, *values: str) -> Any: ...
    async def llen(self, name: str) -> int: ...
    async def lrange(self, name: str, start: int, end: int) -> list[str]: ...
    async def lrem(self, name: str, count: int, value: str) -> int: ...
    async def brpoplpush(self, src: str, dst: str, timeout: int = 0) -> str | None: ...
    async def zadd(self, name: str, mapping: Mapping[str, float]) -> Any: ...
    async def zcard(self, name: str) -> int: ...
    async def zrem(self, name: str, *values: str) -> int: ...
    async def zrange(self, name: str, start: int, end: int) -> list[str]: ...
    async def zrevrange(self, name: str, start: int, end: int) -> list[str]: ...
    async def delete(self, *names: str) -> int: ...
    async def ping(self) -> Any: ...
    async def expire(self, name: str, time: int) -> Any: ...
    async def execute_command(self, *args: Any) -> Any: ...
    async def xadd(self, name: str, fields: Mapping[str, str], *, maxlen: int | None = None, approximate: bool = True) -> Any: ...
    async def xread(self, streams: Mapping[str, str], *, count: int | None = None, block: int | None = None) -> Any: ...
    async def aclose(self) -> Any: ...


@dataclass(slots=True, frozen=True)
class RedisQueueKeys:
    """Redis 队列 key 集合."""
    queue_name: str
    pending_queue: str
    processing_queue: str
    failed_jobs: str
    completed_jobs: str

    def job_key(self, job_id: str) -> str:
        return f"{self.queue_name}:{{{self._slot_tag()}}}:job:{job_id}"

    def _slot_tag(self) -> str:
        return self.queue_name.replace(":", "-")


def build_queue_keys(queue_name: str) -> RedisQueueKeys:
    slot_tag = queue_name.replace(":", "-")
    prefix = f"{queue_name}:{{{slot_tag}}}"
    return RedisQueueKeys(
        queue_name=queue_name,
        pending_queue=f"{prefix}:pending",
        processing_queue=f"{prefix}:processing",
        failed_jobs=f"{prefix}:failed",
        completed_jobs=f"{prefix}:completed",
    )


def create_redis_client(
    *,
    mode: str = "standalone",
    host: str = "127.0.0.1",
    port: int = 6379,
    db: int = 0,
    password: str | None = None,
    max_connections: int = 10,
    cluster_nodes: list[str] | None = None,
) -> RedisClient:
    """创建 Redis 客户端 (standalone 或 cluster)."""
    if mode == "cluster":
        if not cluster_nodes:
            raise ValueError("cluster_nodes is required when mode is 'cluster'")
        startup_nodes = [_parse_cluster_node(n) for n in cluster_nodes]
        return cast(
            RedisClient,
            RedisCluster(
                startup_nodes=startup_nodes,
                password=password,
                max_connections=max_connections,
                decode_responses=True,
            ),
        )

    return cast(
        RedisClient,
        Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            max_connections=max_connections,
            decode_responses=True,
        ),
    )


def dump_queue_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=_json_default)


def load_queue_payload(payload: str | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    return json.loads(payload)


def utc_timestamp() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def utc_timestamp_score() -> float:
    return datetime.utcnow().timestamp()


def _parse_cluster_node(raw_node: str) -> ClusterNode:
    host, separator, port = raw_node.strip().partition(":")
    if not separator or not host or not port:
        raise ValueError(f"Invalid Redis cluster node: {raw_node}")
    return ClusterNode(host=host, port=int(port))


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
