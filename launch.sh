#!/bin/bash
# Claude Neko — SessionStart 启动脚本
# 由 Claude Code SessionStart hook 调用
# 从 stdin 读取 session_id，启动 server + neko

set -e

INSTALL_DIR="$HOME/.local/share/claude-neko"
STATE_DIR="$HOME/.local/state/claude-neko"
SESSIONS_DIR="$STATE_DIR/sessions"
PYTHON="$INSTALL_DIR/venv/bin/python"

# 子进程 PID，trap EXIT 时清理
PID_SERVER=""
PID_WIDGET=""

LOG="$HOME/.local/state/claude-neko/launch.log"
log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }

cleanup() {
    log "CLEANUP: killing server=$PID_SERVER widget=$PID_WIDGET"
    [ -n "$PID_SERVER" ] && kill "$PID_SERVER" 2>/dev/null || true
    [ -n "$PID_WIDGET" ] && kill "$PID_WIDGET" 2>/dev/null || true
}
trap cleanup EXIT
log "=== started ==="

# 创建运行时目录
mkdir -p "$SESSIONS_DIR"

# 从 stdin 读取 hook 数据
INPUT=$(cat)
log "stdin: $INPUT"
SESSION_ID=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
log "session_id: $SESSION_ID"

if [ -z "$SESSION_ID" ]; then
    log "ERROR: No session_id"
    echo "Error: No session_id" >&2
    exit 1
fi

# 校验 session_id 格式（只允许字母数字和连字符，防注入）
if [[ ! "$SESSION_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "Error: Invalid session_id" >&2
    exit 1
fi

# 清理残留注册文件（检查 PID 存活）
for f in "$SESSIONS_DIR"/*.json; do
    [ -f "$f" ] || continue
    PID=$(F="$f" python3 -c "import json,os; print(json.load(open(os.environ['F'])).get('pid_server',0))" 2>/dev/null)
    if [ -n "$PID" ] && [ "$PID" != "0" ]; then
        if ! kill -0 "$PID" 2>/dev/null; then
            rm -f "$f"
        fi
    fi
done

# 检查是否已有该 session 的注册（已在运行）
REG_FILE="$SESSIONS_DIR/$SESSION_ID.json"
if [ -f "$REG_FILE" ]; then
    PID=$(F="$REG_FILE" python3 -c "import json,os; print(json.load(open(os.environ['F'])).get('pid_server',0))" 2>/dev/null)
    if kill -0 "$PID" 2>/dev/null; then
        # 已在运行，无需重复启动
        exit 0
    fi
    rm -f "$REG_FILE"
fi

# 找空闲端口（从 9100 开始，确保端口未被占用）
PORT=9100
for f in "$SESSIONS_DIR"/*.json; do
    [ -f "$f" ] || continue
    P=$(F="$f" python3 -c "import json,os; print(json.load(open(os.environ['F'])).get('port',0))" 2>/dev/null)
    if [ -n "$P" ] && [ "$P" -ge "$PORT" ] 2>/dev/null; then
        PORT=$((P + 1))
    fi
done
# 确保端口未被其他进程占用（精确匹配端口号）
while ss -tlnp 2>/dev/null | grep -qE ":${PORT}\b"; do
    PORT=$((PORT + 1))
done

# 计算窗口偏移（当前活跃小猫数量）
OFFSET=$(ls -1 "$SESSIONS_DIR"/*.json 2>/dev/null | wc -l)

# 启动 server.py（重定向 stdin 避免抢占 Claude Code 的终端输入）
"$PYTHON" "$INSTALL_DIR/server.py" \
    --port "$PORT" \
    --session-id "$SESSION_ID" \
    --state-dir "$STATE_DIR" </dev/null &>/dev/null &
PID_SERVER=$!

# 等待 server 就绪（最多 5 秒，用 python 替代 curl）
SERVER_READY=false
for i in $(seq 1 10); do
    if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:$PORT/api/state', timeout=1)" 2>/dev/null; then
        SERVER_READY=true
        break
    fi
    # 检查 server 进程是否还活着
    if ! kill -0 "$PID_SERVER" 2>/dev/null; then
        echo "Error: server.py exited prematurely" >&2
        exit 1
    fi
    sleep 0.5
done
if [ "$SERVER_READY" != "true" ]; then
    echo "Error: server.py failed to start within 5 seconds" >&2
    exit 1
fi

# 发送 session_start 事件 → 小猫进入 idle 状态（等待用户输入）
"$PYTHON" -c "
import urllib.request, json
urllib.request.urlopen(urllib.request.Request(
    'http://127.0.0.1:$PORT/api/hook',
    data=json.dumps({'event':'session_start','msg':'Ready'}).encode(),
    headers={'Content-Type':'application/json'}
), timeout=2)
" 2>/dev/null || true

# 启动 neko.py（GNOME Wayland 下强制 XWayland 以支持置顶）
BUDDY_ENV=""
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
    BUDDY_ENV="GDK_BACKEND=x11"
fi
env $BUDDY_ENV "$PYTHON" "$INSTALL_DIR/neko_widget.py" \
    --port "$PORT" \
    --offset "$OFFSET" </dev/null &>/dev/null &
PID_WIDGET=$!

# 注册文件由 server.py 自动写入（write_registration），无需此处重复写入
# server.py 会在启动时写入 {session_id, port, pid_server, created_at}

# 正常退出，取消 trap（不杀子进程）
trap - EXIT

# 输出到 stderr 避免干扰 Claude Code 的 stdin/stdout
echo "🐾 Cat started: session=$SESSION_ID port=$PORT offset=$OFFSET" >&2
