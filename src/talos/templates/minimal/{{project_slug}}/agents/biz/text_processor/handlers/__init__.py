"""text_processor handler 聚合 re-export。"""

from agents.biz.text_processor.handlers.create import TextProcessorTaskCreateHandler
from agents.biz.text_processor.handlers.query import TextProcessorTaskQueryHandler
from agents.biz.text_processor.handlers.thinking import (
    TextProcessorTaskThinkingResolver,
)

__all__ = [
    "TextProcessorTaskCreateHandler",
    "TextProcessorTaskQueryHandler",
    "TextProcessorTaskThinkingResolver",
]
