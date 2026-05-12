#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"

stop_by_pid() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "[$name] 停止进程 PID: $pid..."
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
        echo "[$name] 已停止"
    else
        echo "[$name] 未在运行"
    fi
}

echo "=== 停止 {{ project_name }} ==="
stop_by_pid "server"
stop_by_pid "worker"

# 清理可能残留的进程
pkill -f "main.py" 2>/dev/null || true
pkill -f "worker_main.py" 2>/dev/null || true

echo "已全部停止"
