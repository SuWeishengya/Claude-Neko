#!/bin/bash
# Claude Neko — 手动启动脚本（不绑定 Claude 会话）
cd "$(dirname "$0")"

PYTHON="./venv/bin/python"

# 检查 venv
if [ ! -f "$PYTHON" ]; then
    echo "❌ venv 未找到，请先运行: python3 -m venv --system-site-packages venv && source venv/bin/activate && pip install pillow"
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

echo "🐾 启动 Claude Neko（手动模式）..."

# GNOME Wayland 下强制走 XWayland
BUDDY_ENV=""
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    BUDDY_ENV="GDK_BACKEND=x11"
    echo "  ℹ️  GNOME Wayland 检测到，使用 XWayland 后端"
fi

# 启动 server（无 session_id，不自动退出）
$PYTHON server.py --port 9100 &>/dev/null &
pid=$!
echo "  ✅ server.py (PID $pid)"
echo "$pid" >> pids.txt
sleep 1

# 启动 monitor（手动模式保留轮询）
$PYTHON claude_monitor.py &>/dev/null &
pid=$!
echo "  ✅ claude_monitor.py (PID $pid)"
echo "$pid" >> pids.txt
sleep 1

# 启动 buddy_widget
env $BUDDY_ENV $PYTHON buddy_widget.py --port 9100 --offset 0 &>/dev/null &
pid=$!
echo "  ✅ buddy_widget.py (PID $pid)"
echo "$pid" >> pids.txt

echo ""
echo "🐱 小橘猫已启动！拖拽移动，置顶显示"
echo "   停止: ./stop.sh"
