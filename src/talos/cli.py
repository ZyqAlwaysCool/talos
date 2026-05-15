"""Talos CLI — AI Agent 脚手架工具."""

from __future__ import annotations

import typer

from talos.commands.create import create_app
from talos.commands.new import new_command

app = typer.Typer(
    name="talos",
    help="AI Agent 脚手架工具 — 快速生成 AI Agent 项目",
    no_args_is_help=True,
)

app.command(name="new")(new_command)
app.add_typer(create_app, name="create", help="在已有项目中生成代码骨架")


@app.callback()
def main() -> None:
    """Talos — AI Agent 脚手架工具."""
