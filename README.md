# Talos

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
# 1. 交互式创建新项目
talos new my-first-agent

# 2. 进入项目
cd my-first-agent

# 3. 安装依赖
uv sync

# 4. 修改 .env.local 中的 MongoDB / Redis 连接信息（如已通过 CLI 配置 LLM 则可跳过）

# 5. 启动服务
bash scripts/start.sh all

# 6. 测试
curl -X POST http://127.0.0.1:19999/text_processor/create \
  -H "Content-Type: application/json" \
  -d '{"text": "人工智能正在改变我们的生活方式..."}'

curl "http://127.0.0.1:19999/text_processor/query?task_id=<返回的 task_id>"

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
| **Minimal** | `core/`（任务队列、MongoDB、Redis）+ 示例 Agent | 快速原型、学习 |
| **Standard** | Minimal + LLM 执行器 + Thinking Stream + 工作流归档 | 标准 AI Agent 服务 |
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
│   ├── task/                # 异步任务队列（Redis 后端 + MongoDB 存储）
│   ├── storage/             # MongoDB 抽象层
│   ├── logging/             # 日志系统
│   ├── middleware/           # HTTP 中间件
│   ├── exceptions/          # 异常体系
│   └── schemas/             # 统一响应模型
├── agents/
│   └── text_processor/      # 示例 Agent
│       ├── router.py        # FastAPI 路由
│       ├── service.py       # 业务编排
│       ├── schemas.py       # 数据模型
│       ├── repository/      # 持久化
│       └── workflow/        # DAG 工作流
├── tests/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## 添加新 Agent

在已有项目中快速生成 Agent 骨架：

```bash
talos create agent invoice-review

# 选择:
#   Simple   — router + service + 单 LLM 调用
#   Workflow — router + service + DAG 工作流 + 多节点
```

`main.py` 会自动发现 `agents/*/router.py`，无需手动注册路由。

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
