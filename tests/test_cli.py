"""CLI 工具测试."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# 将 talos 包加入 path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_cli_help():
    """talos --help 正常输出."""
    import subprocess

    result = subprocess.run(
        ["uv", "run", "talos", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0
    assert "new" in result.stdout
    assert "create" in result.stdout


def test_cli_create_agent_help():
    """talos create agent --help 正常输出."""
    import subprocess

    result = subprocess.run(
        ["uv", "run", "talos", "create", "agent", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0
    assert "NAME" in result.stdout


def test_generate_agent_simple(tmp_path: Path):
    """talos create agent 生成 Simple Agent (无交互式选择, 直接调用 generator)."""
    from talos.generators.agent import generate_agent

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "agents").mkdir()
        generate_agent("test_bot", agent_type="simple")

        agent_dir = tmp_path / "agents" / "test_bot"
        assert agent_dir.is_dir()
        assert (agent_dir / "__init__.py").exists()
        assert (agent_dir / "constants.py").exists()
        assert (agent_dir / "router.py").exists()
        assert (agent_dir / "service.py").exists()
        assert (agent_dir / "schemas.py").exists()
        assert (agent_dir / "repository" / "task_repository.py").exists()

        # Simple 类型不应有 workflow
        assert not (agent_dir / "workflow" / "task_entry.py").exists()

        # 验证常量内容
        constants = (agent_dir / "constants.py").read_text()
        assert "TEST_BOT_TASK" in constants

        # 验证 router 内容
        router = (agent_dir / "router.py").read_text()
        assert "test_bot_router" in router
        assert "TestBotService" in router
    finally:
        os.chdir(original_cwd)


def test_generate_agent_workflow(tmp_path: Path):
    """talos create agent 生成 Workflow Agent."""
    from talos.generators.agent import generate_agent

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "agents").mkdir()
        generate_agent("invoice_review", agent_type="workflow")

        agent_dir = tmp_path / "agents" / "invoice_review"
        assert agent_dir.is_dir()
        assert (agent_dir / "workflow" / "flow.py").exists()
        assert (agent_dir / "workflow" / "task_entry.py").exists()
        assert (agent_dir / "workflow" / "nodes" / "__init__.py").exists()
        assert (agent_dir / "prompts" / "invoice_review" / "default.md").exists()

        # 验证 task_entry 注册逻辑
        task_entry = (agent_dir / "workflow" / "task_entry.py").read_text()
        assert "run_invoice_review_task" in task_entry
        assert 'task_registry.register("run_invoice_review_task"' in task_entry
        assert "collection_registry.register" in task_entry
    finally:
        os.chdir(original_cwd)


def test_generate_agent_duplicate_dir(tmp_path: Path):
    """重复创建同名 Agent 应报错."""
    from talos.generators.agent import generate_agent

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        (tmp_path / "agents").mkdir()
        generate_agent("my_agent")
        with pytest.raises(SystemExit):
            generate_agent("my_agent")
    finally:
        os.chdir(original_cwd)


def test_project_generator_missing_template(tmp_path: Path):
    """模板不存在时应报错."""
    from talos.generators.project import generate_project

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        context = {
            "project_name": "test-proj",
            "project_slug": "test_proj",
            "template": "nonexistent",
            "llm_provider": "openai",
            "auth_enabled": False,
            "mongo_db_name": "test_db",
            "server_port": 19999,
            "redis_queue_prefix": "test",
        }
        with pytest.raises(SystemExit):
            generate_project(context)
    finally:
        os.chdir(original_cwd)


def test_naming_conventions():
    """命名转换正确性."""
    # 验证 snake_case → PascalCase 转换
    assert "".join(word.capitalize() for word in "hello_world".split("_")) == "HelloWorld"
    assert "".join(word.capitalize() for word in "text_processor".split("_")) == "TextProcessor"


def test_generate_minimal_project(tmp_path: Path):
    """生成 Minimal 模板项目，验证目录结构和文件内容."""
    from talos.generators.project import generate_project

    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        context = {
            "project_name": "my-test-agent",
            "project_slug": "my_test_agent",
            "template": "minimal",
            "llm_provider": "openai",
            "auth_enabled": False,
            "mongo_db_name": "my_test_db",
            "server_port": 18888,
            "redis_queue_prefix": "my_test_queue",
        }
        generate_project(context)

        project_dir = tmp_path / "my-test-agent"
        assert project_dir.is_dir(), "项目目录应存在"

        # 核心文件
        assert (project_dir / "pyproject.toml").exists()
        assert (project_dir / ".env.example").exists()
        assert (project_dir / ".gitignore").exists()
        assert (project_dir / "Dockerfile").exists()
        assert (project_dir / "docker-compose.yml").exists()
        assert (project_dir / "main.py").exists()
        assert (project_dir / "worker_main.py").exists()

        # core/ 模块
        core_dir = project_dir / "core"
        assert (core_dir / "config" / "config_center.py").exists()
        assert (core_dir / "config" / "error_codes.py").exists()
        assert (core_dir / "exceptions" / "exceptions.py").exists()
        assert (core_dir / "logging" / "logger.py").exists()
        assert (core_dir / "middleware" / "base.py").exists()
        assert (core_dir / "schemas" / "base_resp_model_define.py").exists()
        assert (core_dir / "storage" / "mongo_storage.py").exists()
        assert (core_dir / "task" / "worker.py").exists()
        assert (core_dir / "task" / "worker_manager.py").exists()
        assert (core_dir / "task" / "factory.py").exists()
        assert (core_dir / "task" / "registry.py").exists()

        # text_processor Agent
        agent_dir = project_dir / "agents" / "text_processor"
        assert (agent_dir / "router.py").exists()
        assert (agent_dir / "service.py").exists()
        assert (agent_dir / "schemas.py").exists()
        assert (agent_dir / "constants.py").exists()
        assert (agent_dir / "workflow" / "flow.py").exists()
        assert (agent_dir / "workflow" / "task_entry.py").exists()
        assert (agent_dir / "workflow" / "nodes" / "preprocess.py").exists()
        assert (agent_dir / "workflow" / "nodes" / "summarize.py").exists()
        assert (agent_dir / "prompts" / "text_processor" / "summarize.md").exists()

        # scripts/
        assert (project_dir / "scripts" / "start.sh").exists()
        assert (project_dir / "scripts" / "stop.sh").exists()

        # 验证 Jinja2 变量替换
        pyproject = (project_dir / "pyproject.toml").read_text()
        assert "my_test_agent" in pyproject

        env_example = (project_dir / ".env.example").read_text()
        assert "TALOS_SVR_PORT=18888" in env_example
        assert "TALOS_MONGO_DATABASE=my_test_db" in env_example
        assert "my_test_queue" in env_example

        docker_compose = (project_dir / "docker-compose.yml").read_text()
        assert '"18888:18888"' in docker_compose

        config_center = (core_dir / "config" / "config_center.py").read_text()
        assert 'Field("my_test_db"' in config_center
        assert 'Field(18888' in config_center

        # 验证零业务词残留
        all_text = ""
        for f in project_dir.rglob("*.py"):
            all_text += f.read_text()
        for f in project_dir.rglob("*.yml"):
            all_text += f.read_text()
        for f in project_dir.rglob("*.md"):
            all_text += f.read_text()

        business_words = ["gat", "GAT", "travel", "economic_review", "contract", "oss_gat"]
        for word in business_words:
            assert word not in all_text, f"业务词残留: {word}"

    finally:
        os.chdir(original_cwd)

def test_generate_standard_project(tmp_path: Path):
    """生成 Standard 模板，验证 infra 模块存在且无业务词残留."""
    from talos.generators.project import generate_project
    original_cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        context = {
            "project_name": "test-standard",
            "project_slug": "test_standard",
            "template": "standard",
            "llm_provider": "anthropic",
            "auth_enabled": False,
            "mongo_db_name": "test_db",
            "server_port": 19999,
            "redis_queue_prefix": "test_std",
        }
        generate_project(context)
        project_dir = tmp_path / "test-standard"
        assert project_dir.is_dir()
        assert (project_dir / "core" / "task" / "worker.py").exists()
        infra_dir = project_dir / "agents" / "infra"
        assert (infra_dir / "llm" / "executor.py").exists()
        assert (infra_dir / "llm" / "thinking" / "runtime.py").exists()
        assert (infra_dir / "workflow_archive" / "integration.py").exists()
        assert not (infra_dir / "sse" / "router.py").exists()
    finally:
        os.chdir(original_cwd)
