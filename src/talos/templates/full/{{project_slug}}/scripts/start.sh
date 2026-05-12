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
LOGS_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$LOGS_DIR" "$PID_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

SERVER_LOG="$LOGS_DIR/$(date +%Y-%m-%d).log"
WORKER_LOG="$LOGS_DIR/$(date +%Y-%m-%d)-${WORKER_LOG_SUFFIX:-worker}.log"

_show_error() {
    local name="$1" err_file="$2" log_file="$3"
    echo -e "${RED}[$name] 启动失败，进程已退出${NC}"
    if [ -s "$err_file" ]; then
        echo "── 启动错误输出 ──"
        cat "$err_file" | tail -10
    fi
    if [ -f "$log_file" ]; then
        echo "── 最后日志 ($(basename "$log_file")) ──"
        tail -5 "$log_file"
    fi
    rm -f "$err_file"
}

_check_alive() {
    local pid="$1" name="$2" err_file="$3" log_file="$4"
    local max_wait=5 elapsed=0
    while [ $elapsed -lt $max_wait ]; do
        if ! kill -0 "$pid" 2>/dev/null; then
            _show_error "$name" "$err_file" "$log_file"
            return 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    rm -f "$err_file"
    return 0
}

start_server() {
    echo -n "[server] 启动 API 服务 (port: $PORT)... "
    local err_file=$(mktemp)
    nohup uv run python main.py > /dev/null 2> "$err_file" &
    local pid=$!
    echo $pid > "$PID_DIR/server.pid"

    if _check_alive "$pid" "server" "$err_file" "$SERVER_LOG"; then
        echo -e "${GREEN}OK${NC}  PID: $pid"
    fi
}

start_worker() {
    echo -n "[worker] 启动 Worker... "
    local err_file=$(mktemp)
    nohup uv run python worker_main.py > /dev/null 2> "$err_file" &
    local pid=$!
    echo $pid > "$PID_DIR/worker.pid"

    if _check_alive "$pid" "worker" "$err_file" "$WORKER_LOG"; then
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
    echo "日志:  tail -f $SERVER_LOG"
    echo "       tail -f $WORKER_LOG"
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
