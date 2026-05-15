"""MongoDB storage abstraction using Motor."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket


class MongoStorage:
    """MongoDB 存储抽象层，封装 CRUD 和 GridFS 操作."""

    def __init__(
        self,
        db_name: str,
        collection_name: str,
        *,
        host: str = "127.0.0.1",
        port: int = 27017,
        username: str | None = None,
        password: str | None = None,
    ):
        self.db_name = db_name
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self.collection_name = collection_name
        self.client: AsyncIOMotorClient | None = None
        self.db: Any = None
        self.col: Any = None
        self._fs: AsyncIOMotorGridFSBucket | None = None

    def _build_uri(self) -> str:
        if self.username and self._password:
            return f"mongodb://{self.username}:{self._password}@{self.host}:{self.port}"
        return f"mongodb://{self.host}:{self.port}"

    def _get_client(self) -> AsyncIOMotorClient:
        if self.client is None:
            self.client = AsyncIOMotorClient(
                self._build_uri(), serverSelectionTimeoutMS=5000
            )
            self.db = self.client[self.db_name]
            self.col = self.db[self.collection_name]
            self._fs = AsyncIOMotorGridFSBucket(self.db)
        return self.client

    async def create_record(self, record: dict[str, Any]) -> str:
        client = self._get_client()
        result = await self.col.insert_one(record)
        return str(result.inserted_id)

    async def find_record(
        self,
        query: dict[str, Any],
        *,
        sort: list[tuple[str, int]] | None = None,
        limit: int = 0,
        skip: int = 0,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        cursor = self.col.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return list(await cursor.to_list(length=None))

    async def update_record(
        self, query: dict[str, Any], update: dict[str, Any]
    ) -> bool:
        client = self._get_client()
        result = await self.col.update_one(query, {"$set": update})
        return result.modified_count > 0

    async def delete_record(self, query: dict[str, Any]) -> bool:
        client = self._get_client()
        result = await self.col.delete_one(query)
        return result.deleted_count > 0

    async def upload_file(
        self, filename: str, data: bytes, metadata: dict[str, Any] | None = None
    ) -> str:
        client = self._get_client()
        file_id = await self._fs.upload_from_stream(filename, data, metadata=metadata)
        return str(file_id)

    async def download_file(self, file_id: str) -> bytes:
        client = self._get_client()
        grid_out = await self._fs.open_download_stream(ObjectId(file_id))
        return await grid_out.read()

    async def create_index(
        self, keys: list[tuple[str, int]], unique: bool = False
    ) -> str:
        client = self._get_client()
        return await self.col.create_index(keys, unique=unique)

    def close_client(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            self.col = None
            self._fs = None
