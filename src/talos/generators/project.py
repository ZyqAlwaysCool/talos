"""项目生成器 — 从模板渲染完整项目."""

from __future__ import annotations

import shutil
import stat
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from rich.console import Console

console = Console()


def generate_project(context: dict[str, Any]) -> None:
    """根据上下文渲染模板并生成项目到目标目录."""
    project_name = str(context["project_name"])
    template_name = str(context["template"])
    target_dir = Path.cwd() / project_name

    if target_dir.exists():
        console.print(f"[red]目录 {target_dir} 已存在[/red]")
        raise SystemExit(1)

    templates_dir = Path(__file__).resolve().parents[1] / "templates" / template_name

    if not templates_dir.is_dir():
        console.print(f"[red]模板 '{template_name}' 未找到: {templates_dir}[/red]")
        raise SystemExit(1)

    console.print(f"[cyan]正在生成项目: {project_name}[/cyan]")
    console.print(f"  模板: {template_name}")
    console.print(f"  目标: {target_dir}")

    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(),
        keep_trailing_newline=True,
    )

    _render_directory(
        env, templates_dir, target_dir, context, is_root=True, project_name=project_name
    )

    # 如果用户填写了 LLM 配置，直接生成 .env.local
    llm_configured = bool(context.get("llm_configured"))
    if llm_configured:
        _write_env_local(target_dir, context)

    console.print(f"\n[green]✔ 项目已创建在 {target_dir}[/green]")

    if llm_configured:
        console.print("\n[bold]下一步:[/bold]")
        console.print(f"  cd {project_name}")
        console.print("  uv sync")
        console.print("  bash scripts/start.sh all            # 启动 API + Worker")
        console.print("")
        console.print("[dim]LLM 配置已写入 .env.local，如需修改请编辑该文件[/dim]")
    else:
        console.print("\n[bold]下一步:[/bold]")
        console.print(f"  cd {project_name}")
        console.print("  cp .env.example .env.local   # 编辑 .env.local 填入 MongoDB/Redis/LLM 配置")
        console.print("  uv sync")
        console.print("  bash scripts/start.sh all            # 启动 API + Worker")

    console.print("")
    console.print("[dim]或使用 Docker:[/dim]")
    console.print("  cp .env.docker.example .env.docker")
    console.print("  docker compose up -d")


def _write_env_local(target_dir: Path, context: dict[str, Any]) -> None:
    """直接生成 .env.local，包含用户填入的 LLM 配置."""
    project_slug = context["project_slug"]
    mongo_db = context["mongo_db_name"]
    server_port = context["server_port"]
    redis_prefix = context["redis_queue_prefix"]
    llm_provider = context.get("llm_provider", "openai")
    llm_base_url = context.get("llm_base_url", "")
    llm_api_key = context.get("llm_api_key", "")
    llm_model_name = context.get("llm_model_name", "")
    auth_enabled = context.get("auth_enabled", False)

    env_content = f"""# ── Talos Agent 环境变量 (自动生成) ──

# Server
TALOS_SVR_HOST=0.0.0.0
TALOS_SVR_PORT={server_port}

# MongoDB
TALOS_MONGO_HOST=127.0.0.1
TALOS_MONGO_PORT=27017
TALOS_MONGO_DATABASE={mongo_db}

# Redis
TALOS_REDIS_MODE=standalone
TALOS_REDIS_HOST=127.0.0.1
TALOS_REDIS_PORT=6379
TALOS_REDIS_DB=2
TALOS_REDIS_PASSWORD=

# Queue
TALOS_QUEUE_NAMES=default:{redis_prefix}:queue
TALOS_WORKER_QUEUE_NAME={redis_prefix}:queue
TALOS_WORKER_MAX_JOBS=10
TALOS_WORKER_JOB_TIMEOUT=3600
TALOS_WORKER_RETRY_JOBS=true
TALOS_WORKER_MAX_TRIES=3

# LLM
TALOS_LLM_PROVIDER={llm_provider}
TALOS_LLM_BASE_URL={llm_base_url}
TALOS_LLM_API_KEY={llm_api_key}
TALOS_LLM_MODEL={llm_model_name}
TALOS_LLM_TEMPERATURE=0.2
TALOS_LLM_MAX_TOKENS=1024
TALOS_LLM_TIMEOUT=60

# Task modules
TALOS_TASK_MODULES=agents.text_processor.workflow.task_entry

# Auth
TALOS_AUTH_ENABLED={'true' if auth_enabled else 'false'}

# Logging
TALOS_LOG_LEVEL=INFO
"""
    (target_dir / ".env.local").write_text(env_content, encoding="utf-8")
    console.print("  [dim].env.local 已生成 (含 LLM 配置)[/dim]")


def _render_directory(
    env: Environment,
    src_dir: Path,
    dst_dir: Path,
    context: dict[str, Any],
    *,
    is_root: bool = False,
    project_name: str = "",
) -> None:
    """递归渲染模板目录."""
    dst_dir.mkdir(parents=True, exist_ok=True)

    for item in sorted(src_dir.iterdir()):
        if item.name == "__pycache__":
            continue
        # 检查文件名（剥离 .jinja2 后缀后）是否在允许的隐藏文件列表中
        name = item.name
        base_name = name[: -len(".jinja2")] if name.endswith(".jinja2") else name
        if name.startswith(".") and base_name not in (".gitignore", ".env.example", ".env.docker.example"):
            continue

        rel_path = item.relative_to(src_dir)
        dst_path = _resolve_dst_path(dst_dir, rel_path, context, is_root, project_name)

        if item.is_dir():
            _render_directory(env, item, dst_path, context)
        else:
            _render_file(env, item, dst_path, context)


def _resolve_dst_path(
    dst_dir: Path,
    rel_path: Path,
    context: dict[str, Any],
    is_root: bool,
    project_name: str,
) -> Path:
    """解析目标路径, 处理模板变量替换."""
    name = rel_path.name

    # 处理 {{project_slug}} 根目录重命名
    if is_root and name.startswith("{{") and name.endswith("}}"):
        return dst_dir

    # Jinja2 文件名变量替换
    rendered_name = Environment().from_string(name).render(**context)
    # 去掉 .jinja2 后缀
    if rendered_name.endswith(".jinja2"):
        rendered_name = rendered_name[: -len(".jinja2")]

    # dst_dir 即为目标父目录
    return dst_dir / rendered_name


def _render_file(
    env: Environment,
    src_path: Path,
    dst_path: Path,
    context: dict[str, Any],
) -> None:
    """渲染单个模板文件."""
    # 只对文本文件做 Jinja2 渲染，二进制文件直接拷贝
    try:
        raw = src_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, Exception):
        shutil.copy2(src_path, dst_path)
        return

    try:
        template = env.from_string(raw)
        content = template.render(**context)
        dst_path.write_text(content, encoding="utf-8")

        # 保持可执行权限
        if src_path.suffix == ".sh" or ".sh" in src_path.name:
            dst_path.chmod(dst_path.stat().st_mode | stat.S_IEXEC)
    except Exception:
        # 渲染失败时直接写入原始内容（非 Jinja2 文件）
        dst_path.write_text(raw, encoding="utf-8")
