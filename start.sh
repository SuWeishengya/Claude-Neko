#!/bin/bash
# Claude Neko — 手动启动脚本（不绑定 Claude 会话）
cd "$(dirname "$0")" || exit 1

PYTHON="./venv/bin/python"

# 检查 venv
if [ ! -f "$PYTHON" ]; then
    echo "❌ venv 未找到，请先运行: python3 -m venv --system-site-packages venv && source venv/bin/activate && pip install pillow"
    exit 1
fi

# 停止旧进程
if [ -f pids.txt ]; then
    echo "🔄 停止旧进程..."
    while read -r pid; do
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

# 检查端口是否被占用
PORT=9100
if ss -tlnp 2>/dev/null | grep -qE ":${PORT}\b"; then
    echo "❌ 端口 $PORT 已被占用，请先停止冲突进程"
    exit 1
fi

# 启动 server（无 session_id，不自动退出）
$PYTHON server.py --port $PORT >>neko.log 2>&1 &
pid=$!
echo "  ✅ server.py (PID $pid)"
echo "$pid" >> pids.txt
sleep 1

# 启动 monitor（手动模式保留轮询）
$PYTHON claude_monitor.py >>neko.log 2>&1 &
pid=$!
echo "  ✅ claude_monitor.py (PID $pid)"
echo "$pid" >> pids.txt
sleep 1

# 启动 buddy_widget
env $BUDDY_ENV $PYTHON buddy_widget.py --port 9100 --offset 0 >>neko.log 2>&1 &
pid=$!
echo "  ✅ buddy_widget.py (PID $pid)"
echo "$pid" >> pids.txt

echo ""
echo "🐱 小橘猫已启动！拖拽移动，置顶显示"
echo "   停止: ./stop.sh"
