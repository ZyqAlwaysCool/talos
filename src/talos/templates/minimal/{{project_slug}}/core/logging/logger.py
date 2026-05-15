"""
Description: 日志配置
"""

import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from core.config.config_center import get_app_config

from .context import get_task_id


def _inject_task_id(record: Any) -> None:
    if isinstance(record, dict):
        record.setdefault("extra", {})
        record["extra"].setdefault("task_id", get_task_id())


def setup_logger(custom_dir: str | None = None, file_suffix: str | None = None) -> None:
    """按每天一个独立文件输出日志."""
    app_config = get_app_config()
    log_dir = Path(custom_dir or app_config.log_dir).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)

    level = app_config.log_level
    suffix = f"-{file_suffix}" if file_suffix else ""
    file_name = f"{{time:YYYY-MM-DD}}{suffix}.log"
    retention = "30 days"
    compression = "zip"
    enqueue = (
        os.getenv("LOGURU_ENQUEUE", "true").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<magenta>task_id={extra[task_id]}</magenta> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.remove()
    logger.configure(patcher=_inject_task_id)
    logger.add(
        log_dir / file_name,
        level=level,
        rotation="00:00",
        retention=retention,
        compression=compression,
        encoding="utf-8",
        enqueue=enqueue,
        format=fmt,
    )
    logger.add(sys.stdout, level=level, format=fmt)
    logger.info("Logger initialized")
