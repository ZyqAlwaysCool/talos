#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"
export PYTHONPATH="$PROJECT_DIR"

if [ -f "$PROJECT_DIR/.env.local" ]; then
    set -a
    source "$PROJECT_DIR/.env.local"
    set +a
fi

PORT="${TALOS_SVR_PORT:-19999}"
PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PID_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

_check_alive() {
    local pid="$1" name="$2" log_name="$3"
    local max_wait=5 elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo -e "${RED}[$name] 启动失败，进程已退出${NC}"
            echo "── 最后 5 行日志 ($log_name) ──"
            local log_file=$(find "$PROJECT_DIR/logs" -name "$log_name" -type f 2>/dev/null | sort | tail -1)
            if [ -n "${log_file:-}" ]; then
                tail -5 "$log_file"
            else
                echo "  (日志文件未生成)"
            fi
            return 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 0
}

start_server() {
    echo -n "[server] 启动 API 服务 (port: $PORT)... "
    nohup uv run python main.py > /dev/null 2>&1 &
    local pid=$!
    echo $pid > "$PID_DIR/server.pid"

    if _check_alive "$pid" "server" "$(date +%Y-%m-%d)*.log"; then
        echo -e "${GREEN}OK${NC}  PID: $pid"
    fi
}

start_worker() {
    echo -n "[worker] 启动 Worker... "
    nohup uv run python worker_main.py > /dev/null 2>&1 &
    local pid=$!
    echo $pid > "$PID_DIR/worker.pid"

    if _check_alive "$pid" "worker" "$(date +%Y-%m-%d)-worker*.log"; then
        echo -e "${GREEN}OK${NC}  PID: $pid"
    fi
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
