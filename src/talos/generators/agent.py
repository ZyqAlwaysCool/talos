"""Agent 脚手架生成器 — 在已有项目中创建 Agent 骨架."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

console = Console()

# 「talos create agent」生成的是 biz/<name>/handlers/ 结构，接入统一路由体系。
# 旧模板（router.py + service.py + constants.py）已废弃。

AGENT_DOMAIN_INIT_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from agents.infra.registry import AppRegistries
from core.task.base.storage_backend import StorageBackend

{agent_upper}_TASK = "{agent_snake}"


def register(registries: AppRegistries, storage: StorageBackend | None = None) -> None:
    from agents.biz.{agent_snake}.handlers import (
        {agent_pascal}TaskCreateHandler,
        {agent_pascal}TaskQueryHandler,
        {agent_pascal}TaskThinkingResolver,
    )
    registries.create.register({agent_upper}_TASK, {agent_pascal}TaskCreateHandler())
    registries.query.register({agent_upper}_TASK, {agent_pascal}TaskQueryHandler())
    registries.thinking.register(
        {agent_upper}_TASK, {agent_pascal}TaskThinkingResolver(storage=storage)
    )
'''

AGENT_SCHEMAS_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class {agent_pascal}CreateRequest(BaseModel):
    """创建{agent_name}任务请求。"""
    text: str = Field(..., description="待处理的文本")
    options: dict = Field(default_factory=dict, description="可选的额外参数")


class {agent_pascal}QueryResponseData(BaseModel):
    """查询{agent_name}任务响应数据。"""
    task_id: str = Field(..., description="任务ID")
    task_status: str = Field(..., description="任务状态")
    failed_reason: str = Field(default="", description="失败原因")
    result: dict = Field(default_factory=dict, description="任务结果")
'''

AGENT_HANDLER_INIT_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from agents.biz.{agent_snake}.handlers.create import {agent_pascal}TaskCreateHandler
from agents.biz.{agent_snake}.handlers.query import {agent_pascal}TaskQueryHandler
from agents.biz.{agent_snake}.handlers.thinking import {agent_pascal}TaskThinkingResolver

__all__ = [
    "{agent_pascal}TaskCreateHandler",
    "{agent_pascal}TaskQueryHandler",
    "{agent_pascal}TaskThinkingResolver",
]
'''

AGENT_CREATE_HANDLER_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from typing import Any

from agents.biz.{agent_snake}.repository.task_repository import {agent_pascal}TaskRepository
from agents.biz.{agent_snake}.schemas import {agent_pascal}CreateRequest
from agents.biz.{agent_snake}.workflow.task_entry import run_{agent_snake}_task
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus, generate_task_id
from loguru import logger

{agent_upper}_TASK = "{agent_snake}"
{agent_upper}_COLLECTION = "{agent_snake}_tasks"


class {agent_pascal}TaskCreateHandler:
    def __init__(self) -> None:
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        self.queue_backend = queue_backend
        self.repository = {agent_pascal}TaskRepository(storage_backend)

    async def create(self, payload: dict[str, Any], trace_id: str = "") -> str:
        body = {{k: v for k, v in payload.items() if k != "task_type"}}
        request = {agent_pascal}CreateRequest(**body)
        task_id = generate_task_id(prefix={agent_upper}_TASK)

        metadata = request.model_dump()
        metadata["collection_type"] = {agent_upper}_COLLECTION
        if trace_id:
            metadata["trace_id"] = trace_id

        created = await self.repository.create_task(task_id, metadata)
        if not created:
            raise Exception("Failed to create {agent_snake} task")

        task = await self.repository.get_task(task_id)
        if task is None:
            raise Exception(f"Task not found after create: {{task_id}}")

        try:
            queue_task_id = await self.queue_backend.enqueue_task(
                task, run_{agent_snake}_task,
                text=request.text, options=request.options,
            )
        except Exception as exc:
            logger.error("{agent_name} task enqueue failed, task orphaned: {{}} | {{}}", task_id, str(exc))
            try:
                await self.repository.update_status(
                    task_id, TaskStatus.FAILED, error_message=f"Enqueue failed: {{str(exc)}}"
                )
            except Exception:
                pass
            raise

        await self.repository.update_status(task_id, TaskStatus.PENDING, queue_task_id=queue_task_id)
        logger.info("{agent_name} task created: {{}}", task_id)
        return task_id
'''

AGENT_QUERY_HANDLER_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from typing import Any

from agents.biz.{agent_snake}.repository.task_repository import {agent_pascal}TaskRepository
from agents.biz.{agent_snake}.schemas import {agent_pascal}QueryResponseData
from agents.infra.query.result import (
    normalize_task_status,
    task_query_err,
    task_query_ok,
)
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus

TASK_NOT_FOUND = 10001


class {agent_pascal}TaskQueryHandler:
    def __init__(self) -> None:
        storage_backend = TaskManagerFactory.create_mongo_storage()
        self.repository = {agent_pascal}TaskRepository(storage_backend)

    async def __call__(self, task_id: str) -> tuple[int, str, dict[str, Any]]:
        task = await self.repository.get_task(task_id)
        if not task:
            return task_query_err(
                code=TASK_NOT_FOUND, msg="task not found",
                detail={agent_pascal}QueryResponseData(
                    task_id=task_id,
                    task_status=TaskStatus.FAILED.value,
                    failed_reason="task not found",
                ).model_dump(),
            )

        metadata = task.metadata or {{}}
        failed_reason = metadata.get("failed_reason", "") or task.error_message or ""
        result = metadata.get("result", {{}})
        if task.result_data:
            result = task.result_data

        data = {agent_pascal}QueryResponseData(
            task_id=task.task_id,
            task_status=normalize_task_status(task),
            failed_reason=failed_reason,
            result=result,
        )
        return task_query_ok(data.model_dump())
'''

AGENT_THINKING_HANDLER_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from agents.biz.{agent_snake}.repository.task_repository import {agent_pascal}TaskRepository
from agents.infra.schemas.task_thinking import TaskThinkingSnapshot
from core.task.base.storage_backend import StorageBackend
from core.task.factory import TaskManagerFactory


class {agent_pascal}TaskThinkingResolver:
    def __init__(self, storage: StorageBackend | None = None) -> None:
        resolved_storage = storage if storage is not None else TaskManagerFactory.create_mongo_storage()
        self.repository = {agent_pascal}TaskRepository(resolved_storage)

    async def resolve(self, task_id: str) -> TaskThinkingSnapshot:
        task = await self.repository.get_task(task_id)
        if task is None:
            return TaskThinkingSnapshot(task_id=task_id, exists=False)
        metadata = task.metadata if isinstance(task.metadata, dict) else {{}}
        task_status = getattr(task.status, "value", task.status)
        failed_reason = metadata.get("failed_reason") or task.error_message or ""
        return TaskThinkingSnapshot(
            task_id=task_id,
            exists=True,
            status=str(task_status or ""),
            failed_reason=str(failed_reason or ""),
            thinking_stream_enabled=False,
        )
'''

AGENT_REPO_TEMPLATE = '''"""任务持久化。"""

from __future__ import annotations

from typing import Any

from core.task.base.storage_backend import StorageBackend
from core.task.models.task_models import BaseTask, TaskStatus


class {agent_pascal}TaskRepository:
    def __init__(self, storage: StorageBackend):
        self.storage = storage

    async def create_task(self, task_id: str, metadata: dict[str, Any]) -> bool:
        task = BaseTask(task_id=task_id, metadata=metadata)
        return await self.storage.create_task(task)

    async def get_task(self, task_id: str) -> BaseTask | None:
        return await self.storage.get_task(task_id)

    async def update_status(
        self, task_id: str, status: TaskStatus, **kwargs
    ) -> bool:
        return await self.storage.update_task_status(task_id, status, **kwargs)
'''

AGENT_TASK_ENTRY_TEMPLATE = '''"""{agent_name} Worker 任务入口 — 注册到全局 task_registry。"""

from __future__ import annotations

from typing import Any

from loguru import logger

from agents.biz.{agent_snake}.workflow.flow import {agent_pascal}Workflow
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus
from core.task.registry import collection_registry, task_registry

{agent_upper}_COLLECTION = "{agent_snake}_tasks"
{agent_upper}_TASK_PREFIX = "{agent_snake}"

collection_registry.register(
    {agent_upper}_COLLECTION, {agent_upper}_COLLECTION,
    task_id_prefix={agent_upper}_TASK_PREFIX,
)


async def run_{agent_snake}_task(
    text: str, options: dict[str, Any], task_id: str,
    task_retry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    storage = TaskManagerFactory.create_mongo_storage()
    await storage.update_task_status(task_id, TaskStatus.PROCESSING)
    logger.info("start {agent_snake} task: {{}}", task_id)

    try:
        workflow = {agent_pascal}Workflow()
        result = await workflow.run(text=text, options=options)
        await storage.update_task_status(task_id, TaskStatus.COMPLETED, result_data=result)
        return {{"result": result}}
    except Exception as exc:
        logger.error("{agent_name} task failed: {{}} | {{}}", task_id, str(exc))
        await storage.update_task_status(task_id, TaskStatus.FAILED, error_message=str(exc))
        raise


task_registry.register("run_{agent_snake}_task", run_{agent_snake}_task)
'''

AGENT_FLOW_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from typing import Any

from pocketflow import AsyncFlow


class {agent_pascal}Workflow:
    """{agent_name}工作流."""

    def __init__(self):
        pass

    async def run(self, text: str, options: dict[str, Any]) -> dict[str, Any]:
        """执行工作流."""
        # TODO: 实现工作流节点编排
        return {{
            "text_length": len(text),
            "processed": True,
            "options": options,
        }}
'''

AGENT_PROMPT_TEMPLATE = """# system
You are a helpful AI assistant. Process the following text according to the given options.

# user
Text: {{text}}
Options: {{options}}

Please process the text and return the result.
"""


def generate_agent(name: str, *, agent_type: str = "simple") -> None:
    """在已有项目中生成 Agent 骨架（biz/<name>/handlers/ 结构）。"""
    cwd = Path.cwd()
    agent_snake = name.replace("-", "_")
    agent_dir = cwd / "agents" / "biz" / agent_snake

    if agent_dir.exists():
        console.print(f"[red]Agent 目录已存在: {agent_dir}[/red]")
        raise SystemExit(1)

    agent_pascal = "".join(word.capitalize() for word in agent_snake.split("_"))
    agent_upper = agent_snake.upper()
    agent_name = name.replace("_", " ").title()

    namespace = {
        "agent_snake": agent_snake,
        "agent_pascal": agent_pascal,
        "agent_upper": agent_upper,
        "agent_name": agent_name,
    }

    # 目录结构
    dirs = [
        agent_dir,
        agent_dir / "handlers",
        agent_dir / "repository",
        agent_dir / "workflow",
        agent_dir / "workflow" / "nodes",
        agent_dir / "prompts" / agent_snake,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # 核心文件
    files = {
        agent_dir / "__init__.py": AGENT_DOMAIN_INIT_TEMPLATE.format(**namespace),
        agent_dir / "schemas.py": AGENT_SCHEMAS_TEMPLATE.format(**namespace),
        agent_dir / "handlers" / "__init__.py": AGENT_HANDLER_INIT_TEMPLATE.format(**namespace),
        agent_dir / "handlers" / "create.py": AGENT_CREATE_HANDLER_TEMPLATE.format(**namespace),
        agent_dir / "handlers" / "query.py": AGENT_QUERY_HANDLER_TEMPLATE.format(**namespace),
        agent_dir / "handlers" / "thinking.py": AGENT_THINKING_HANDLER_TEMPLATE.format(**namespace),
        agent_dir / "repository" / "__init__.py": "",
        agent_dir / "repository" / "task_repository.py": AGENT_REPO_TEMPLATE.format(**namespace),
    }

    if agent_type == "workflow":
        workflow_files = {
            agent_dir / "workflow" / "__init__.py": "",
            agent_dir / "workflow" / "flow.py": AGENT_FLOW_TEMPLATE.format(**namespace),
            agent_dir / "workflow" / "task_entry.py": AGENT_TASK_ENTRY_TEMPLATE.format(**namespace),
            agent_dir / "workflow" / "nodes" / "__init__.py": "",
            agent_dir / "prompts" / agent_snake / "default.md": AGENT_PROMPT_TEMPLATE.format(**namespace),
        }
        files.update(workflow_files)

    for filepath, content in files.items():
        filepath.write_text(content, encoding="utf-8")
        console.print(f"  [green]✓[/green] {filepath.relative_to(cwd)}")

    console.print(f"\n[green]✔ Agent {agent_pascal} 已创建在 {agent_dir.relative_to(cwd)}[/green]")
    console.print("[dim]请在 app/register_handlers.py 中添加一行注册:[/dim]")
    console.print(f"  from agents.biz.{agent_snake} import register as _register_{agent_snake}")
    console.print(f"  _register_{agent_snake}(app_registries, storage=_shared_storage)")
