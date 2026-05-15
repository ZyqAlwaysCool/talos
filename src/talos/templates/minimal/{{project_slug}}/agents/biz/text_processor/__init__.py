"""text_processor 域装配：向全局注册表注册 create/query/thinking。"""

from __future__ import annotations

from agents.infra.registry import AppRegistries
from core.task.base.storage_backend import StorageBackend

TEXT_PROCESSOR_TASK = "text_processor"


def register(registries: AppRegistries, storage: StorageBackend | None = None) -> None:
    from agents.biz.text_processor.handlers import (
        TextProcessorTaskCreateHandler,
        TextProcessorTaskQueryHandler,
        TextProcessorTaskThinkingResolver,
    )
    registries.create.register(TEXT_PROCESSOR_TASK, TextProcessorTaskCreateHandler())
    registries.query.register(TEXT_PROCESSOR_TASK, TextProcessorTaskQueryHandler())
    registries.thinking.register(TEXT_PROCESSOR_TASK, TextProcessorTaskThinkingResolver(storage=storage))
