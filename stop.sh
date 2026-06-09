#!/bin/bash
# Claude Neko — 停止脚本（手动模式 + hook 模式）
cd "$(dirname "$0")"

echo "🛑 停止 Claude Neko..."

STOPPED=0

# 停止 pids.txt 中记录的进程（手动模式）
if [ -f pids.txt ]; then
    while read pid; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "  ✅ 已停止 PID $pid"
            STOPPED=$((STOPPED + 1))
        fi
    done < pids.txt
    rm -f pids.txt
fi

# 也停止 hook 模式启动的进程（限定路径避免误杀）
pkill -f "claude-desktop-pet/buddy_widget.py" 2>/dev/null && STOPPED=$((STOPPED + 1)) || true
pkill -f "claude-desktop-pet/server.py" 2>/dev/null && STOPPED=$((STOPPED + 1)) || true

if [ "$STOPPED" -gt 0 ]; then
    echo "🐱 小橘猫已停止"
else
    echo "⚠️ 未找到运行中的进程"
fi
