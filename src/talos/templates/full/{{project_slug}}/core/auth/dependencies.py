'''
Description: 鉴权依赖配置, 接口级
Author: zyq
Date: 2026-02-24 11:13:31
LastEditors: zyq
LastEditTime: 2026-02-28 09:32:49
'''

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger

from core.config.config_center import get_app_config
from core.config.error_codes import (
    AUTH_ERROR_AUTH_FAILED,
    AUTH_ERROR_INVALID_TOKEN,
    COMMON_ERROR_SERVICE_INIT_FAILED,
    get_error_message,
)

_bearer_scheme = HTTPBearer(auto_error=False)


async def require_auth(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> None:
    config = get_app_config()
    if not config.auth_enabled:
        return

    auth_service = getattr(request.app.state, "auth_service", None)
    if not auth_service:
        logger.warning("Auth service not available")
        raise HTTPException(
            status_code=500,
            detail=get_error_message(COMMON_ERROR_SERVICE_INIT_FAILED),
        )

    if credentials is None:
        logger.warning("Missing or invalid Authorization header")
        raise HTTPException(
            status_code=401,
            detail=get_error_message(AUTH_ERROR_AUTH_FAILED),
        )

    token = credentials.credentials.strip()
    if not token:
        logger.warning("Missing or invalid Authorization token")
        raise HTTPException(
            status_code=401,
            detail=get_error_message(AUTH_ERROR_AUTH_FAILED),
        )

    payload = auth_service.verify_token(token)
    if not payload:
        logger.warning("Invalid or expired token")
        raise HTTPException(
            status_code=401,
            detail=get_error_message(AUTH_ERROR_INVALID_TOKEN),
        )

    request.state.user_id = payload.user_id
    request.state.username = payload.username
    request.state.permissions = payload.permissions
