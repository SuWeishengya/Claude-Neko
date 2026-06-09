#!/bin/bash
# Claude Desktop Buddy — Linux 启动脚本
cd "$(dirname "$0")"

PYTHON="./venv/bin/python"

# 检查 venv
if [ ! -f "$PYTHON" ]; then
    echo "❌ venv 未找到，请先运行: python3 -m venv venv && source venv/bin/activate && pip install pillow watchdog"
    exit 1
fi

# 停止旧进程
if [ -f pids.txt ]; then
    echo "🔄 停止旧进程..."
    while read pid; do
        kill "$pid" 2>/dev/null
    done < pids.txt
    rm -f pids.txt
    sleep 1
fi

echo "🐾 启动 Claude Desktop Buddy..."

# 启动三个进程（用 claude_monitor 替代 cc_switch_monitor）
for script in server.py claude_monitor.py buddy_widget.py; do
    $PYTHON "$script" &>/dev/null &
    pid=$!
    echo "  ✅ $script (PID $pid)"
    echo "$pid" >> pids.txt
    sleep 1
done

echo ""
echo "🐱 小橘猫已启动！拖拽移动，置顶显示"
echo "   停止: ./stop.sh"
