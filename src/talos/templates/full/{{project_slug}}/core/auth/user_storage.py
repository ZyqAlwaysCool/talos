'''
Description: 认证用户存储服务
Author: zyq
Date: 2026-02-09 10:03:36
LastEditors: zyq
LastEditTime: 2026-02-28 09:33:17
'''

import hashlib
import secrets
from datetime import datetime

from loguru import logger

from core.storage.mongo_storage import MongoStorage

from .models import AuthUser, UserStatus


class AuthUserStorage:
    """认证用户存储服务"""

    def __init__(self, mongo_storage: MongoStorage):
        self.mongo = mongo_storage
        self.collection_name = "auth_users"
        self._indexes_ready = False

    async def _ensure_indexes(self) -> None:
        """Ensure required indexes exist."""
        if self._indexes_ready:
            return
        collection = self.mongo.db[self.collection_name]
        await collection.create_index("username", unique=True)
        await collection.create_index("user_id", unique=True)
        self._indexes_ready = True

    def _hash_password(self, password: str) -> str:
        """Password hashing."""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password."""
        try:
            salt, hashed = password_hash.split(":", 1)
            return hashlib.sha256((password + salt).encode()).hexdigest() == hashed
        except ValueError:
            return False

    async def create_user(
        self, business_name: str, permissions: list[str]
    ) -> tuple[AuthUser, str]:
        """Create user."""
        await self._ensure_indexes()
        username = f"{business_name}_auth_user"
        user_id = f"user_{secrets.token_hex(8)}"

        password = secrets.token_urlsafe(16)
        password_hash = self._hash_password(password)

        user_data = {
            "user_id": user_id,
            "username": username,
            "password_hash": password_hash,
            "permissions": permissions,
            "status": UserStatus.ACTIVE,
            "created_at": datetime.utcnow(),
            "last_login": None,
        }

        collection = self.mongo.db[self.collection_name]
        result = await collection.insert_one(user_data)
        user_data["_id"] = result.inserted_id

        logger.info(f"Auth user created: {username} (ID: {user_id})")
        return AuthUser(**user_data), password

    async def authenticate_user(
        self, username: str, password: str
    ) -> AuthUser | None:
        """Authenticate user."""
        await self._ensure_indexes()
        collection = self.mongo.db[self.collection_name]
        user_data = await collection.find_one(
            {"username": username, "status": UserStatus.ACTIVE}
        )

        if not user_data:
            logger.warning(f"Authentication failed: user not found - {username}")
            return None

        if not self._verify_password(password, user_data["password_hash"]):
            logger.warning(f"Authentication failed: invalid password - {username}")
            return None

        await collection.update_one(
            {"user_id": user_data["user_id"]},
            {"$set": {"last_login": datetime.utcnow()}},
        )

        logger.info(f"User authenticated: {username}")
        return AuthUser(**user_data)

    async def get_user_by_username(self, username: str) -> AuthUser | None:
        """Get user by username."""
        await self._ensure_indexes()
        collection = self.mongo.db[self.collection_name]
        user_data = await collection.find_one({"username": username})
        return AuthUser(**user_data) if user_data else None

    async def disable_user(self, username: str) -> bool:
        """Disable user."""
        await self._ensure_indexes()
        collection = self.mongo.db[self.collection_name]
        result = await collection.update_one(
            {"username": username}, {"$set": {"status": UserStatus.DISABLED}}
        )
        return result.modified_count > 0

    async def update_permissions(self, username: str, permissions: list[str]) -> bool:
        """Update user permissions."""
        await self._ensure_indexes()
        collection = self.mongo.db[self.collection_name]
        result = await collection.update_one(
            {"username": username}, {"$set": {"permissions": permissions}}
        )
        return result.modified_count > 0
