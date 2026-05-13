# Talos

[中文 / Chinese](README_zh.md)

> **Talos** was the bronze giant of Greek mythology, forged by Hephaestus the divine craftsman — tirelessly patrolling the shores of Crete, faithfully carrying out his guardianship. He is the earliest "automaton" in myth: a sleepless, indefatigable executor.
>
> This project borrows that image: **forge your AI Agent backend as Hephaestus forged Talos — generate a complete, production-ready service in seconds.** You define the Agent's behavioral boundaries; Talos scaffolds the infrastructure — task queues, storage, logging, and workflow orchestration.

An AI Agent project scaffolding tool — rapidly generate AI Agent backend services powered by async task queues (Redis + MongoDB).

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/getting-started/installation/) — Python package manager
- MongoDB & Redis (Docker available for local development)

## Installation

```bash
# Install directly from GitHub (recommended)
uv tool install git+https://github.com/ZyqAlwaysCool/talos.git

# Or clone and install locally
git clone https://github.com/ZyqAlwaysCool/talos.git
cd talos
uv tool install .
```

The `talos` command is globally available after installation:

```bash
talos --help
```

## Quick Start

```bash
# 0. Upgrade the tool (if installed via uv tool)
uv tool upgrade talos

# 1. Create a new project interactively
talos new my-first-agent

# 2. Enter the project directory
cd my-first-agent

# 3. Install dependencies
uv sync

# 4. Edit MongoDB/Redis connection info in .env.local
#    (skip if LLM was already configured via CLI)

# 5. Start services
bash scripts/start.sh all

# 6. Test
curl -X POST http://127.0.0.1:19999/text_processor/create \
  -H "Content-Type: application/json" \
  -d '{"text": "Artificial intelligence is transforming how we live..."}'

curl "http://127.0.0.1:19999/text_processor/query?task_id=<returned task_id>"

# 7. Stop
bash scripts/stop.sh
```

## Interactive CLI

```
$ talos new my-agent

  Select project template:
    Minimal  — core lib + minimal Agent example
  ❯ Standard — + LLM executor + Thinking Stream + pocketflow workflow
    Full     — + SSE push + workflow archiving + auth + Coze/Dify clients

  Select LLM Provider:
    OpenAI-compatible (Qwen / DeepSeek / etc.)
  ❯ Skip, configure manually later

  Enable authentication? (y/N)

  MongoDB database name: (my_agent)
  API service port: (19999)
  Redis queue prefix: (my_agent)
```

If you select an LLM Provider and enter the API Key, `.env.local` is auto-generated — ready to use out of the box.

## Templates

| Template | Includes | Best for |
|------|---------|------|
| **Minimal** | `core/` (task queue, MongoDB, Redis) + example Agent | Prototyping & learning |
| **Standard** | Minimal + LLM executor + Thinking Stream + workflow archiving | Standard AI Agent services |
| **Full** | Standard + SSE push + auth + Coze/Dify clients | Production |

## Project Structure

```
my-agent/
├── main.py                  # FastAPI entry point
├── worker_main.py           # Worker entry point
├── scripts/
│   ├── start.sh             # Start script
│   └── stop.sh              # Stop script
├── core/                    # Infrastructure
│   ├── config/              # Configuration center
│   ├── task/                # Async task queue (Redis backend + MongoDB storage)
│   ├── storage/             # MongoDB abstraction layer
│   ├── logging/             # Logging system
│   ├── middleware/           # HTTP middleware
│   ├── exceptions/          # Exception hierarchy
│   └── schemas/             # Unified response schemas
├── agents/
│   └── text_processor/      # Example Agent
│       ├── router.py        # FastAPI router
│       ├── service.py       # Business orchestration
│       ├── schemas.py       # Data models
│       ├── repository/      # Persistence
│       └── workflow/        # DAG workflow
├── tests/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Add a New Agent

Quickly generate an Agent scaffold within an existing project:

```bash
talos create agent invoice-review

# Options:
#   Simple   — router + service + single LLM call
#   Workflow — router + service + DAG workflow + multi-node
```

`main.py` auto-discovers `agents/*/router.py` — no manual route registration needed.

## Docker Deployment

```bash
cp .env.docker.example .env.docker
# Edit MongoDB/Redis addresses in .env.docker
docker compose up -d
```

## Logs

Logs are written to the `logs/` directory after startup:

```bash
tail -f logs/$(date +%Y-%m-%d).log              # API logs (daily rotation)
tail -f logs/$(date +%Y-%m-%d)-worker.log       # Worker logs (daily rotation)
```

## Development

```bash
git clone https://github.com/ZyqAlwaysCool/talos.git
cd talos
uv sync
uv run pytest tests/ -v
```
