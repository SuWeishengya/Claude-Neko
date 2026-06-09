#!/bin/bash
# Claude Desktop Buddy — 停止脚本
cd "$(dirname "$0")"

if [ -f pids.txt ]; then
    echo "🛑 停止 Claude Desktop Buddy..."
    while read pid; do
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "  ✅ 已停止 PID $pid"
        fi
    done < pids.txt
    rm -f pids.txt
    echo "🐱 小橘猫已停止"
else
    echo "⚠️ 未找到运行中的进程"
fi
