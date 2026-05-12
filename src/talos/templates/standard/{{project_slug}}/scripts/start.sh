#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR"

# 加载 .env.local
if [ -f "$PROJECT_DIR/.env.local" ]; then
    set -a
    source "$PROJECT_DIR/.env.local"
    set +a
fi

PORT="${TALOS_SVR_PORT:-19999}"
PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PID_DIR"

start_server() {
    echo "[server] 启动 API 服务 (port: $PORT)..."
    nohup uv run python main.py > /dev/null 2>&1 &
    echo $! > "$PID_DIR/server.pid"
    echo "[server] PID: $(cat $PID_DIR/server.pid)  日志: logs/$(date +%Y-%m-%d).log"
}

start_worker() {
    echo "[worker] 启动 Worker..."
    nohup uv run python worker_main.py > /dev/null 2>&1 &
    echo $! > "$PID_DIR/worker.pid"
    echo "[worker] PID: $(cat $PID_DIR/worker.pid)  日志: logs/$(date +%Y-%m-%d)-worker.log"
}

start_all() {
    echo "=== 启动 {{ project_name }} ==="
    start_server
    sleep 2
    start_worker
    echo ""
    echo "API:   http://0.0.0.0:$PORT"
    echo "Docs:  http://0.0.0.0:$PORT/docs"
    echo ""
    echo "日志:  tail -f logs/\$(date +%Y-%m-%d).log"
    echo "       tail -f logs/\$(date +%Y-%m-%d)-worker.log"
    echo "停止:  bash scripts/stop.sh"
}

case "${1:-all}" in
    server) start_server ;;
    worker) start_worker ;;
    all)    start_all ;;
    *)
        echo "Usage: $0 {server|worker|all}"
        exit 1
        ;;
esac
