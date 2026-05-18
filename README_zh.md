# Talos

[English](README.md)

> **Talos**（塔洛斯）是希腊神话中的青铜巨人，由匠神赫淮斯托斯铸造，日复一日巡视克里特海岸，忠实地执行守护使命。他是神话中最早的"自动化造物"——一个无需休息、不知疲倦的执行者。
>
> 本项目以此为名，正是借喻这一意象：**像铸造塔洛斯一样，快速生成一个结构完整、可稳定运行的 AI Agent 后端服务。** 你定义 Agent 的行为边界，Talos 负责生成基础设施——任务队列、存储、日志、工作流编排。

AI Agent 项目脚手架 — 快速生成基于异步任务队列（Redis + MongoDB）的 AI Agent 后端服务。

## 前置要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)（Python 包管理器）
- MongoDB 和 Redis（开发环境可用 Docker 快速启动）

## 安装

```bash
# 从 GitHub 直接安装（推荐）
uv tool install git+https://github.com/ZyqAlwaysCool/talos.git

# 或克隆后本地安装
git clone https://github.com/ZyqAlwaysCool/talos.git
cd talos
uv tool install .
```

安装后 `talos` 命令全局可用：

```bash
talos --help
```

## 快速开始

```bash
# 0. 更新工具（uv tool 安装方式）
uv tool upgrade talos

# 1. 交互式创建新项目
talos new my-first-agent

# 2. 进入项目
cd my-first-agent

# 3. 安装依赖
uv sync

# 4. 修改 .env.local 中的 MongoDB / Redis 连接信息（如已通过 CLI 配置 LLM 则可跳过）

# 5. 启动服务
bash scripts/start.sh all

# 6. 测试（统一 API）
curl -X POST http://127.0.0.1:19999/agents/task/create \
  -H "Content-Type: application/json" \
  -d '{"task_type": "text_processor", "metadata": {"text": "人工智能正在改变我们的生活方式..."}}'

curl "http://127.0.0.1:19999/agents/task/query?task_id=<返回的 task_id>"

# 7. 停止
bash scripts/stop.sh
```

## 交互式 CLI

```
$ talos new my-agent

  选择项目模板:
    Minimal  — 仅 core 基础库 + 最简 Agent 示例
  ❯ Standard — + LLM 执行器 + Thinking Stream + pocketflow 工作流
    Full     — + SSE 推送 + 工作流归档 + 认证 + Coze/Dify 客户端

  选择 LLM Provider:
    OpenAI 兼容 (Qwen / DeepSeek / etc.)
  ❯ 跳过，稍后手动配置

  是否启用认证模块? (y/N)

  MongoDB 数据库名: (my_agent)
  API 服务端口: (19999)
  Redis 队列前缀: (my_agent)
```

如果选择 LLM Provider 并填写 API Key，`.env.local` 会自动生成，开箱即用。

## 模板说明

| 模板 | 包含内容 | 适用 |
|------|---------|------|
| **Minimal** | core + 统一路由(create/query) + 注册表 + 编排层 + handler 三件套 + 自动发现 | 快速原型、学习 |
| **Standard** | Minimal + LLM 执行器 + Thinking Stream + 工作流归档 + 查询工厂函数 | 标准 AI Agent 服务 |
| **Full** | Standard + SSE 推送 + 认证 + Coze/Dify 客户端 | 生产级服务 |

## 项目结构

```
my-agent/
├── main.py                  # FastAPI 入口
├── worker_main.py           # Worker 入口
├── scripts/
│   ├── start.sh             # 启动脚本
│   └── stop.sh              # 停止脚本
├── core/                    # 基础设施
│   ├── config/              # 配置中心
│   ├── task/                # 异步任务队列（Redis + MongoDB）+ 自动发现
│   ├── storage/             # MongoDB 抽象层
│   ├── logging/             # 日志系统
│   ├── middleware/           # HTTP 中间件
│   ├── auth/                # 认证依赖
│   ├── exceptions/          # 异常体系
│   └── schemas/             # 统一响应模型
├── app/
│   ├── api.py               # 路由聚合
│   └── register_handlers.py # 业务域 handler 注册
├── agents/
│   ├── router/              # 统一 HTTP 路由（薄层）
│   │   ├── task_create.py   # POST /agents/task/create
│   │   └── task_query.py    # GET  /agents/task/query
│   ├── infra/               # Agent 基础设施
│   │   ├── registry/        # 三注册表（create/query/thinking）+ AppRegistries
│   │   ├── orchestrator/    # 任务编排（分发到 handler）
│   │   ├── query/           # 查询结果工厂（task_query_ok/err）
│   │   └── schemas/         # 统一请求/响应 schema
│   └── biz/                 # 业务域
│       └── text_processor/  # 示例 Agent 域
│           ├── __init__.py           # register(registries) 自注册
│           ├── handlers/             # 实现 infra 协议的三个 handler
│           │   ├── create.py         # TaskCreateHandler
│           │   ├── query.py          # TaskQueryHandler
│           │   └── thinking.py       # TaskThinkingResolver
│           ├── repository/           # 持久化
│           ├── workflow/             # DAG 工作流 + task_entry
│           └── schemas.py            # 业务专属数据模型
├── tests/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## 添加新 Agent

在已有项目中快速生成 Agent 域骨架（handler 三件套 + repository + workflow）：

```bash
talos create agent invoice-review

# 选择:
#   Simple   — handlers/ 三件套（create + query + thinking）+ 单 LLM 调用
#   Workflow — handlers/ 三件套 + DAG 工作流 + 多节点 + task_entry
```

然后在 `app/register_handlers.py` 追加一行注册即可接入统一路由体系。任务模块由 Worker 自动发现（`agents/biz/*/workflow/task_entry`），无需手动配置 `TASK_MODULES`。

## Docker 部署

```bash
cp .env.docker.example .env.docker
# 编辑 .env.docker 中的 MongoDB/Redis 地址
docker compose up -d
```

## 日志

启动后日志写入 `logs/` 目录：

```bash
tail -f logs/$(date +%Y-%m-%d).log              # API 日志（按日轮转）
tail -f logs/$(date +%Y-%m-%d)-worker.log       # Worker 日志（按日轮转）
```

## 开发

```bash
git clone https://github.com/ZyqAlwaysCool/talos.git
cd talos
uv sync
uv run pytest tests/ -v
```
