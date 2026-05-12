"""talos create — 在已有项目中生成代码骨架."""

from __future__ import annotations

import questionary
import typer
from questionary import Choice
from rich.console import Console

from talos.generators.agent import generate_agent

create_app = typer.Typer(help="在已有项目中生成代码骨架", no_args_is_help=True)
console = Console()


@create_app.command(name="agent")
def create_agent(name: str) -> None:
    """在已有项目中创建新的 Agent 骨架."""
    agent_type = questionary.select(
        "选择 Agent 类型:",
        choices=[
            Choice(title="Simple — router + service + 单个 LLM 调用", value="simple"),
            Choice(title="Workflow — router + service + DAG 工作流 + 多节点", value="workflow"),
        ],
        use_indicator=True,
    ).ask()

    if agent_type is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    generate_agent(name, agent_type=agent_type)
