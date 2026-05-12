"""统一配置中心 — 环境变量驱动的应用配置."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class ConfigValidationError(Exception):
    """Configuration validation error."""


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_LOADED = False
ENV_LOCAL_PATH = PROJECT_ROOT / ".env.local"
ENV_LEGACY_PATH = PROJECT_ROOT / ".env"


class AppConfig(BaseModel):
    """Application configuration."""

    log_level: str = Field("INFO", description="Log level")
    log_dir: str = Field("logs", description="Log directory")
    auth_enabled: bool = Field(False, description="Enable auth")
    auth_secret_key: str = Field("", description="Auth secret key")
    auth_token_expire_hours: int = Field(
        24, description="Auth token expire hours", ge=1, le=168
    )

    # MongoDB
    mongo_host: str = Field("127.0.0.1", description="MongoDB host")
    mongo_port: int = Field(27017, description="MongoDB port", ge=1, le=65535)
    mongo_db_name: str = Field("{{ mongo_db_name }}", description="MongoDB database")

    # Redis
    redis_mode: Literal["standalone", "cluster"] = Field(
        "standalone", description="Redis deploy mode"
    )
    redis_host: str = Field("127.0.0.1", description="Redis host")
    redis_port: int = Field(6379, description="Redis port", ge=1, le=65535)
    redis_db: int = Field(2, description="Redis database", ge=0, le=15)
    redis_cluster_nodes: list[str] = Field(
        default_factory=list, description="Redis cluster startup nodes"
    )
    redis_password: str | None = Field(None, description="Redis password")
    redis_max_connections: int = Field(
        10, description="Redis max connections", ge=1, le=100
    )

    # 多队列配置: worker_group_name → redis_queue_name
    queue_names: dict[str, str] = Field(
        default_factory=lambda: {"default": "{{ redis_queue_prefix }}:queue"},
        description="Worker group to queue name mapping",
    )

    # LLM
    llm_provider: Literal["openai", "anthropic", "custom"] = Field(
        {% if llm_provider == 'openai' %}"openai"{% elif llm_provider == 'anthropic' %}"anthropic"{% else %}"custom"{% endif %},
        description="LLM provider",
    )
    llm_base_url: str = Field("", description="LLM base URL")
    llm_api_key: str = Field("", description="LLM API key")
    llm_model: str = Field("gpt-4o", description="LLM model name")
    llm_temperature: float = Field(0.2, description="LLM temperature", ge=0.0, le=2.0)
    llm_max_tokens: int = Field(1024, description="LLM max tokens", ge=1, le=89200)
    llm_timeout: int = Field(60, description="LLM timeout seconds", ge=1)
    llm_output_retries: int = Field(
        1, description="LLM output validation retries", ge=0, le=20
    )
    llm_extra_body: dict[str, Any] | None = Field(
        None, description="Extra request body for OpenAI compatible models"
    )

    # Server
    server_host: str = Field("0.0.0.0", description="Server host")
    server_port: int = Field({{ server_port }}, description="Server port", ge=1, le=65535)

    # Task modules — 由各 Agent 注册，此处仅做配置根
    task_modules: list[str] = Field(
        default_factory=list,
        description="Task registration modules (auto-discovered)",
    )

    enalbe_file_write: bool = Field(False, description="Enable file write API")

    # Thinking stream
    thinking_stream_enabled: bool = Field(
        False, description="Enable thinking stream output"
    )
    thinking_channel_prefix: str = Field(
        "agents:thinking", description="Redis thinking stream key prefix"
    )

    def resolve_llm_model(self) -> str:
        """Resolve the effective LLM model name."""
        return self.llm_model


class WorkerConfig(BaseModel):
    """Worker configuration."""

    queue_name: str = Field("{{ redis_queue_prefix }}:queue", description="Default queue name")
    max_jobs: int = Field(10, description="Max concurrent jobs")
    job_timeout: int = Field(3600, description="Job timeout seconds")
    keep_result: int = Field(86400, description="Keep result seconds")
    health_check_interval: int = Field(
        3600, description="Health check interval seconds"
    )
    retry_jobs: bool = Field(True, description="Retry failed jobs")
    max_tries: int = Field(3, description="Max retry tries")


# ── env loader helpers ──────────────────────────────────────────────


def _load_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if ENV_LOCAL_PATH.exists():
        load_dotenv(ENV_LOCAL_PATH, override=False)
    elif ENV_LEGACY_PATH.exists():
        load_dotenv(ENV_LEGACY_PATH, override=False)
    _ENV_LOADED = True


def _get_env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _get_env_int(name: str, default: int) -> int:
    value = _get_env_str(name)
    return int(value) if value is not None else default


def _get_env_float(name: str, default: float) -> float:
    value = _get_env_str(name)
    return float(value) if value is not None else default


def _get_env_bool(name: str, default: bool) -> bool:
    value = _get_env_str(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _get_env_list(name: str, default: list[str]) -> list[str]:
    value = _get_env_str(name)
    if value is None:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or default


def _get_env_json_dict(name: str) -> dict[str, Any] | None:
    value = _get_env_str(name)
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(
            f"{name} must be a valid JSON object string"
        ) from exc
    if not isinstance(parsed, dict):
        raise ConfigValidationError(f"{name} must be a JSON object")
    return parsed


def _get_env_queue_names() -> dict[str, str]:
    """从环境变量解析多队列配置: TALOS_QUEUE_NAMES=default:queue1,worker2:queue2"""
    value = _get_env_str("TALOS_QUEUE_NAMES")
    if not value:
        return {"default": "{{ redis_queue_prefix }}:queue"}
    result: dict[str, str] = {}
    for pair in value.split(","):
        pair = pair.strip()
        if ":" in pair:
            k, v = pair.split(":", 1)
            result[k.strip()] = v.strip()
    return result or {"default": "{{ redis_queue_prefix }}:queue"}


@lru_cache(maxsize=1)
def load_app_config() -> AppConfig:
    _load_env()
    config_data: dict[str, Any] = {
        "log_level": _get_env_str("TALOS_LOG_LEVEL", "INFO"),
        "log_dir": _get_env_str("TALOS_LOG_DIR", "logs"),
        "auth_enabled": _get_env_bool("TALOS_AUTH_ENABLED", False),
        "auth_secret_key": _get_env_str("TALOS_AUTH_SECRET_KEY", ""),
        "auth_token_expire_hours": _get_env_int("TALOS_AUTH_TOKEN_EXPIRE_HOURS", 24),
        "mongo_host": _get_env_str("TALOS_MONGO_HOST", "127.0.0.1"),
        "mongo_port": _get_env_int("TALOS_MONGO_PORT", 27017),
        "mongo_db_name": _get_env_str("TALOS_MONGO_DATABASE", "{{ mongo_db_name }}"),
        "redis_mode": _get_env_str("TALOS_REDIS_MODE", "standalone"),
        "redis_host": _get_env_str("TALOS_REDIS_HOST", "127.0.0.1"),
        "redis_port": _get_env_int("TALOS_REDIS_PORT", 6379),
        "redis_db": _get_env_int("TALOS_REDIS_DB", 2),
        "redis_cluster_nodes": _get_env_list("TALOS_REDIS_CLUSTER_NODES", []),
        "redis_password": _get_env_str("TALOS_REDIS_PASSWORD", None),
        "redis_max_connections": _get_env_int("TALOS_REDIS_MAX_CONNECTIONS", 10),
        "queue_names": _get_env_queue_names(),
        "llm_provider": _get_env_str("TALOS_LLM_PROVIDER", {% if llm_provider == 'openai' %}"openai"{% elif llm_provider == 'anthropic' %}"anthropic"{% else %}"custom"{% endif %}),
        "llm_base_url": _get_env_str("TALOS_LLM_BASE_URL", ""),
        "llm_api_key": _get_env_str("TALOS_LLM_API_KEY", ""),
        "llm_model": _get_env_str("TALOS_LLM_MODEL", "gpt-4o"),
        "llm_temperature": _get_env_float("TALOS_LLM_TEMPERATURE", 0.2),
        "llm_max_tokens": _get_env_int("TALOS_LLM_MAX_TOKENS", 1024),
        "llm_timeout": _get_env_int("TALOS_LLM_TIMEOUT", 60),
        "llm_output_retries": _get_env_int("TALOS_LLM_OUTPUT_RETRIES", 1),
        "llm_extra_body": _get_env_json_dict("TALOS_LLM_EXTRA_BODY"),
        "server_host": _get_env_str("TALOS_SVR_HOST", "0.0.0.0"),
        "server_port": _get_env_int("TALOS_SVR_PORT", {{ server_port }}),
        "task_modules": _get_env_list("TALOS_TASK_MODULES", []),
        "enalbe_file_write": _get_env_bool("TALOS_ENABLE_FILE_WRITE", False),
        "thinking_stream_enabled": _get_env_bool("TALOS_THINKING_STREAM_ENABLED", False),
        "thinking_channel_prefix": _get_env_str(
            "TALOS_THINKING_CHANNEL_PREFIX", "agents:thinking"
        ),
    }
    return AppConfig(**config_data)


@lru_cache(maxsize=1)
def load_worker_config() -> WorkerConfig:
    _load_env()
    config_data: dict[str, Any] = {
        "queue_name": _get_env_str("TALOS_WORKER_QUEUE_NAME", "{{ redis_queue_prefix }}:queue"),
        "max_jobs": _get_env_int("TALOS_WORKER_MAX_JOBS", 10),
        "job_timeout": _get_env_int("TALOS_WORKER_JOB_TIMEOUT", 3600),
        "keep_result": _get_env_int("TALOS_WORKER_KEEP_RESULT", 86400),
        "health_check_interval": _get_env_int("TALOS_WORKER_HEALTH_CHECK_INTERVAL", 3600),
        "retry_jobs": _get_env_bool("TALOS_WORKER_RETRY_JOBS", True),
        "max_tries": _get_env_int("TALOS_WORKER_MAX_TRIES", 3),
    }
    return WorkerConfig(**config_data)


def get_app_config() -> AppConfig:
    return load_app_config()


def get_worker_config() -> WorkerConfig:
    return load_worker_config()
