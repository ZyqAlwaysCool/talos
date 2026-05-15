"""认证依赖注入。AUTH_ENABLED=false 时透传，不校验 token。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from loguru import logger

from core.config.config_center import get_app_config


async def require_auth(request: Request) -> None:
    """全局认证守卫。认证关闭时透传，开启时校验 JWT token。"""
    config = get_app_config()
    if not config.auth_enabled:
        return
    from core.auth.auth_service import get_auth_service

    auth_service = get_auth_service()
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Missing authorization token")
    try:
        payload = auth_service.verify_token(token)
        request.state.user_id = payload.get("user_id", "")
    except Exception:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid or expired token")


AuthDep = Annotated[None, Depends(require_auth)]
