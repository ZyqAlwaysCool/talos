"""text_processor Agent 测试."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agents.text_processor.schemas import TextProcessorCreateRequest
from agents.text_processor.service import TextProcessorService
from core.task.models.task_models import BaseTask, TaskStatus

SAMPLE_TEXT = (
    "Artificial intelligence has transformed how we interact with technology. "
    "From voice assistants to autonomous vehicles, AI systems are becoming "
    "ubiquitous in daily life. However, concerns about privacy, bias, and "
    "job displacement remain significant challenges that society must address."
)


@pytest.fixture
def mock_backends():
    with patch(
        "agents.text_processor.service.TaskManagerFactory.create_default_backends"
    ) as mock_factory:
        queue_backend = AsyncMock()
        queue_backend.enqueue_task.return_value = "test_queue_id"
        storage_backend = AsyncMock()
        storage_backend.create_task.return_value = True
        storage_backend.get_task.return_value = BaseTask(
            task_id="text_processor_test_id",
            metadata={"text": SAMPLE_TEXT},
            status=TaskStatus.COMPLETED,
            result_data={
                "result": {
                    "preprocessed": {"word_count": 40, "char_count": 280},
                    "summary": "人工智能正在改变日常生活，同时也带来了隐私和就业等挑战。",
                    "used_llm": False,
                }
            },
        )
        mock_factory.return_value = (queue_backend, storage_backend)
        yield queue_backend, storage_backend


@pytest.mark.asyncio
async def test_create_task(mock_backends):
    queue_backend, storage_backend = mock_backends
    service = TextProcessorService()
    service.queue_backend = queue_backend
    service.repository.storage = storage_backend

    request = TextProcessorCreateRequest(text=SAMPLE_TEXT)
    task_id = await service.create_task(request)

    assert task_id.startswith("text_processor_")
    queue_backend.enqueue_task.assert_called_once()


@pytest.mark.asyncio
async def test_query_task(mock_backends):
    queue_backend, storage_backend = mock_backends
    service = TextProcessorService()
    service.queue_backend = queue_backend
    service.repository.storage = storage_backend

    code, msg, data = await service.query_task("text_processor_test_id")
    assert code == 0
    assert data.task_status == "completed"


@pytest.mark.asyncio
async def test_query_not_found(mock_backends):
    queue_backend, storage_backend = mock_backends
    storage_backend.get_task.return_value = None
    service = TextProcessorService()
    service.queue_backend = queue_backend
    service.repository.storage = storage_backend

    code, msg, data = await service.query_task("nonexistent")
    assert code == 10001


@pytest.mark.asyncio
async def test_preprocess_node():
    from agents.text_processor.workflow.nodes.preprocess import PreprocessNode

    node = PreprocessNode()
    result = await node.process("hello world test", {})
    assert result["word_count"] == 3
    assert result["char_count"] == 16


@pytest.mark.asyncio
async def test_summarize_node_no_llm(monkeypatch):
    """未配置 LLM 时应使用 hardcode fallback."""
    monkeypatch.delenv("TALOS_LLM_API_KEY", raising=False)

    from agents.text_processor.workflow.nodes.summarize import SummarizeNode

    node = SummarizeNode()
    preprocessed = {"word_count": 3, "char_count": 16, "preview": "hello world test"}
    result = await node.process(
        text="hello world test", preprocessed=preprocessed, options={}
    )
    assert result["used_llm"] is False
    assert "hello world test" in result["summary"]


def test_llm_detection():
    """有 API Key 时 _llm_available 应返回 True."""
    import os
    from agents.text_processor.workflow.nodes.summarize import _llm_available

    os.environ["TALOS_LLM_API_KEY"] = "sk-test"
    assert _llm_available() is True
    del os.environ["TALOS_LLM_API_KEY"]
    assert _llm_available() is False
