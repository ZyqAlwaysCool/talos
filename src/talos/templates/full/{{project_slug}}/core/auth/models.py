'''
Description: 认证相关数据模型
Author: zyq
Date: 2026-02-09 10:03:36
LastEditors: zyq
LastEditTime: 2026-02-28 09:33:05
'''

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class AuthUser(BaseModel):
    """简化的认证用户模型"""

    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名 (格式: {业务名}_auth_user)")
    password_hash: str = Field(..., description="密码哈希")
    permissions: list[str] = Field(default=[], description="权限列表")
    status: UserStatus = Field(default=UserStatus.ACTIVE, description="用户状态")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="创建时间"
    )
    last_login: datetime | None = Field(None, description="最后登录时间")

    class Config:
        collection_name = "auth_users"


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class RegisterRequest(BaseModel):
    """注册请求"""

    business_name: str = Field(
        ..., description="业务名称 (将生成格式: {business_name}_auth_user)"
    )


class RegisterResponse(BaseModel):
    """注册响应"""

    user_id: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="系统生成的密码（仅显示一次，请妥善保管）")
    created_at: datetime = Field(..., description="创建时间")
    permissions: list[str] = Field(default=[], description="权限列表")


class TokenResponse(BaseModel):
    """Token响应"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒数
    expires_at: datetime


class TokenPayload(BaseModel):
    """Token载荷"""

    user_id: str
    username: str
    permissions: list[str] = []
    exp: int  # 过期时间戳
