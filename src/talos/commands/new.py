"""talos new — 交互式创建新项目."""

from __future__ import annotations

import questionary
import typer
from questionary import Choice, Separator
from rich.console import Console
from rich.panel import Panel

from talos.generators.project import generate_project

console = Console()

TEMPLATE_CHOICES = [
    Choice(title="Minimal — 仅 core 基础库 + 最简 Agent 示例", value="minimal"),
    Choice(title="Standard — + LLM 执行器 + Thinking Stream + pocketflow 工作流", value="standard"),
    Choice(title="Full — + SSE 推送 + 工作流归档 + 认证 + Coze/Dify 客户端", value="full"),
]

LLM_PROVIDER_CHOICES = [
    Separator("── 主流 Provider ──"),
    Choice(title="OpenAI 兼容 (Qwen / DeepSeek / etc.)", value="openai"),
    Choice(title="Anthropic Claude", value="anthropic"),
    Choice(title="自定义", value="custom"),
    Separator("── ── ── ── ── ──"),
    Choice(title="跳过，稍后手动配置", value="skip"),
]


def _collect_llm_config(llm_provider: str) -> dict[str, str]:
    """根据 provider 收集 LLM 连接信息."""
    if llm_provider == "anthropic":
        base_url_default = "https://api.anthropic.com/v1"
        model_default = "claude-sonnet-4-6"
    elif llm_provider == "openai":
        base_url_default = "https://api.openai.com/v1"
        model_default = "gpt-4o"
    else:
        base_url_default = ""
        model_default = ""

    base_url = questionary.text(
        "LLM Base URL:",
        default=base_url_default,
    ).ask()

    if base_url is None:
        return {}

    api_key = questionary.password(
        "LLM API Key:",
    ).ask()

    if api_key is None:
        return {}

    model_name = questionary.text(
        "LLM Model Name:",
        default=model_default,
    ).ask()

    if model_name is None:
        return {}

    return {
        "base_url": base_url.strip(),
        "api_key": api_key.strip(),
        "model_name": model_name.strip(),
    }


def new_command(project_name: str) -> None:
    """交互式创建新的 AI Agent 项目."""
    console.print(
        Panel.fit(
            "[bold cyan]Talos[/bold cyan] — AI Agent 脚手架",
            subtitle="快速生成 AI Agent 项目",
        )
    )

    # 1. 选择模板
    template = questionary.select(
        "选择项目模板:",
        choices=TEMPLATE_CHOICES,
        use_indicator=True,
    ).ask()

    if template is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    # 2. 配置 LLM
    llm_provider = questionary.select(
        "选择 LLM Provider:",
        choices=LLM_PROVIDER_CHOICES,
        use_indicator=True,
    ).ask()

    if llm_provider is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    llm_config: dict[str, str] = {}
    if llm_provider != "skip":
        console.print(f"\n[bold]配置 {llm_provider} 连接信息:[/bold]")
        llm_config = _collect_llm_config(llm_provider)
        if not llm_config:
            llm_provider = "skip"  # 中途取消视为跳过
            console.print("[dim]LLM 配置已跳过[/dim]")

    # 3. 认证模块
    auth_enabled = questionary.confirm(
        "是否启用认证模块?",
        default=False,
    ).ask()

    if auth_enabled is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    # 4. MongoDB 数据库名
    default_db = project_name.replace("-", "_").replace(" ", "_")
    mongo_db = questionary.text(
        "MongoDB 数据库名:",
        default=default_db,
    ).ask()

    if mongo_db is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    # 5. 服务端口
    server_port = questionary.text(
        "API 服务端口:",
        default="19999",
    ).ask()

    if server_port is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    # 6. Redis 队列前缀
    redis_prefix = questionary.text(
        "Redis 队列前缀:",
        default=project_name.replace("-", "_").replace(" ", "_"),
    ).ask()

    if redis_prefix is None:
        console.print("[yellow]已取消[/yellow]")
        raise typer.Exit(0)

    context = {
        "project_name": project_name,
        "project_slug": project_name.replace("-", "_").replace(" ", "_"),
        "template": template,
        "llm_provider": llm_provider if llm_provider != "skip" else "openai",
        "llm_configured": llm_provider != "skip",
        "auth_enabled": auth_enabled,
        "mongo_db_name": mongo_db,
        "server_port": int(server_port),
        "redis_queue_prefix": redis_prefix,
        # llm 连接信息（仅当用户填写时生效）
        "llm_base_url": llm_config.get("base_url", ""),
        "llm_api_key": llm_config.get("api_key", ""),
        "llm_model_name": llm_config.get("model_name", ""),
    }

    generate_project(context)
