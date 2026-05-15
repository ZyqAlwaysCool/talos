'''
Description: 认证服务
Author: zyq
Date: 2026-02-09 10:03:36
LastEditors: zyq
LastEditTime: 2026-02-28 09:32:35
'''

from datetime import datetime, timedelta, timezone

import jwt
from loguru import logger
from pymongo.errors import DuplicateKeyError

from core.config.error_codes import (
    AUTH_ERROR_REGISTER_FAILED,
    AUTH_ERROR_USER_ALREADY_EXISTS,
    COMMON_ERROR_SERVICE_INIT_FAILED,
)

from .models import AuthUser, TokenPayload, TokenResponse
from .user_storage import AuthUserStorage


class AuthService:
    def __init__(self, secret_key: str, token_expire_hours: int = 24):
        self.secret_key = secret_key
        self.token_expire_hours = token_expire_hours
        self.user_storage: AuthUserStorage | None = None

    def set_user_storage(self, user_storage: AuthUserStorage):
        """设置用户存储服务"""
        self.user_storage = user_storage

    async def register(
        self, business_name: str
    ) -> tuple[AuthUser | None, str | None, int | None]:
        """Register user and return (user, password, error_code)."""
        if not self.user_storage:
            logger.error("User storage not initialized")
            return None, None, COMMON_ERROR_SERVICE_INIT_FAILED

        try:
            permissions = ["*"]
            user, password = await self.user_storage.create_user(
                business_name, permissions
            )
            logger.info(f"User registered successfully: {user.username}")
            return user, password, None
        except DuplicateKeyError:
            logger.warning("User registration failed: user already exists")
            return None, None, AUTH_ERROR_USER_ALREADY_EXISTS
        except Exception as e:
            logger.error(f"User registration error: {str(e)}")
            return None, None, AUTH_ERROR_REGISTER_FAILED

    async def authenticate(
        self, username: str, password: str
    ) -> TokenResponse | None:
        """Authenticate user and return token response."""
        if not self.user_storage:
            logger.error("User storage not initialized")
            return None

        user = await self.user_storage.authenticate_user(username, password)
        if not user:
            return None

        # 生成token
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self.token_expire_hours
        )
        payload = {
            "user_id": user.user_id,
            "username": user.username,
            "permissions": user.permissions,
            "exp": int(expires_at.timestamp()),
        }

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")

        logger.info(f"User {username} authenticated successfully")
        return TokenResponse(
            access_token=token,
            expires_in=self.token_expire_hours * 3600,
            expires_at=expires_at,
        )

    def verify_token(self, token: str) -> TokenPayload | None:
        """验证Token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired.")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            return None
