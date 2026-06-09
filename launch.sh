#!/bin/bash
# Claude Neko — SessionStart 启动脚本
# 由 Claude Code SessionStart hook 调用
# 从 stdin 读取 session_id，启动 server + buddy_widget

set -e

INSTALL_DIR="$HOME/.local/share/claude-desktop-pet"
STATE_DIR="$HOME/.local/state/claude-desktop-pet"
SESSIONS_DIR="$STATE_DIR/sessions"
PYTHON="$INSTALL_DIR/venv/bin/python"

# 创建运行时目录
mkdir -p "$SESSIONS_DIR"

# 从 stdin 读取 hook 数据
INPUT=$(cat)
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
    echo "Error: No session_id" >&2
    exit 1
fi

# 清理残留注册文件（检查 PID 存活）
for f in "$SESSIONS_DIR"/*.json; do
    [ -f "$f" ] || continue
    PID=$(python3 -c "import json; print(json.load(open('$f')).get('pid_server',0))" 2>/dev/null)
    if [ -n "$PID" ] && [ "$PID" != "0" ]; then
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$f"
        fi
    fi
done

# 检查是否已有该 session 的注册（已在运行）
REG_FILE="$SESSIONS_DIR/$SESSION_ID.json"
if [ -f "$REG_FILE" ]; then
    PID=$(python3 -c "import json; print(json.load(open('$REG_FILE')).get('pid_server',0))" 2>/dev/null)
    if kill -0 "$PID" 2>/dev/null; then
        # 已在运行，无需重复启动
        exit 0
    fi
    rm -f "$REG_FILE"
fi

# 找空闲端口（从 9100 开始）
PORT=9100
for f in "$SESSIONS_DIR"/*.json; do
    [ -f "$f" ] || continue
    P=$(python3 -c "import json; print(json.load(open('$f')).get('port',0))" 2>/dev/null)
    if [ -n "$P" ] && [ "$P" -ge "$PORT" ] 2>/dev/null; then
        PORT=$((P + 1))
    fi
done

# 计算窗口偏移（当前活跃小猫数量）
OFFSET=$(ls -1 "$SESSIONS_DIR"/*.json 2>/dev/null | wc -l)

# 启动 server.py
"$PYTHON" "$INSTALL_DIR/server.py" \
    --port "$PORT" \
    --session-id "$SESSION_ID" \
    --state-dir "$STATE_DIR" &
PID_SERVER=$!

# 等待 server 就绪（最多 5 秒）
for i in $(seq 1 10); do
    if curl -s "http://127.0.0.1:$PORT/api/state" >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# 启动 buddy_widget.py（GNOME Wayland 下强制 XWayland 以支持置顶）
BUDDY_ENV=""
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    BUDDY_ENV="GDK_BACKEND=x11"
fi
env $BUDDY_ENV "$PYTHON" "$INSTALL_DIR/buddy_widget.py" \
    --port "$PORT" \
    --offset "$OFFSET" &
PID_WIDGET=$!

echo "🐾 Cat started: session=$SESSION_ID port=$PORT offset=$OFFSET"
