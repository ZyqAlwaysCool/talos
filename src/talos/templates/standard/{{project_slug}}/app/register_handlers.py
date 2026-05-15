"""应用组合根：各域 register() 依次装配 handler。import 须在挂载路由前完成。"""

from __future__ import annotations

from agents.infra.registry import app_registries
from core.task.factory import TaskManagerFactory

_shared_storage = TaskManagerFactory.create_mongo_storage()

from agents.biz.text_processor import register as _register_text_processor

_register_text_processor(app_registries, storage=_shared_storage)
