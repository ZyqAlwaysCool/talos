"""Agent 脚手架生成器 — 在已有项目中创建 Agent 骨架."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

console = Console()

AGENT_INIT_TEMPLATE = '''"""
Description:
Author:
Date:
"""
'''

AGENT_CONSTANTS_TEMPLATE = '''"""
Description:
Author:
Date:
"""

# 任务类型标识
{agent_upper}_TASK = "{agent_snake}"

# 任务前缀
{agent_upper}_TASK_PREFIX = "{agent_snake}"

# MongoDB collection 名称
{agent_upper}_COLLECTION = "{agent_snake}_tasks"
'''

AGENT_ROUTER_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger

from agents.{agent_snake}.schemas import (
    {agent_pascal}CreateRequest,
    {agent_pascal}QueryResponseData,
)
from agents.{agent_snake}.service import {agent_pascal}Service
from core.exceptions import generate_trace_id
from core.schemas import BaseResponse

{agent_snake}_router = APIRouter(
    prefix="/{agent_snake}",
    tags=["{agent_snake}"],
)
{agent_var}_service = {agent_pascal}Service()


@{agent_snake}_router.post(
    "/create",
    summary="创建{agent_name}任务",
    description="创建{agent_name}任务",
    response_model=BaseResponse,
)
async def create_{agent_snake}_task(
    request: Request, payload: {agent_pascal}CreateRequest
) -> BaseResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info(f"{{agent_name}} create request - TraceID: {{trace_id}}")
    task_id = await {agent_var}_service.create_task(payload, trace_id=trace_id)
    return BaseResponse.success(data={{"task_id": task_id}}, trace_id=trace_id)


@{agent_snake}_router.get(
    "/query",
    summary="查询{agent_name}任务状态",
    description="查询{agent_name}任务状态",
    response_model=BaseResponse,
)
async def query_{agent_snake}_task(
    request: Request,
    task_id: Annotated[str, Query(..., description="{agent_name} task id")],
) -> BaseResponse:
    trace_id = getattr(request.state, "trace_id", generate_trace_id())
    logger.info(f"{{agent_name}} query request - TraceID: {{trace_id}}")
    code, msg, data = await {agent_var}_service.query_task(task_id)
    return BaseResponse(code=code, msg=msg, data=data.model_dump(), trace_id=trace_id)
'''

AGENT_SCHEMAS_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class {agent_pascal}CreateRequest(BaseModel):
    """创建{agent_name}任务请求."""

    text: str = Field(
        ...,
        description="待处理的文本",
        examples=["Hello, this is a sample text for processing."],
    )
    options: dict = Field(
        default_factory=dict,
        description="可选的额外参数",
        examples=[{{"language": "en"}}],
    )


class {agent_pascal}QueryResponseData(BaseModel):
    """查询{agent_name}任务响应数据."""
    task_id: str = Field(..., description="任务ID")
    task_status: str = Field(..., description="任务状态")
    failed_reason: str = Field("", description="失败原因")
    result: dict = Field(default_factory=dict, description="任务结果")
'''

AGENT_SERVICE_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from loguru import logger

from agents.{agent_snake}.constants import {agent_upper}_TASK_PREFIX, {agent_upper}_COLLECTION
from agents.{agent_snake}.repository.task_repository import {agent_pascal}TaskRepository
from agents.{agent_snake}.schemas import {agent_pascal}QueryResponseData
from agents.{agent_snake}.workflow.task_entry import run_{agent_snake}_task
from core.exceptions.exceptions import BaseBusinessException
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus, generate_task_id


class {agent_pascal}Service:
    def __init__(self):
        queue_backend, storage_backend = TaskManagerFactory.create_default_backends()
        self.queue_backend = queue_backend
        self.repository = {agent_pascal}TaskRepository(storage_backend)

    async def create_task(self, request, trace_id: str = "") -> str:
        task_id = generate_task_id(prefix={agent_upper}_TASK_PREFIX)
        metadata = request.model_dump()
        metadata["collection_type"] = {agent_upper}_COLLECTION
        if trace_id:
            metadata["trace_id"] = trace_id

        created = await self.repository.create_task(task_id, metadata)
        if not created:
            raise Exception("Failed to create task")

        task = await self.repository.get_task(task_id)
        if task is None:
            raise Exception(f"Task not found after create: {{task_id}}")

        try:
            queue_task_id = await self.queue_backend.enqueue_task(
                task,
                run_{agent_snake}_task,
                text=request.text,
                options=request.options,
            )
        except Exception as exc:
            logger.error("{agent_name}任务入队失败: {{}} | {{}}", task_id, str(exc))
            try:
                await self.repository.update_status(
                    task_id, TaskStatus.FAILED, error_message=f"入队失败: {{str(exc)}}"
                )
            except Exception:
                pass
            raise

        await self.repository.update_status(task_id, TaskStatus.PENDING, queue_task_id=queue_task_id)
        logger.info(f"{{agent_name}} task created: {{task_id}}")
        return task_id

    async def query_task(self, task_id: str) -> tuple[int, str, {agent_pascal}QueryResponseData]:
        task = await self.repository.get_task(task_id)
        if not task:
            return (
                10001,
                "{agent_name} task not found",
                {agent_pascal}QueryResponseData(
                    task_id=task_id,
                    task_status=TaskStatus.FAILED.value,
                    failed_reason="task not found",
                ),
            )

        metadata = task.metadata or {{}}
        task_status = task.status if isinstance(task.status, str) else task.status.value
        failed_reason = metadata.get("failed_reason", "") or task.error_message or ""
        result = metadata.get("result", {{}})

        return 0, "ok", {agent_pascal}QueryResponseData(
            task_id=task.task_id,
            task_status=task_status,
            failed_reason=failed_reason,
            result=result,
        )
'''

AGENT_REPO_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from core.task.models.task_models import BaseTask, TaskStatus
from core.task.base.storage_backend import StorageBackend


class {agent_pascal}TaskRepository:
    def __init__(self, storage: StorageBackend):
        self.storage = storage

    async def create_task(self, task_id: str, metadata: dict[str, Any]) -> bool:
        task = BaseTask(task_id=task_id, metadata=metadata)
        return await self.storage.create_task(task)

    async def get_task(self, task_id: str) -> BaseTask | None:
        return await self.storage.get_task(task_id)

    async def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: str | None = None,
        queue_task_id: str | None = None,
    ) -> bool:
        kwargs: dict[str, Any] = {{}}
        if error_message:
            kwargs["error_message"] = error_message
        if queue_task_id:
            kwargs["queue_task_id"] = queue_task_id
        return await self.storage.update_task_status(task_id, status, **kwargs)
'''

AGENT_TASK_ENTRY_TEMPLATE = '''"""
Description:
Author:
Date:
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from agents.{agent_snake}.constants import {agent_upper}_COLLECTION, {agent_upper}_TASK_PREFIX
from agents.{agent_snake}.workflow.flow import {agent_pascal}Workflow
from core.task.factory import TaskManagerFactory
from core.task.models.task_models import TaskStatus
from core.task.registry import collection_registry, task_registry

# 注册 collection 映射
collection_registry.register(
    {agent_upper}_COLLECTION,
    {agent_upper}_COLLECTION,
    task_id_prefix={agent_upper}_TASK_PREFIX,
)


async def run_{agent_snake}_task(
    text: str,
    options: dict[str, Any],
    task_id: str,
    task_retry_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """{agent_name}任务入口."""
    storage = TaskManagerFactory.create_mongo_storage()
    await storage.update_task_status(task_id, TaskStatus.PROCESSING)
    logger.info(f"start {agent_snake} task: {{task_id}}")

    try:
        workflow = {agent_pascal}Workflow()
        result = await workflow.run(text=text, options=options)

        await storage.update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            result_data=result,
        )
        return {{"result": result}}
    except Exception as exc:
        logger.error(f"{{agent_name}} task failed: {{task_id}} | {{str(exc)}}")
        await storage.update_task_status(
            task_id,
            TaskStatus.FAILED,
            error_message=str(exc),
        )
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
    """在已有项目中生成 Agent 骨架."""
    cwd = Path.cwd()
    agent_dir = cwd / "agents" / name.replace("-", "_")

    if agent_dir.exists():
        console.print(f"[red]Agent 目录已存在: {agent_dir}[/red]")
        raise SystemExit(1)

    # 命名转换
    agent_snake = name.replace("-", "_")
    agent_pascal = "".join(word.capitalize() for word in agent_snake.split("_"))
    agent_upper = agent_snake.upper()
    agent_name = name.replace("_", " ").title()

    namespace = {
        "agent_snake": agent_snake,
        "agent_pascal": agent_pascal,
        "agent_upper": agent_upper,
        "agent_name": agent_name,
        "agent_var": agent_snake,
    }

    # 创建目录结构
    dirs = [
        agent_dir,
        agent_dir / "repository",
        agent_dir / "workflow",
        agent_dir / "workflow" / "nodes",
        agent_dir / "prompts" / agent_snake,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # 生成文件
    files = {
        agent_dir / "__init__.py": AGENT_INIT_TEMPLATE.format(**namespace),
        agent_dir / "constants.py": AGENT_CONSTANTS_TEMPLATE.format(**namespace),
        agent_dir / "router.py": AGENT_ROUTER_TEMPLATE.format(**namespace),
        agent_dir / "schemas.py": AGENT_SCHEMAS_TEMPLATE.format(**namespace),
        agent_dir / "service.py": AGENT_SERVICE_TEMPLATE.format(**namespace),
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
